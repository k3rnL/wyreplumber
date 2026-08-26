#include "wp_connection.h"
#include "../wp_compat.h"

#include <pipewire/keys.h>
#include <pipewire/version.h>
#include <spa/pod/pod.h>
#include <string.h>


typedef struct {
    WPConnection *conn;
    PyObject *result;
    GError *error;
} CaptureRuntimeData;


static void set_capture_error(GError **error, const char *message) {
    if (!*error) {
        *error = g_error_new_literal(G_IO_ERROR, G_IO_ERROR_FAILED, message);
    }
    PyErr_Clear();
}


static gboolean dict_set_owned(
    PyObject *dict,
    const char *key,
    PyObject *value,
    GError **error)
{
    if (!value) {
        set_capture_error(error, "Failed to allocate runtime payload value");
        return FALSE;
    }
    const int result = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    if (result < 0) {
        set_capture_error(error, "Failed to append runtime payload field");
        return FALSE;
    }
    return TRUE;
}


static gboolean dict_move(
    PyObject *dict,
    const char *key,
    PyObject **value,
    GError **error)
{
    PyObject *owned = *value;
    *value = NULL;
    return dict_set_owned(dict, key, owned, error);
}


static gboolean list_append(PyObject *list, PyObject *value, GError **error) {
    if (PyList_Append(list, value) < 0) {
        set_capture_error(error, "Failed to append runtime payload item");
        return FALSE;
    }
    return TRUE;
}


static PyObject *copy_properties(WpProperties *properties, GError **error) {
    PyObject *result = PyDict_New();
    if (!result) {
        set_capture_error(error, "Failed to allocate properties payload");
        return NULL;
    }
    if (!properties) return result;

    g_autoptr(WpIterator) iterator = wp_properties_new_iterator(properties);
    g_auto(GValue) item = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &item)) {
        WpPropertiesItem *property = g_value_get_boxed(&item);
        const char *key = property ? wp_properties_item_get_key(property) : NULL;
        const char *value = property ? wp_properties_item_get_value(property) : NULL;
        if (key && value) {
            PyObject *py_value = PyUnicode_FromString(value);
            if (!py_value || PyDict_SetItemString(result, key, py_value) < 0) {
                Py_XDECREF(py_value);
                g_value_unset(&item);
                Py_DECREF(result);
                set_capture_error(error, "Failed to copy PipeWire properties");
                return NULL;
            }
            Py_DECREF(py_value);
        }
        g_value_unset(&item);
    }
    return result;
}


static gboolean merge_properties(
    PyObject *result, WpProperties *properties, GError **error)
{
    if (!properties) return TRUE;
    g_autoptr(WpIterator) iterator = wp_properties_new_iterator(properties);
    g_auto(GValue) item = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &item)) {
        WpPropertiesItem *property = g_value_get_boxed(&item);
        const char *key = property ? wp_properties_item_get_key(property) : NULL;
        const char *value = property ? wp_properties_item_get_value(property) : NULL;
        if (key && value) {
            PyObject *py_value = PyUnicode_FromString(value);
            if (!py_value || PyDict_SetItemString(result, key, py_value) < 0) {
                Py_XDECREF(py_value);
                g_value_unset(&item);
                set_capture_error(error, "Failed to merge PipeWire properties");
                return FALSE;
            }
            Py_DECREF(py_value);
        }
        g_value_unset(&item);
    }
    return TRUE;
}


static PyObject *copy_raw_pods(WpIterator *iterator, GError **error) {
    PyObject *values = PyList_New(0);
    if (!values) {
        set_capture_error(error, "Failed to allocate parameter values");
        return NULL;
    }
    if (!iterator) return values;

    g_auto(GValue) value = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &value)) {
        WpSpaPod *pod = g_value_get_boxed(&value);
        const struct spa_pod *spa_pod = pod ? wp_spa_pod_get_spa_pod(pod) : NULL;
        if (!spa_pod) {
            g_value_unset(&value);
            continue;
        }

        const gsize total_size = sizeof(struct spa_pod) + spa_pod->size;
        PyObject *bytes = PyBytes_FromStringAndSize(
            (const char *) spa_pod, (Py_ssize_t) total_size);
        if (!bytes) {
            g_value_unset(&value);
            Py_DECREF(values);
            set_capture_error(error, "Failed to copy SPA pod bytes");
            return NULL;
        }
        PyObject *record = Py_BuildValue(
            "{sI,sI,sO}",
            "type", spa_pod->type,
            "size", spa_pod->size,
            "data", bytes);
        Py_DECREF(bytes);
        if (!record || !list_append(values, record, error)) {
            Py_XDECREF(record);
            g_value_unset(&value);
            Py_DECREF(values);
            return NULL;
        }
        Py_DECREF(record);
        g_value_unset(&value);
    }
    return values;
}


static gboolean copy_parameters(
    WpPipewireObject *object,
    const char *owner_type,
    guint32 owner_id,
    PyObject *parameter_ids,
    PyObject *parameters,
    PyObject *profiles,
    PyObject *routes,
    GError **error)
{
    g_autoptr(GVariant) info = wp_pipewire_object_get_param_info(object);
    if (!info) return TRUE;
    if (!g_variant_is_of_type(info, G_VARIANT_TYPE("a{ss}"))) {
        set_capture_error(error, "Unexpected WirePlumber parameter info type");
        return FALSE;
    }

    GVariantIter iterator;
    const gchar *parameter_id = NULL;
    const gchar *permissions = NULL;
    g_variant_iter_init(&iterator, info);
    while (g_variant_iter_loop(&iterator, "{&s&s}", &parameter_id, &permissions)) {
        PyObject *py_id = PyUnicode_FromString(parameter_id ? parameter_id : "");
        if (!py_id || !list_append(parameter_ids, py_id, error)) {
            Py_XDECREF(py_id);
            return FALSE;
        }
        Py_DECREF(py_id);

        gboolean complete = TRUE;
        g_autoptr(WpIterator) values_iterator = NULL;
        if (permissions && strchr(permissions, 'r')) {
            values_iterator = wp_pipewire_object_enum_params_sync(object, parameter_id, NULL);
            if (!values_iterator) complete = FALSE;
        }
        PyObject *values = copy_raw_pods(values_iterator, error);
        if (!values) return FALSE;

        PyObject *record = PyDict_New();
        if (!record ||
            !dict_set_owned(record, "owner_type", PyUnicode_FromString(owner_type), error) ||
            !dict_set_owned(record, "owner_id", PyLong_FromUnsignedLong(owner_id), error) ||
            !dict_set_owned(record, "id", PyUnicode_FromString(parameter_id ? parameter_id : ""), error) ||
            !dict_set_owned(record, "permissions", PyUnicode_FromString(permissions ? permissions : ""), error) ||
            !dict_set_owned(record, "complete", PyBool_FromLong(complete), error)) {
            Py_XDECREF(record);
            Py_DECREF(values);
            return FALSE;
        }
        if (!dict_move(record, "values", &values, error)) {
            Py_DECREF(record);
            return FALSE;
        }

        if (!list_append(parameters, record, error)) {
            Py_DECREF(record);
            return FALSE;
        }
        if (g_strcmp0(parameter_id, "Profile") == 0 ||
            g_strcmp0(parameter_id, "EnumProfile") == 0) {
            if (!list_append(profiles, record, error)) {
                Py_DECREF(record);
                return FALSE;
            }
        }
        if (g_strcmp0(parameter_id, "Route") == 0 ||
            g_strcmp0(parameter_id, "EnumRoute") == 0) {
            if (!list_append(routes, record, error)) {
                Py_DECREF(record);
                return FALSE;
            }
        }
        Py_DECREF(record);
    }
    return TRUE;
}


static gboolean object_has_snapshot_features(WpPipewireObject *object) {
    const WpObjectFeatures features = wp_object_get_active_features(WP_OBJECT(object));
    return (features & WP_PROXY_FEATURE_BOUND) &&
        (features & WP_PIPEWIRE_OBJECT_FEATURE_INFO);
}


static PyObject *copy_pipewire_object(
    WpPipewireObject *object,
    const char *owner_type,
    PyObject *parameters,
    PyObject *profiles,
    PyObject *routes,
    GError **error)
{
    const guint32 id = wp_proxy_get_bound_id(WP_PROXY(object));
    PyObject *record = PyDict_New();
    PyObject *parameter_ids = PyList_New(0);
    if (!record || !parameter_ids ||
        !dict_set_owned(record, "id", PyLong_FromUnsignedLong(id), error) ||
        !dict_set_owned(
            record,
            "properties",
            copy_properties(wp_pipewire_object_get_properties(object), error),
            error)) {
        Py_XDECREF(record);
        Py_XDECREF(parameter_ids);
        return NULL;
    }
    if (!copy_parameters(
            object, owner_type, id, parameter_ids,
            parameters, profiles, routes, error)) {
        Py_DECREF(record);
        Py_DECREF(parameter_ids);
        return NULL;
    }
    if (!dict_move(record, "parameter_ids", &parameter_ids, error)) {
        Py_DECREF(record);
        return NULL;
    }
    return record;
}


static gboolean append_device(
    WpDevice *device,
    PyObject *devices,
    PyObject *parameters,
    PyObject *profiles,
    PyObject *routes,
    GError **error)
{
    if (!object_has_snapshot_features(WP_PIPEWIRE_OBJECT(device))) return TRUE;
    PyObject *record = copy_pipewire_object(
        WP_PIPEWIRE_OBJECT(device), "device", parameters, profiles, routes, error);
    if (!record) return FALSE;
    const gboolean success = list_append(devices, record, error);
    Py_DECREF(record);
    return success;
}


static gboolean append_node(
    WpNode *node,
    PyObject *nodes,
    PyObject *parameters,
    PyObject *profiles,
    PyObject *routes,
    GError **error)
{
    if (!object_has_snapshot_features(WP_PIPEWIRE_OBJECT(node))) return TRUE;
    PyObject *record = copy_pipewire_object(
        WP_PIPEWIRE_OBJECT(node), "node", parameters, profiles, routes, error);
    if (!record) return FALSE;

    const gchar *error_message = NULL;
    guint max_input_ports = 0;
    guint max_output_ports = 0;
    const WpNodeState state = wp_node_get_state(node, &error_message);
    const guint input_ports = wp_node_get_n_input_ports(node, &max_input_ports);
    const guint output_ports = wp_node_get_n_output_ports(node, &max_output_ports);
    if (!dict_set_owned(record, "state", PyLong_FromLong(state), error) ||
        !dict_set_owned(record, "error", error_message ? PyUnicode_FromString(error_message) : Py_NewRef(Py_None), error) ||
        !dict_set_owned(record, "n_input_ports", PyLong_FromUnsignedLong(input_ports), error) ||
        !dict_set_owned(record, "max_input_ports", PyLong_FromUnsignedLong(max_input_ports), error) ||
        !dict_set_owned(record, "n_output_ports", PyLong_FromUnsignedLong(output_ports), error) ||
        !dict_set_owned(record, "max_output_ports", PyLong_FromUnsignedLong(max_output_ports), error)) {
        Py_DECREF(record);
        return FALSE;
    }
    const gboolean success = list_append(nodes, record, error);
    Py_DECREF(record);
    return success;
}


static gboolean append_port(
    WpPort *port,
    PyObject *ports,
    PyObject *parameters,
    PyObject *profiles,
    PyObject *routes,
    GError **error)
{
    if (!object_has_snapshot_features(WP_PIPEWIRE_OBJECT(port))) return TRUE;
    PyObject *record = copy_pipewire_object(
        WP_PIPEWIRE_OBJECT(port), "port", parameters, profiles, routes, error);
    if (!record) return FALSE;
    if (!dict_set_owned(record, "direction", PyLong_FromLong(wp_port_get_direction(port)), error)) {
        Py_DECREF(record);
        return FALSE;
    }
    const gboolean success = list_append(ports, record, error);
    Py_DECREF(record);
    return success;
}


static gboolean append_link(
    WPConnection *conn,
    WpLink *link,
    PyObject *links,
    PyObject *parameters,
    PyObject *profiles,
    PyObject *routes,
    GError **error)
{
    if (!object_has_snapshot_features(WP_PIPEWIRE_OBJECT(link))) return TRUE;
    PyObject *record = copy_pipewire_object(
        WP_PIPEWIRE_OBJECT(link), "link", parameters, profiles, routes, error);
    if (!record) return FALSE;
    PyObject *properties = PyDict_GetItemString(record, "properties");
    g_autoptr(WpProperties) global_properties =
        wp_global_proxy_get_global_properties(WP_GLOBAL_PROXY(link));
    if (!properties || !PyDict_Check(properties) ||
        !merge_properties(properties, global_properties, error)) {
        Py_DECREF(record);
        return FALSE;
    }

    guint32 output_node = 0;
    guint32 output_port = 0;
    guint32 input_node = 0;
    guint32 input_port = 0;
    const gchar *error_message = NULL;
    wp_link_get_linked_object_ids(
        link, &output_node, &output_port, &input_node, &input_port);
    const WpLinkState state = wp_link_get_state(link, &error_message);
    const WpManagedLinkSpec *managed =
        wp_connection_managed_link_lookup_endpoints(
            conn, output_node, output_port, input_node, input_port);
    if (managed &&
        (!dict_set_owned(
             properties,
             "open-cinema.owner",
             PyUnicode_FromString(managed->owner),
             error) ||
         !dict_set_owned(
             properties,
             "open-cinema.desired-id",
             PyUnicode_FromString(managed->desired_id),
             error))) {
        Py_DECREF(record);
        return FALSE;
    }
    if (!dict_set_owned(record, "output_node_id", PyLong_FromUnsignedLong(output_node), error) ||
        !dict_set_owned(record, "output_port_id", PyLong_FromUnsignedLong(output_port), error) ||
        !dict_set_owned(record, "input_node_id", PyLong_FromUnsignedLong(input_node), error) ||
        !dict_set_owned(record, "input_port_id", PyLong_FromUnsignedLong(input_port), error) ||
        !dict_set_owned(record, "state", PyLong_FromLong(state), error) ||
        !dict_set_owned(record, "error", error_message ? PyUnicode_FromString(error_message) : Py_NewRef(Py_None), error)) {
        Py_DECREF(record);
        return FALSE;
    }
    const gboolean success = list_append(links, record, error);
    Py_DECREF(record);
    return success;
}


static gboolean append_metadata(
    WpMetadata *metadata,
    PyObject *metadata_list,
    PyObject *defaults,
    GError **error)
{
    const WpObjectFeatures features = wp_object_get_active_features(WP_OBJECT(metadata));
    if (!(features & WP_PROXY_FEATURE_BOUND) || !(features & WP_METADATA_FEATURE_DATA)) {
        return TRUE;
    }

    const guint32 id = wp_proxy_get_bound_id(WP_PROXY(metadata));
    WpProperties *properties = wp_global_proxy_get_global_properties(WP_GLOBAL_PROXY(metadata));
    const gchar *metadata_name = properties ? wp_properties_get(properties, "metadata.name") : NULL;
    PyObject *entries = PyList_New(0);
    PyObject *record = PyDict_New();
    if (!entries || !record ||
        !dict_set_owned(record, "id", PyLong_FromUnsignedLong(id), error) ||
        !dict_set_owned(record, "name", metadata_name ? PyUnicode_FromString(metadata_name) : Py_NewRef(Py_None), error) ||
        !dict_set_owned(record, "properties", copy_properties(properties, error), error)) {
        Py_XDECREF(entries);
        Py_XDECREF(record);
        return FALSE;
    }

    g_autoptr(WpIterator) iterator = wp_metadata_new_iterator(metadata, -1);
    g_auto(GValue) value = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &value)) {
        guint32 subject = 0;
        const gchar *key = NULL;
        const gchar *type = NULL;
        const gchar *item_value = NULL;
        if (!wyreplumber_metadata_item_extract(
                &value, &subject, &key, &type, &item_value)) {
            g_value_unset(&value);
            continue;
        }

        PyObject *entry = PyDict_New();
        if (!entry ||
            !dict_set_owned(entry, "subject", PyLong_FromUnsignedLong(subject), error) ||
            !dict_set_owned(entry, "key", PyUnicode_FromString(key ? key : ""), error) ||
            !dict_set_owned(entry, "type", type ? PyUnicode_FromString(type) : Py_NewRef(Py_None), error) ||
            !dict_set_owned(entry, "value", item_value ? PyUnicode_FromString(item_value) : Py_NewRef(Py_None), error) ||
            !list_append(entries, entry, error)) {
            Py_XDECREF(entry);
            g_value_unset(&value);
            Py_DECREF(entries);
            Py_DECREF(record);
            return FALSE;
        }

        if (key && g_str_has_prefix(key, "default.")) {
            PyObject *default_entry = PyDict_Copy(entry);
            if (!default_entry ||
                !dict_set_owned(default_entry, "metadata_id", PyLong_FromUnsignedLong(id), error) ||
                !dict_set_owned(default_entry, "metadata_name", metadata_name ? PyUnicode_FromString(metadata_name) : Py_NewRef(Py_None), error) ||
                !list_append(defaults, default_entry, error)) {
                Py_XDECREF(default_entry);
                Py_DECREF(entry);
                g_value_unset(&value);
                Py_DECREF(entries);
                Py_DECREF(record);
                return FALSE;
            }
            Py_DECREF(default_entry);
        }
        Py_DECREF(entry);
        g_value_unset(&value);
    }

    if (!dict_move(record, "entries", &entries, error)) {
        Py_DECREF(record);
        return FALSE;
    }
    const gboolean success = list_append(metadata_list, record, error);
    Py_DECREF(record);
    return success;
}


static PyObject *build_health(WPConnection *conn, GError **error) {
    PyObject *details = PyDict_New();
    PyObject *health = PyDict_New();
    const gchar *remote_version = wp_core_get_remote_version(conn->core);
    if (!details || !health ||
        !dict_set_owned(details, "wireplumber_library_version", PyUnicode_FromString(wp_get_library_version()), error) ||
        !dict_set_owned(details, "wireplumber_api_version", PyUnicode_FromString(wp_get_library_api_version()), error) ||
        !dict_set_owned(details, "pipewire_library_version", PyUnicode_FromString(pw_get_library_version()), error) ||
        !dict_set_owned(details, "pipewire_remote_version", remote_version ? PyUnicode_FromString(remote_version) : Py_NewRef(Py_None), error) ||
        !dict_set_owned(health, "state", PyUnicode_FromString(wp_core_is_connected(conn->core) ? "connected" : "disconnected"), error) ||
        !dict_set_owned(health, "generation", PyLong_FromUnsignedLongLong(conn->generation), error) ||
        !dict_set_owned(health, "reason", Py_NewRef(Py_None), error)) {
        Py_XDECREF(details);
        Py_XDECREF(health);
        return NULL;
    }
    if (!dict_move(health, "details", &details, error)) {
        Py_DECREF(health);
        return NULL;
    }
    return health;
}


static PyObject *capture_runtime_payload(WPConnection *conn, GError **error) {
    g_autoptr(WpIterator) iterator = NULL;
    g_autoptr(GDateTime) now = NULL;
    g_autofree gchar *captured_at = NULL;
    PyObject *payload = PyDict_New();
    PyObject *devices = PyList_New(0);
    PyObject *nodes = PyList_New(0);
    PyObject *ports = PyList_New(0);
    PyObject *links = PyList_New(0);
    PyObject *metadata = PyList_New(0);
    PyObject *parameters = PyList_New(0);
    PyObject *profiles = PyList_New(0);
    PyObject *routes = PyList_New(0);
    PyObject *defaults = PyList_New(0);
    if (!payload || !devices || !nodes || !ports || !links || !metadata ||
        !parameters || !profiles || !routes || !defaults) {
        set_capture_error(error, "Failed to allocate runtime payload collections");
        goto fail;
    }

    iterator = wp_object_manager_new_iterator(conn->om);
    g_auto(GValue) value = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &value)) {
        GObject *object = g_value_get_object(&value);
        gboolean success = TRUE;
        if (WP_IS_DEVICE(object)) {
            success = append_device(WP_DEVICE(object), devices, parameters, profiles, routes, error);
        } else if (WP_IS_NODE(object)) {
            success = append_node(WP_NODE(object), nodes, parameters, profiles, routes, error);
        } else if (WP_IS_PORT(object)) {
            success = append_port(WP_PORT(object), ports, parameters, profiles, routes, error);
        } else if (WP_IS_LINK(object)) {
            success = append_link(
                conn, WP_LINK(object), links,
                parameters, profiles, routes, error);
        } else if (WP_IS_METADATA(object)) {
            success = append_metadata(WP_METADATA(object), metadata, defaults, error);
        }
        g_value_unset(&value);
        if (!success) goto fail;
    }

    const guint64 sequence = conn->sequence + 1;
    now = g_date_time_new_now_utc();
    captured_at = now ? g_date_time_format_iso8601(now) : NULL;
    if (!captured_at ||
        !dict_set_owned(payload, "payload_version", PyLong_FromLong(1), error) ||
        !dict_set_owned(payload, "generation", PyLong_FromUnsignedLongLong(conn->generation), error) ||
        !dict_set_owned(payload, "sequence", PyLong_FromUnsignedLongLong(sequence), error) ||
        !dict_set_owned(payload, "captured_at", PyUnicode_FromString(captured_at), error) ||
        !dict_set_owned(payload, "health", build_health(conn, error), error)) {
        goto fail;
    }
    if (!dict_move(payload, "devices", &devices, error) ||
        !dict_move(payload, "nodes", &nodes, error) ||
        !dict_move(payload, "ports", &ports, error) ||
        !dict_move(payload, "links", &links, error) ||
        !dict_move(payload, "metadata", &metadata, error) ||
        !dict_move(payload, "parameters", &parameters, error) ||
        !dict_move(payload, "profiles", &profiles, error) ||
        !dict_move(payload, "routes", &routes, error) ||
        !dict_move(payload, "defaults", &defaults, error)) {
        goto fail;
    }
    conn->sequence = sequence;
    // This snapshot is the new projection baseline. Events queued before it are
    // represented by the snapshot and must not be replayed afterward.
    wp_connection_runtime_events_reset(conn);
    return payload;

fail:
    Py_XDECREF(payload);
    Py_XDECREF(devices);
    Py_XDECREF(nodes);
    Py_XDECREF(ports);
    Py_XDECREF(links);
    Py_XDECREF(metadata);
    Py_XDECREF(parameters);
    Py_XDECREF(profiles);
    Py_XDECREF(routes);
    Py_XDECREF(defaults);
    return NULL;
}


static gboolean do_capture_runtime_on_wp_thread(gpointer user_data) {
    CaptureRuntimeData *data = user_data;
    const PyGILState_STATE gil_state = PyGILState_Ensure();
    data->result = capture_runtime_payload(data->conn, &data->error);
    if (!data->result && !data->error) {
        set_capture_error(&data->error, "Failed to capture runtime payload");
    }
    PyGILState_Release(gil_state);

    g_mutex_lock(&data->conn->call_lock);
    data->conn->call_completed = TRUE;
    g_cond_signal(&data->conn->call_cond);
    g_mutex_unlock(&data->conn->call_lock);
    return G_SOURCE_REMOVE;
}


PyObject *WPConnection_capture_runtime_payload(
    WPConnection *self,
    PyObject *Py_UNUSED(ignored))
{
    if (!self->ctx || !self->om || !self->core) {
        PyErr_SetString(PyExc_RuntimeError, "WirePlumber runtime is not ready");
        return NULL;
    }
    CaptureRuntimeData data = {
        .conn = self,
        .result = NULL,
        .error = NULL,
    };

    g_mutex_lock(&self->call_lock);
    self->call_completed = FALSE;
    g_mutex_unlock(&self->call_lock);

    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_capture_runtime_on_wp_thread, &data, NULL);
    g_source_attach(source, self->ctx);
    g_source_unref(source);

    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&self->call_lock);
    while (!self->call_completed) {
        g_cond_wait(&self->call_cond, &self->call_lock);
    }
    g_mutex_unlock(&self->call_lock);
    Py_END_ALLOW_THREADS

    if (data.error) {
        PyErr_SetString(PyExc_RuntimeError, data.error->message);
        g_error_free(data.error);
        Py_XDECREF(data.result);
        return NULL;
    }
    if (!data.result) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to capture runtime payload");
        return NULL;
    }
    return data.result;
}
