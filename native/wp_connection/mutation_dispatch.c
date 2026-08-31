#include "wp_connection.h"

#include <pipewire/keys.h>
#include <spa/pod/pod.h>
#include <math.h>
#include <string.h>


#define NATIVE_MUTATION_DISPATCH_PAYLOAD_VERSION 1


typedef enum {
    MUTATION_DISPATCH_READY,
    MUTATION_DISPATCH_STALE_GENERATION,
    MUTATION_DISPATCH_STALE_SEQUENCE,
    MUTATION_DISPATCH_GENERATION_LOST,
    MUTATION_DISPATCH_RUNTIME_STOPPED,
    MUTATION_DISPATCH_UNSUPPORTED_OPERATION,
    MUTATION_DISPATCH_TARGET_NOT_FOUND,
    MUTATION_DISPATCH_NOT_WRITABLE,
    MUTATION_DISPATCH_OWNERSHIP_CONFLICT,
    MUTATION_DISPATCH_NATIVE_REJECTED,
} MutationDispatchResult;


typedef struct {
    gchar *request_id;
    gchar *operation;
    gchar *target_kind;
    guint32 target_id;
    gchar *parameter_id;
    guint32 metadata_subject;
    gchar *metadata_key;
    gchar *metadata_type;
    gchar *metadata_value;
    guint32 output_node_id;
    guint32 output_port_id;
    guint32 input_node_id;
    guint32 input_port_id;
    guint32 link_id;
    gchar *link_owner;
    gchar *link_desired_id;
    WpProperties *link_properties;
    guint32 flags;
    GBytes *pod_data;
    gboolean has_mixer_volume;
    gdouble mixer_volume;
    gboolean has_mixer_mute;
    gboolean mixer_mute;
    guint64 expected_generation;
    guint64 expected_sequence;
    gboolean has_expected_sequence;
    guint64 enqueued_generation;
    guint64 dispatch_order;
    guint64 observed_generation;
    guint64 observed_sequence;
    MutationDispatchResult result;
    GMutex lock;
    GCond cond;
    gboolean completed;
} MutationDispatchCall;


static gboolean dispatch_next_mutation_on_wp_thread(gpointer user_data);


static void managed_link_spec_free(gpointer data) {
    WpManagedLinkSpec *spec = data;
    if (!spec) return;
    g_free(spec->owner);
    g_free(spec->desired_id);
    g_clear_object(&spec->proxy);
    g_free(spec);
}


static gchar *managed_link_key(const gchar *owner, const gchar *desired_id) {
    return g_strdup_printf("%s\x1f%s", owner, desired_id);
}


void wp_connection_managed_links_init(WPConnection *conn) {
    conn->managed_links = g_hash_table_new_full(
        g_str_hash, g_str_equal, g_free, managed_link_spec_free);
}


void wp_connection_managed_links_reset(WPConnection *conn) {
    if (conn && conn->managed_links) g_hash_table_remove_all(conn->managed_links);
}


void wp_connection_managed_links_clear(WPConnection *conn) {
    if (!conn || !conn->managed_links) return;
    g_hash_table_destroy(conn->managed_links);
    conn->managed_links = NULL;
}


const WpManagedLinkSpec *wp_connection_managed_link_lookup_identity(
    WPConnection *conn, const gchar *owner, const gchar *desired_id)
{
    if (!conn || !conn->managed_links || !owner || !desired_id) return NULL;
    g_autofree gchar *key = managed_link_key(owner, desired_id);
    return g_hash_table_lookup(conn->managed_links, key);
}


static gboolean managed_link_endpoints_equal(
    const WpManagedLinkSpec *spec,
    guint32 output_node_id,
    guint32 output_port_id,
    guint32 input_node_id,
    guint32 input_port_id)
{
    return spec &&
        spec->output_node_id == output_node_id &&
        spec->output_port_id == output_port_id &&
        spec->input_node_id == input_node_id &&
        spec->input_port_id == input_port_id;
}


const WpManagedLinkSpec *wp_connection_managed_link_lookup_endpoints(
    WPConnection *conn,
    guint32 output_node_id,
    guint32 output_port_id,
    guint32 input_node_id,
    guint32 input_port_id)
{
    if (!conn || !conn->managed_links) return NULL;
    GHashTableIter iterator;
    gpointer value = NULL;
    g_hash_table_iter_init(&iterator, conn->managed_links);
    while (g_hash_table_iter_next(&iterator, NULL, &value)) {
        WpManagedLinkSpec *spec = value;
        if (managed_link_endpoints_equal(
                spec, output_node_id, output_port_id,
                input_node_id, input_port_id)) {
            return spec;
        }
    }
    return NULL;
}


void wp_connection_managed_link_forget_endpoints(
    WPConnection *conn,
    guint32 output_node_id,
    guint32 output_port_id,
    guint32 input_node_id,
    guint32 input_port_id)
{
    if (!conn || !conn->managed_links) return;
    GHashTableIter iterator;
    gpointer value = NULL;
    g_hash_table_iter_init(&iterator, conn->managed_links);
    while (g_hash_table_iter_next(&iterator, NULL, &value)) {
        WpManagedLinkSpec *spec = value;
        if (managed_link_endpoints_equal(
                spec, output_node_id, output_port_id,
                input_node_id, input_port_id)) {
            g_hash_table_iter_remove(&iterator);
            return;
        }
    }
}


static void managed_link_store(
    WPConnection *conn, MutationDispatchCall *call, WpLink *link)
{
    WpManagedLinkSpec *spec = g_new0(WpManagedLinkSpec, 1);
    spec->owner = g_strdup(call->link_owner);
    spec->desired_id = g_strdup(call->link_desired_id);
    spec->proxy = g_object_ref(link);
    spec->output_node_id = call->output_node_id;
    spec->output_port_id = call->output_port_id;
    spec->input_node_id = call->input_node_id;
    spec->input_port_id = call->input_port_id;
    g_hash_table_replace(
        conn->managed_links,
        managed_link_key(call->link_owner, call->link_desired_id),
        spec);
}


static gboolean object_matches_kind(GObject *object, const gchar *kind) {
    if (g_str_equal(kind, "device")) return WP_IS_DEVICE(object);
    if (g_str_equal(kind, "node")) return WP_IS_NODE(object);
    if (g_str_equal(kind, "port")) return WP_IS_PORT(object);
    if (g_str_equal(kind, "link")) return WP_IS_LINK(object);
    return FALSE;
}


static WpPipewireObject *find_pipewire_object(
    WPConnection *conn, const gchar *kind, guint32 id)
{
    g_autoptr(WpIterator) iterator = wp_object_manager_new_iterator(conn->om);
    g_auto(GValue) value = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &value)) {
        GObject *object = g_value_get_object(&value);
        if (object && object_matches_kind(object, kind) && WP_IS_PROXY(object) &&
            wp_proxy_get_bound_id(WP_PROXY(object)) == id) {
            WpPipewireObject *result = g_object_ref(WP_PIPEWIRE_OBJECT(object));
            g_value_unset(&value);
            return result;
        }
        g_value_unset(&value);
    }
    return NULL;
}


static WpMetadata *find_metadata(WPConnection *conn, guint32 id) {
    g_autoptr(WpIterator) iterator = wp_object_manager_new_iterator(conn->om);
    g_auto(GValue) value = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &value)) {
        GObject *object = g_value_get_object(&value);
        if (object && WP_IS_METADATA(object) && WP_IS_PROXY(object) &&
            wp_proxy_get_bound_id(WP_PROXY(object)) == id) {
            WpMetadata *result = g_object_ref(WP_METADATA(object));
            g_value_unset(&value);
            return result;
        }
        g_value_unset(&value);
    }
    return NULL;
}


static gboolean parameter_is_writable(
    WpPipewireObject *object, const gchar *parameter_id)
{
    g_autoptr(GVariant) info = wp_pipewire_object_get_param_info(object);
    if (!info || !g_variant_is_of_type(info, G_VARIANT_TYPE("a{ss}"))) {
        return FALSE;
    }
    GVariantIter iterator;
    const gchar *id = NULL;
    const gchar *permissions = NULL;
    g_variant_iter_init(&iterator, info);
    while (g_variant_iter_loop(&iterator, "{&s&s}", &id, &permissions)) {
        if (g_strcmp0(id, parameter_id) == 0) {
            return permissions && strchr(permissions, 'w');
        }
    }
    return FALSE;
}


static MutationDispatchResult execute_set_parameter(
    WPConnection *conn, MutationDispatchCall *call)
{
    WpPipewireObject *object = find_pipewire_object(
        conn, call->target_kind, call->target_id);
    if (!object) return MUTATION_DISPATCH_TARGET_NOT_FOUND;
    if (!parameter_is_writable(object, call->parameter_id)) {
        g_object_unref(object);
        return MUTATION_DISPATCH_NOT_WRITABLE;
    }

    gsize size = 0;
    gconstpointer bytes = g_bytes_get_data(call->pod_data, &size);
    if (!bytes || size < sizeof(struct spa_pod)) {
        g_object_unref(object);
        return MUTATION_DISPATCH_NATIVE_REJECTED;
    }
    gpointer pod_copy = g_malloc(size);
    if (!pod_copy) {
        g_object_unref(object);
        return MUTATION_DISPATCH_NATIVE_REJECTED;
    }
    memcpy(pod_copy, bytes, size);
    WpSpaPod *wrapped = wp_spa_pod_new_wrap((struct spa_pod *) pod_copy);
    WpSpaPod *parameter = wrapped ? wp_spa_pod_copy(wrapped) : NULL;
    if (wrapped) wp_spa_pod_unref(wrapped);
    g_free(pod_copy);
    if (!parameter) {
        g_object_unref(object);
        return MUTATION_DISPATCH_NATIVE_REJECTED;
    }

    const gboolean accepted = wp_pipewire_object_set_param(
        object, call->parameter_id, call->flags, parameter);
    g_object_unref(object);
    return accepted ? MUTATION_DISPATCH_READY : MUTATION_DISPATCH_NATIVE_REJECTED;
}


static MutationDispatchResult execute_set_node_mixer(
    WPConnection *conn, MutationDispatchCall *call)
{
    WpPipewireObject *object = find_pipewire_object(
        conn, "node", call->target_id);
    if (!object) return MUTATION_DISPATCH_TARGET_NOT_FOUND;
    g_object_unref(object);

    return wp_connection_set_mixer_state(
        conn,
        call->target_id,
        call->has_mixer_volume,
        call->mixer_volume,
        call->has_mixer_mute,
        call->mixer_mute)
        ? MUTATION_DISPATCH_READY
        : MUTATION_DISPATCH_NOT_WRITABLE;
}


static MutationDispatchResult execute_metadata(
    WPConnection *conn, MutationDispatchCall *call, gboolean clear)
{
    WpMetadata *metadata = find_metadata(conn, call->target_id);
    if (!metadata) return MUTATION_DISPATCH_TARGET_NOT_FOUND;
    wp_metadata_set(
        metadata,
        call->metadata_subject,
        call->metadata_key,
        clear ? NULL : call->metadata_type,
        clear ? NULL : call->metadata_value);
    g_object_unref(metadata);
    return MUTATION_DISPATCH_READY;
}


static void on_managed_link_activated(
    GObject *source, GAsyncResult *result, gpointer user_data)
{
    g_autoptr(GError) error = NULL;
    if (!wp_object_activate_finish(WP_OBJECT(source), result, &error)) {
        g_warning(
            "managed link activation failed: %s",
            error ? error->message : "unknown error");
    }
    g_object_unref(user_data);
}


static gboolean endpoint_exists(
    WPConnection *conn, const gchar *kind, guint32 object_id)
{
    WpPipewireObject *object = find_pipewire_object(conn, kind, object_id);
    if (!object) return FALSE;
    g_object_unref(object);
    return TRUE;
}


static MutationDispatchResult managed_link_preflight(
    WPConnection *conn, MutationDispatchCall *call, gboolean *already_exists)
{
    gboolean found_exact = FALSE;
    g_autoptr(WpIterator) iterator = wp_object_manager_new_iterator(conn->om);
    g_auto(GValue) value = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &value)) {
        GObject *object = g_value_get_object(&value);
        if (!object || !WP_IS_LINK(object) ||
            !(wp_object_get_active_features(WP_OBJECT(object)) &
              WP_PIPEWIRE_OBJECT_FEATURE_INFO)) {
            g_value_unset(&value);
            continue;
        }
        guint32 output_node = 0;
        guint32 output_port = 0;
        guint32 input_node = 0;
        guint32 input_port = 0;
        wp_link_get_linked_object_ids(
            WP_LINK(object),
            &output_node,
            &output_port,
            &input_node,
            &input_port);
        const gboolean same_topology =
            output_node == call->output_node_id &&
            output_port == call->output_port_id &&
            input_node == call->input_node_id &&
            input_port == call->input_port_id;
        const WpManagedLinkSpec *spec =
            wp_connection_managed_link_lookup_endpoints(
                conn, output_node, output_port, input_node, input_port);
        const gchar *owner = spec ? spec->owner : NULL;
        const gchar *desired_id = spec ? spec->desired_id : NULL;
        const gboolean same_identity =
            g_strcmp0(owner, call->link_owner) == 0 &&
            g_strcmp0(desired_id, call->link_desired_id) == 0;
        g_value_unset(&value);

        if (same_topology && same_identity) {
            if (found_exact) return MUTATION_DISPATCH_OWNERSHIP_CONFLICT;
            found_exact = TRUE;
        } else if (same_topology || same_identity) {
            return MUTATION_DISPATCH_OWNERSHIP_CONFLICT;
        }
    }
    *already_exists = found_exact;
    return MUTATION_DISPATCH_READY;
}


static MutationDispatchResult execute_create_link(
    WPConnection *conn, MutationDispatchCall *call)
{
    if (!endpoint_exists(conn, "node", call->output_node_id) ||
        !endpoint_exists(conn, "port", call->output_port_id) ||
        !endpoint_exists(conn, "node", call->input_node_id) ||
        !endpoint_exists(conn, "port", call->input_port_id)) {
        return MUTATION_DISPATCH_TARGET_NOT_FOUND;
    }
    gboolean already_exists = FALSE;
    MutationDispatchResult preflight = managed_link_preflight(
        conn, call, &already_exists);
    if (preflight != MUTATION_DISPATCH_READY || already_exists) {
        return preflight;
    }

    WpProperties *properties = call->link_properties
        ? wp_properties_copy(call->link_properties)
        : wp_properties_new_empty();
    if (!properties) return MUTATION_DISPATCH_NATIVE_REJECTED;
    wp_properties_setf(
        properties, PW_KEY_LINK_OUTPUT_NODE, "%u", call->output_node_id);
    wp_properties_setf(
        properties, PW_KEY_LINK_OUTPUT_PORT, "%u", call->output_port_id);
    wp_properties_setf(
        properties, PW_KEY_LINK_INPUT_NODE, "%u", call->input_node_id);
    wp_properties_setf(
        properties, PW_KEY_LINK_INPUT_PORT, "%u", call->input_port_id);
    wp_properties_set(properties, "open-cinema.owner", call->link_owner);
    wp_properties_set(
        properties, "open-cinema.desired-id", call->link_desired_id);

    WpLink *link = wp_link_new_from_factory(
        conn->core, "link-factory", properties);
    if (!link) return MUTATION_DISPATCH_NATIVE_REJECTED;
    managed_link_store(conn, call, link);
    wp_object_activate(
        WP_OBJECT(link),
        WP_OBJECT_FEATURES_ALL,
        NULL,
        on_managed_link_activated,
        g_object_ref(link));
    g_object_unref(link);
    return MUTATION_DISPATCH_READY;
}


static MutationDispatchResult execute_remove_link(
    WPConnection *conn, MutationDispatchCall *call)
{
    WpPipewireObject *object = find_pipewire_object(conn, "link", call->link_id);
    if (!object) return MUTATION_DISPATCH_READY;
    guint32 output_node = 0;
    guint32 output_port = 0;
    guint32 input_node = 0;
    guint32 input_port = 0;
    wp_link_get_linked_object_ids(
        WP_LINK(object),
        &output_node,
        &output_port,
        &input_node,
        &input_port);
    const WpManagedLinkSpec *spec =
        wp_connection_managed_link_lookup_identity(
            conn, call->link_owner, call->link_desired_id);
    if (!managed_link_endpoints_equal(
            spec, output_node, output_port, input_node, input_port)) {
        g_object_unref(object);
        return MUTATION_DISPATCH_OWNERSHIP_CONFLICT;
    }
    wp_global_proxy_request_destroy(WP_GLOBAL_PROXY(object));
    g_object_unref(object);
    return MUTATION_DISPATCH_READY;
}


static MutationDispatchResult execute_mutation(
    WPConnection *conn, MutationDispatchCall *call)
{
    if (g_str_equal(call->operation, "set_parameter")) {
        return execute_set_parameter(conn, call);
    }
    if (g_str_equal(call->operation, "set_node_mixer")) {
        return execute_set_node_mixer(conn, call);
    }
    if (g_str_equal(call->operation, "select_profile") ||
        g_str_equal(call->operation, "select_route")) {
        return execute_set_parameter(conn, call);
    }
    if (g_str_equal(call->operation, "set_metadata")) {
        return execute_metadata(conn, call, FALSE);
    }
    if (g_str_equal(call->operation, "clear_metadata")) {
        return execute_metadata(conn, call, TRUE);
    }
    if (g_str_equal(call->operation, "create_link")) {
        return execute_create_link(conn, call);
    }
    if (g_str_equal(call->operation, "remove_link")) {
        return execute_remove_link(conn, call);
    }
    return MUTATION_DISPATCH_UNSUPPORTED_OPERATION;
}


static void complete_call(
    MutationDispatchCall *call,
    MutationDispatchResult result,
    guint64 observed_generation,
    guint64 observed_sequence)
{
    g_mutex_lock(&call->lock);
    if (!call->completed) {
        call->result = result;
        call->observed_generation = observed_generation;
        call->observed_sequence = observed_sequence;
        call->completed = TRUE;
        g_cond_signal(&call->cond);
    }
    g_mutex_unlock(&call->lock);
}


static void schedule_dispatch_locked(WPConnection *conn) {
    if (conn->mutation_source_scheduled || !conn->ctx ||
        g_queue_is_empty(conn->mutation_queue)) {
        return;
    }
    conn->mutation_source_scheduled = TRUE;
    GSource *source = g_idle_source_new();
    g_source_set_callback(
        source, dispatch_next_mutation_on_wp_thread, conn, NULL);
    g_source_attach(source, conn->ctx);
    g_source_unref(source);
}


static gboolean dispatch_next_mutation_on_wp_thread(gpointer user_data) {
    WPConnection *conn = user_data;
    g_mutex_lock(&conn->mutation_lock);
    MutationDispatchCall *call = g_queue_pop_head(conn->mutation_queue);
    if (!call) {
        conn->mutation_source_scheduled = FALSE;
        g_mutex_unlock(&conn->mutation_lock);
        return G_SOURCE_REMOVE;
    }
    g_mutex_unlock(&conn->mutation_lock);

    g_mutex_lock(&conn->lock);
    const gboolean stopped = conn->stop_requested;
    const guint64 generation = conn->generation;
    g_mutex_unlock(&conn->lock);
    const guint64 sequence = conn->sequence;

    MutationDispatchResult result = MUTATION_DISPATCH_READY;
    if (stopped || !conn->core || !conn->om) {
        result = MUTATION_DISPATCH_RUNTIME_STOPPED;
    } else if (generation != call->enqueued_generation) {
        result = MUTATION_DISPATCH_GENERATION_LOST;
    } else if (generation != call->expected_generation) {
        result = MUTATION_DISPATCH_STALE_GENERATION;
    } else if (call->has_expected_sequence &&
               sequence != call->expected_sequence) {
        result = MUTATION_DISPATCH_STALE_SEQUENCE;
    } else {
        result = execute_mutation(conn, call);
    }
    complete_call(call, result, generation, sequence);

    // One call per idle dispatch lets lifecycle sources interleave and cancel
    // the still-queued generation-scoped requests deterministically.
    g_mutex_lock(&conn->mutation_lock);
    conn->mutation_source_scheduled = FALSE;
    schedule_dispatch_locked(conn);
    g_mutex_unlock(&conn->mutation_lock);
    return G_SOURCE_REMOVE;
}


static const gchar *disposition(MutationDispatchResult result) {
    switch (result) {
        case MUTATION_DISPATCH_READY:
            return "ready";
        case MUTATION_DISPATCH_STALE_GENERATION:
        case MUTATION_DISPATCH_STALE_SEQUENCE:
        case MUTATION_DISPATCH_UNSUPPORTED_OPERATION:
        case MUTATION_DISPATCH_TARGET_NOT_FOUND:
        case MUTATION_DISPATCH_NOT_WRITABLE:
        case MUTATION_DISPATCH_OWNERSHIP_CONFLICT:
            return "rejected";
        case MUTATION_DISPATCH_NATIVE_REJECTED:
            return "failed";
        case MUTATION_DISPATCH_GENERATION_LOST:
        case MUTATION_DISPATCH_RUNTIME_STOPPED:
            return "cancelled";
    }
    return "cancelled";
}


static const gchar *failure_code(MutationDispatchResult result) {
    switch (result) {
        case MUTATION_DISPATCH_READY:
            return NULL;
        case MUTATION_DISPATCH_STALE_GENERATION:
            return "stale_generation";
        case MUTATION_DISPATCH_STALE_SEQUENCE:
            return "stale_sequence";
        case MUTATION_DISPATCH_GENERATION_LOST:
            return "generation_lost";
        case MUTATION_DISPATCH_RUNTIME_STOPPED:
            return "runtime_stopped";
        case MUTATION_DISPATCH_UNSUPPORTED_OPERATION:
            return "unsupported_operation";
        case MUTATION_DISPATCH_TARGET_NOT_FOUND:
            return "target_not_found";
        case MUTATION_DISPATCH_NOT_WRITABLE:
            return "not_writable";
        case MUTATION_DISPATCH_OWNERSHIP_CONFLICT:
            return "ownership_conflict";
        case MUTATION_DISPATCH_NATIVE_REJECTED:
            return "native_rejected";
    }
    return "internal_error";
}


static gboolean set_owned(PyObject *dict, const char *key, PyObject *value) {
    if (!value) return FALSE;
    const int result = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    return result == 0;
}


static PyObject *call_to_payload(MutationDispatchCall *call) {
    PyObject *payload = PyDict_New();
    if (!payload ||
        !set_owned(payload, "payload_version", PyLong_FromLong(
            NATIVE_MUTATION_DISPATCH_PAYLOAD_VERSION)) ||
        !set_owned(payload, "request_id", PyUnicode_FromString(call->request_id)) ||
        !set_owned(payload, "operation", PyUnicode_FromString(call->operation)) ||
        !set_owned(payload, "dispatch_order", PyLong_FromUnsignedLongLong(
            call->dispatch_order)) ||
        !set_owned(payload, "disposition", PyUnicode_FromString(
            disposition(call->result))) ||
        !set_owned(payload, "expected_generation", PyLong_FromUnsignedLongLong(
            call->expected_generation)) ||
        !set_owned(payload, "expected_sequence", call->has_expected_sequence
            ? PyLong_FromUnsignedLongLong(call->expected_sequence)
            : Py_NewRef(Py_None)) ||
        !set_owned(payload, "observed_generation", PyLong_FromUnsignedLongLong(
            call->observed_generation)) ||
        !set_owned(payload, "observed_sequence", PyLong_FromUnsignedLongLong(
            call->observed_sequence)) ||
        !set_owned(payload, "failure_code", failure_code(call->result)
            ? PyUnicode_FromString(failure_code(call->result))
            : Py_NewRef(Py_None))) {
        Py_XDECREF(payload);
        return NULL;
    }
    return payload;
}


static gboolean parse_identifier(
    PyObject *request, const char *name, guint64 *result, gboolean optional)
{
    PyObject *value = PyDict_GetItemString(request, name);
    if (optional && (!value || value == Py_None)) return TRUE;
    if (!value || PyBool_Check(value) || !PyLong_Check(value)) {
        PyErr_Format(PyExc_TypeError, "%s must be a non-negative integer%s",
            name, optional ? " or None" : "");
        return FALSE;
    }
    *result = PyLong_AsUnsignedLongLong(value);
    return !PyErr_Occurred();
}


static gboolean parse_string(
    PyObject *request, const char *name, gchar **result)
{
    PyObject *value = PyDict_GetItemString(request, name);
    if (!value || !PyUnicode_Check(value)) {
        PyErr_Format(PyExc_TypeError, "%s must be a string", name);
        return FALSE;
    }
    const gchar *text = PyUnicode_AsUTF8(value);
    if (!text) return FALSE;
    if (!*text) {
        PyErr_Format(PyExc_ValueError, "%s must not be empty", name);
        return FALSE;
    }
    *result = g_strdup(text);
    if (!*result) {
        PyErr_NoMemory();
        return FALSE;
    }
    return TRUE;
}


static gboolean parse_optional_string(
    PyObject *request, const char *name, gchar **result)
{
    PyObject *value = PyDict_GetItemString(request, name);
    if (!value || value == Py_None) return TRUE;
    if (!PyUnicode_Check(value)) {
        PyErr_Format(PyExc_TypeError, "%s must be a string or None", name);
        return FALSE;
    }
    const gchar *text = PyUnicode_AsUTF8(value);
    if (!text) return FALSE;
    if (!*text) {
        PyErr_Format(PyExc_ValueError, "%s must not be empty", name);
        return FALSE;
    }
    *result = g_strdup(text);
    if (!*result) {
        PyErr_NoMemory();
        return FALSE;
    }
    return TRUE;
}


static gboolean parse_set_parameter(MutationDispatchCall *call, PyObject *request) {
    PyObject *target = PyDict_GetItemString(request, "target");
    PyObject *payload = PyDict_GetItemString(request, "payload");
    if (!target || !PyDict_Check(target) || !payload || !PyDict_Check(payload)) {
        PyErr_SetString(PyExc_TypeError, "set_parameter target and payload must be dictionaries");
        return FALSE;
    }
    if (!parse_string(target, "object_kind", &call->target_kind)) return FALSE;
    guint64 target_id = 0;
    if (!parse_identifier(target, "object_id", &target_id, FALSE)) return FALSE;
    if (target_id > G_MAXUINT32) {
        PyErr_SetString(PyExc_ValueError, "target object_id exceeds PipeWire ID range");
        return FALSE;
    }
    call->target_id = (guint32) target_id;

    PyObject *selector = PyDict_GetItemString(target, "selector");
    if (!selector || !PyDict_Check(selector) ||
        !parse_string(selector, "parameter_id", &call->parameter_id)) {
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_TypeError, "target selector must contain parameter_id");
        }
        return FALSE;
    }

    PyObject *flags = PyDict_GetItemString(payload, "flags");
    if (!flags || PyBool_Check(flags) || !PyLong_Check(flags)) {
        PyErr_SetString(PyExc_TypeError, "payload flags must be a non-negative integer");
        return FALSE;
    }
    const unsigned long parsed_flags = PyLong_AsUnsignedLong(flags);
    if (PyErr_Occurred() || parsed_flags > G_MAXUINT32) {
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_ValueError, "payload flags exceed uint32 range");
        }
        return FALSE;
    }
    call->flags = (guint32) parsed_flags;

    PyObject *base64_value = PyDict_GetItemString(payload, "pod_base64");
    if (!base64_value || !PyUnicode_Check(base64_value)) {
        PyErr_SetString(PyExc_TypeError, "payload pod_base64 must be a string");
        return FALSE;
    }
    const gchar *base64 = PyUnicode_AsUTF8(base64_value);
    if (!base64) return FALSE;
    gsize decoded_size = 0;
    guchar *decoded = g_base64_decode(base64, &decoded_size);
    if (!decoded || decoded_size < sizeof(struct spa_pod)) {
        g_free(decoded);
        PyErr_SetString(PyExc_ValueError, "payload pod_base64 is not a valid SPA pod");
        return FALSE;
    }
    struct spa_pod header;
    memcpy(&header, decoded, sizeof(header));
    if ((gsize) header.size + sizeof(header) > decoded_size) {
        g_free(decoded);
        PyErr_SetString(PyExc_ValueError, "payload SPA pod size exceeds decoded data");
        return FALSE;
    }
    call->pod_data = g_bytes_new_take(decoded, decoded_size);
    return TRUE;
}


static gboolean parse_set_node_mixer(
    MutationDispatchCall *call, PyObject *request)
{
    PyObject *target = PyDict_GetItemString(request, "target");
    PyObject *payload = PyDict_GetItemString(request, "payload");
    if (!target || !PyDict_Check(target) || !payload || !PyDict_Check(payload)) {
        PyErr_SetString(
            PyExc_TypeError,
            "set_node_mixer target and payload must be dictionaries");
        return FALSE;
    }
    if (!parse_string(target, "object_kind", &call->target_kind)) return FALSE;
    if (!g_str_equal(call->target_kind, "node")) {
        PyErr_SetString(PyExc_ValueError, "set_node_mixer target must be a node");
        return FALSE;
    }
    guint64 target_id = 0;
    if (!parse_identifier(target, "object_id", &target_id, FALSE)) return FALSE;
    if (target_id > G_MAXUINT32) {
        PyErr_SetString(PyExc_ValueError, "target object_id exceeds PipeWire ID range");
        return FALSE;
    }
    call->target_id = (guint32) target_id;

    PyObject *selector = PyDict_GetItemString(target, "selector");
    PyObject *control = selector && PyDict_Check(selector)
        ? PyDict_GetItemString(selector, "control") : NULL;
    if (!control || !PyUnicode_Check(control) ||
        g_strcmp0(PyUnicode_AsUTF8(control), "mixer") != 0) {
        PyErr_SetString(
            PyExc_ValueError,
            "set_node_mixer target selector control must be mixer");
        return FALSE;
    }

    PyObject *volume = PyDict_GetItemString(payload, "volume");
    if (volume && volume != Py_None) {
        if (PyBool_Check(volume)) {
            PyErr_SetString(PyExc_TypeError, "mixer volume must be a number");
            return FALSE;
        }
        call->mixer_volume = PyFloat_AsDouble(volume);
        if (PyErr_Occurred()) return FALSE;
        if (!isfinite(call->mixer_volume) || call->mixer_volume < 0.0) {
            PyErr_SetString(
                PyExc_ValueError,
                "mixer volume must be finite and non-negative");
            return FALSE;
        }
        call->has_mixer_volume = TRUE;
    }

    PyObject *mute = PyDict_GetItemString(payload, "mute");
    if (mute && mute != Py_None) {
        if (!PyBool_Check(mute)) {
            PyErr_SetString(PyExc_TypeError, "mixer mute must be a boolean");
            return FALSE;
        }
        call->mixer_mute = mute == Py_True;
        call->has_mixer_mute = TRUE;
    }
    if (!call->has_mixer_volume && !call->has_mixer_mute) {
        PyErr_SetString(
            PyExc_ValueError,
            "set_node_mixer payload must contain volume or mute");
        return FALSE;
    }
    return TRUE;
}


static gboolean parse_metadata_mutation(
    MutationDispatchCall *call, PyObject *request, gboolean clear)
{
    PyObject *target = PyDict_GetItemString(request, "target");
    PyObject *payload = PyDict_GetItemString(request, "payload");
    if (!target || !PyDict_Check(target) || !payload || !PyDict_Check(payload)) {
        PyErr_SetString(
            PyExc_TypeError,
            "metadata mutation target and payload must be dictionaries");
        return FALSE;
    }
    if (!parse_string(target, "object_kind", &call->target_kind)) return FALSE;
    if (!g_str_equal(call->target_kind, "metadata")) {
        PyErr_SetString(
            PyExc_ValueError, "metadata mutation target must be metadata");
        return FALSE;
    }
    guint64 target_id = 0;
    if (!parse_identifier(target, "object_id", &target_id, FALSE)) return FALSE;
    if (target_id > G_MAXUINT32) {
        PyErr_SetString(
            PyExc_ValueError, "target object_id exceeds PipeWire ID range");
        return FALSE;
    }
    call->target_id = (guint32) target_id;

    PyObject *selector = PyDict_GetItemString(target, "selector");
    if (!selector || !PyDict_Check(selector)) {
        PyErr_SetString(
            PyExc_TypeError,
            "metadata target selector must contain subject and key");
        return FALSE;
    }
    guint64 subject = 0;
    if (!parse_identifier(selector, "subject", &subject, FALSE)) return FALSE;
    if (subject > G_MAXUINT32) {
        PyErr_SetString(
            PyExc_ValueError, "metadata subject exceeds PipeWire ID range");
        return FALSE;
    }
    call->metadata_subject = (guint32) subject;
    if (!parse_string(selector, "key", &call->metadata_key)) return FALSE;

    if (!clear) {
        if (!parse_optional_string(payload, "type_name", &call->metadata_type)) {
            return FALSE;
        }
        PyObject *value = PyDict_GetItemString(payload, "value");
        if (!value || !PyUnicode_Check(value)) {
            PyErr_SetString(PyExc_TypeError, "payload value must be a string");
            return FALSE;
        }
        const gchar *text = PyUnicode_AsUTF8(value);
        if (!text) return FALSE;
        call->metadata_value = g_strdup(text);
        if (!call->metadata_value) {
            PyErr_NoMemory();
            return FALSE;
        }
    }
    return TRUE;
}


static gboolean parse_pipewire_id(
    PyObject *mapping, const char *name, guint32 *result)
{
    guint64 value = 0;
    if (!parse_identifier(mapping, name, &value, FALSE)) return FALSE;
    if (value > G_MAXUINT32) {
        PyErr_Format(PyExc_ValueError, "%s exceeds PipeWire ID range", name);
        return FALSE;
    }
    *result = (guint32) value;
    return TRUE;
}


static gboolean reserved_link_property(const gchar *key) {
    return g_str_equal(key, PW_KEY_LINK_OUTPUT_NODE) ||
        g_str_equal(key, PW_KEY_LINK_OUTPUT_PORT) ||
        g_str_equal(key, PW_KEY_LINK_INPUT_NODE) ||
        g_str_equal(key, PW_KEY_LINK_INPUT_PORT) ||
        g_str_equal(key, PW_KEY_OBJECT_LINGER) ||
        g_str_equal(key, "open-cinema.owner") ||
        g_str_equal(key, "open-cinema.desired-id");
}


static gboolean parse_link_properties(
    MutationDispatchCall *call, PyObject *payload)
{
    PyObject *properties = PyDict_GetItemString(payload, "properties");
    if (!properties || !PyDict_Check(properties)) {
        PyErr_SetString(PyExc_TypeError, "link payload properties must be a dictionary");
        return FALSE;
    }
    call->link_properties = wp_properties_new_empty();
    if (!call->link_properties) {
        PyErr_NoMemory();
        return FALSE;
    }
    Py_ssize_t position = 0;
    PyObject *key = NULL;
    PyObject *value = NULL;
    while (PyDict_Next(properties, &position, &key, &value)) {
        if (!PyUnicode_Check(key) || !PyUnicode_Check(value)) {
            PyErr_SetString(
                PyExc_TypeError, "link property names and values must be strings");
            return FALSE;
        }
        const gchar *key_text = PyUnicode_AsUTF8(key);
        const gchar *value_text = PyUnicode_AsUTF8(value);
        if (!key_text || !value_text) return FALSE;
        if (!*key_text) {
            PyErr_SetString(PyExc_ValueError, "link property names must not be empty");
            return FALSE;
        }
        if (reserved_link_property(key_text)) {
            PyErr_Format(
                PyExc_ValueError, "link property %s is managed by the dispatcher", key_text);
            return FALSE;
        }
        wp_properties_set(call->link_properties, key_text, value_text);
    }
    return TRUE;
}


static gboolean parse_link_identity(
    MutationDispatchCall *call, PyObject *selector)
{
    return parse_string(selector, "owner", &call->link_owner) &&
        parse_string(selector, "desired_id", &call->link_desired_id);
}


static gboolean parse_create_link(MutationDispatchCall *call, PyObject *request) {
    PyObject *target = PyDict_GetItemString(request, "target");
    PyObject *payload = PyDict_GetItemString(request, "payload");
    if (!target || !PyDict_Check(target) || !payload || !PyDict_Check(payload)) {
        PyErr_SetString(
            PyExc_TypeError, "create_link target and payload must be dictionaries");
        return FALSE;
    }
    if (!parse_string(target, "object_kind", &call->target_kind)) return FALSE;
    if (!g_str_equal(call->target_kind, "link")) {
        PyErr_SetString(PyExc_ValueError, "create_link target must be a link");
        return FALSE;
    }
    PyObject *selector = PyDict_GetItemString(target, "selector");
    if (!selector || !PyDict_Check(selector)) {
        PyErr_SetString(PyExc_TypeError, "create_link target selector is required");
        return FALSE;
    }
    return parse_link_identity(call, selector) &&
        parse_pipewire_id(selector, "output_node_id", &call->output_node_id) &&
        parse_pipewire_id(selector, "output_port_id", &call->output_port_id) &&
        parse_pipewire_id(selector, "input_node_id", &call->input_node_id) &&
        parse_pipewire_id(selector, "input_port_id", &call->input_port_id) &&
        parse_link_properties(call, payload);
}


static gboolean parse_remove_link(MutationDispatchCall *call, PyObject *request) {
    PyObject *target = PyDict_GetItemString(request, "target");
    PyObject *payload = PyDict_GetItemString(request, "payload");
    if (!target || !PyDict_Check(target) || !payload || !PyDict_Check(payload)) {
        PyErr_SetString(
            PyExc_TypeError, "remove_link target and payload must be dictionaries");
        return FALSE;
    }
    if (!parse_string(target, "object_kind", &call->target_kind)) return FALSE;
    if (!g_str_equal(call->target_kind, "link")) {
        PyErr_SetString(PyExc_ValueError, "remove_link target must be a link");
        return FALSE;
    }
    PyObject *selector = PyDict_GetItemString(target, "selector");
    if (!selector || !PyDict_Check(selector)) {
        PyErr_SetString(PyExc_TypeError, "remove_link target selector is required");
        return FALSE;
    }
    return parse_link_identity(call, selector) &&
        parse_pipewire_id(payload, "link_id", &call->link_id);
}


static void clear_call(MutationDispatchCall *call) {
    g_free(call->request_id);
    g_free(call->operation);
    g_free(call->target_kind);
    g_free(call->parameter_id);
    g_free(call->metadata_key);
    g_free(call->metadata_type);
    g_free(call->metadata_value);
    g_free(call->link_owner);
    g_free(call->link_desired_id);
    if (call->link_properties) wp_properties_unref(call->link_properties);
    if (call->pod_data) g_bytes_unref(call->pod_data);
    g_mutex_clear(&call->lock);
    g_cond_clear(&call->cond);
}


PyObject *WPConnection_dispatch_runtime_mutation_payload(
    WPConnection *self, PyObject *request)
{
    if (!PyDict_Check(request)) {
        PyErr_SetString(PyExc_TypeError, "request must be a mutation request dictionary");
        return NULL;
    }

    MutationDispatchCall call = {0};
    g_mutex_init(&call.lock);
    g_cond_init(&call.cond);
    if (!parse_string(request, "request_id", &call.request_id) ||
        !parse_string(request, "operation", &call.operation) ||
        !parse_identifier(
            request, "expected_generation", &call.expected_generation, FALSE)) {
        clear_call(&call);
        return NULL;
    }
    if ((g_str_equal(call.operation, "set_parameter") ||
         g_str_equal(call.operation, "select_profile") ||
         g_str_equal(call.operation, "select_route")) &&
        !parse_set_parameter(&call, request)) {
        clear_call(&call);
        return NULL;
    }
    if (g_str_equal(call.operation, "set_node_mixer") &&
        !parse_set_node_mixer(&call, request)) {
        clear_call(&call);
        return NULL;
    }
    if (g_str_equal(call.operation, "set_metadata") &&
        !parse_metadata_mutation(&call, request, FALSE)) {
        clear_call(&call);
        return NULL;
    }
    if (g_str_equal(call.operation, "clear_metadata") &&
        !parse_metadata_mutation(&call, request, TRUE)) {
        clear_call(&call);
        return NULL;
    }
    if (g_str_equal(call.operation, "create_link") &&
        !parse_create_link(&call, request)) {
        clear_call(&call);
        return NULL;
    }
    if (g_str_equal(call.operation, "remove_link") &&
        !parse_remove_link(&call, request)) {
        clear_call(&call);
        return NULL;
    }
    PyObject *expected_sequence = PyDict_GetItemString(request, "expected_sequence");
    call.has_expected_sequence = expected_sequence && expected_sequence != Py_None;
    if (!parse_identifier(
            request, "expected_sequence", &call.expected_sequence, TRUE)) {
        clear_call(&call);
        return NULL;
    }

    g_mutex_lock(&self->lock);
    call.enqueued_generation = self->generation;
    call.observed_generation = self->generation;
    call.observed_sequence = 0;
    if (self->stop_requested || !self->thread || !self->ctx) {
        call.result = MUTATION_DISPATCH_RUNTIME_STOPPED;
        call.completed = TRUE;
        g_mutex_unlock(&self->lock);
    } else if (call.expected_generation != self->generation) {
        call.result = MUTATION_DISPATCH_STALE_GENERATION;
        call.completed = TRUE;
        g_mutex_unlock(&self->lock);
    } else {
        g_mutex_lock(&self->mutation_lock);
        call.dispatch_order = ++self->mutation_dispatch_order;
        g_queue_push_tail(self->mutation_queue, &call);
        schedule_dispatch_locked(self);
        g_mutex_unlock(&self->mutation_lock);
        g_mutex_unlock(&self->lock);

        Py_BEGIN_ALLOW_THREADS
        g_mutex_lock(&call.lock);
        while (!call.completed) g_cond_wait(&call.cond, &call.lock);
        g_mutex_unlock(&call.lock);
        Py_END_ALLOW_THREADS
    }

    PyObject *result = call_to_payload(&call);
    clear_call(&call);
    return result;
}


void wp_connection_mutations_cancel_pending(
    WPConnection *conn, WpMutationCancelReason reason)
{
    if (!conn || !conn->mutation_queue) return;
    g_mutex_lock(&conn->lock);
    const guint64 generation = conn->generation;
    g_mutex_lock(&conn->mutation_lock);
    MutationDispatchCall *call = NULL;
    while ((call = g_queue_pop_head(conn->mutation_queue))) {
        complete_call(
            call,
            reason == WP_MUTATION_CANCEL_GENERATION_LOST
                ? MUTATION_DISPATCH_GENERATION_LOST
                : MUTATION_DISPATCH_RUNTIME_STOPPED,
            generation,
            0);
    }
    g_mutex_unlock(&conn->mutation_lock);
    g_mutex_unlock(&conn->lock);
}


void wp_connection_mutations_clear(WPConnection *conn) {
    if (!conn) return;
    wp_connection_mutations_cancel_pending(
        conn, WP_MUTATION_CANCEL_RUNTIME_STOPPED);
    if (conn->mutation_queue) {
        g_queue_free(conn->mutation_queue);
        conn->mutation_queue = NULL;
    }
}
