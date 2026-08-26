#include "wp_connection.h"
#include "../wp_compat.h"

#include <spa/pod/pod.h>


static gboolean set_owned(PyObject *dict, const char *key, PyObject *value) {
    if (!value) {
        PyErr_Clear();
        return FALSE;
    }
    const int result = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    if (result < 0) {
        PyErr_Clear();
        return FALSE;
    }
    return TRUE;
}


static PyObject *copy_properties(WpProperties *properties) {
    PyObject *result = PyDict_New();
    if (!result || !properties) return result;

    g_autoptr(WpIterator) iterator = wp_properties_new_iterator(properties);
    g_auto(GValue) item = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &item)) {
        WpPropertiesItem *property = g_value_get_boxed(&item);
        const gchar *key = property ? wp_properties_item_get_key(property) : NULL;
        const gchar *value = property ? wp_properties_item_get_value(property) : NULL;
        if (key && value) {
            PyObject *py_value = PyUnicode_FromString(value);
            if (!py_value || PyDict_SetItemString(result, key, py_value) < 0) {
                Py_XDECREF(py_value);
                g_value_unset(&item);
                Py_DECREF(result);
                PyErr_Clear();
                return NULL;
            }
            Py_DECREF(py_value);
        }
        g_value_unset(&item);
    }
    return result;
}


static PyObject *copy_parameter_ids(WpPipewireObject *object) {
    PyObject *result = PyList_New(0);
    if (!result) return NULL;
    g_autoptr(GVariant) info = wp_pipewire_object_get_param_info(object);
    if (!info || !g_variant_is_of_type(info, G_VARIANT_TYPE("a{ss}"))) {
        return result;
    }

    GVariantIter iterator;
    const gchar *parameter_id = NULL;
    const gchar *permissions = NULL;
    g_variant_iter_init(&iterator, info);
    while (g_variant_iter_loop(&iterator, "{&s&s}", &parameter_id, &permissions)) {
        PyObject *value = PyUnicode_FromString(parameter_id ? parameter_id : "");
        if (!value || PyList_Append(result, value) < 0) {
            Py_XDECREF(value);
            Py_DECREF(result);
            PyErr_Clear();
            return NULL;
        }
        Py_DECREF(value);
    }
    return result;
}


static PyObject *copy_raw_parameter_values(
    WpPipewireObject *object, const gchar *parameter_id)
{
    PyObject *result = PyList_New(0);
    if (!result) return NULL;
    g_autoptr(WpIterator) iterator =
        wp_pipewire_object_enum_params_sync(object, parameter_id, NULL);
    if (!iterator) return result;

    g_auto(GValue) value = G_VALUE_INIT;
    while (wp_iterator_next(iterator, &value)) {
        WpSpaPod *pod = g_value_get_boxed(&value);
        const struct spa_pod *spa_pod = pod ? wp_spa_pod_get_spa_pod(pod) : NULL;
        if (!spa_pod) {
            g_value_unset(&value);
            continue;
        }
        const gsize total_size = sizeof(struct spa_pod) + spa_pod->size;
        PyObject *data = PyBytes_FromStringAndSize(
            (const gchar *) spa_pod, (Py_ssize_t) total_size);
        PyObject *record = data ? Py_BuildValue(
            "{sI,sI,sO}", "type", spa_pod->type,
            "size", spa_pod->size, "data", data) : NULL;
        Py_XDECREF(data);
        if (!record || PyList_Append(result, record) < 0) {
            Py_XDECREF(record);
            g_value_unset(&value);
            Py_DECREF(result);
            PyErr_Clear();
            return NULL;
        }
        Py_DECREF(record);
        g_value_unset(&value);
    }
    return result;
}


static const gchar *object_kind(GObject *object) {
    if (WP_IS_DEVICE(object)) return "device";
    if (WP_IS_NODE(object)) return "node";
    if (WP_IS_PORT(object)) return "port";
    if (WP_IS_LINK(object)) return "link";
    if (WP_IS_METADATA(object)) return "metadata";
    return NULL;
}


static PyObject *copy_metadata_record(WpMetadata *metadata) {
    const guint32 id = wp_proxy_get_bound_id(WP_PROXY(metadata));
    WpProperties *properties =
        wp_global_proxy_get_global_properties(WP_GLOBAL_PROXY(metadata));
    const gchar *name = properties
        ? wp_properties_get(properties, "metadata.name") : NULL;
    PyObject *record = PyDict_New();
    PyObject *entries = PyList_New(0);
    if (!record || !entries ||
        !set_owned(record, "id", PyLong_FromUnsignedLong(id)) ||
        !set_owned(record, "name", name ? PyUnicode_FromString(name) : Py_NewRef(Py_None)) ||
        !set_owned(record, "properties", copy_properties(properties))) {
        Py_XDECREF(record);
        Py_XDECREF(entries);
        return NULL;
    }

    g_autoptr(WpIterator) iterator = wp_metadata_new_iterator(metadata, -1);
    g_auto(GValue) value = G_VALUE_INIT;
    while (iterator && wp_iterator_next(iterator, &value)) {
        guint32 subject = 0;
        const gchar *key = NULL;
        const gchar *type = NULL;
        const gchar *item_value = NULL;
        if (!wyreplumber_metadata_item_extract(
                &value, &subject, &key, &type, &item_value)) {
            g_value_unset(&value);
            continue;
        }
        PyObject *entry = Py_BuildValue(
            "{sI,s:s,s:z,s:z}",
            "subject", subject,
            "key", key ? key : "",
            "type", type,
            "value", item_value);
        if (!entry || PyList_Append(entries, entry) < 0) {
            Py_XDECREF(entry);
            g_value_unset(&value);
            Py_DECREF(record);
            Py_DECREF(entries);
            PyErr_Clear();
            return NULL;
        }
        Py_DECREF(entry);
        g_value_unset(&value);
    }
    if (!set_owned(record, "entries", entries)) {
        Py_DECREF(record);
        return NULL;
    }
    return record;
}


static PyObject *copy_object_record(WPConnection *conn, GObject *object) {
    if (WP_IS_METADATA(object)) {
        return copy_metadata_record(WP_METADATA(object));
    }
    if (!WP_IS_PIPEWIRE_OBJECT(object) || !WP_IS_PROXY(object)) return NULL;

    WpPipewireObject *pipewire_object = WP_PIPEWIRE_OBJECT(object);
    PyObject *record = PyDict_New();
    if (!record ||
        !set_owned(record, "id", PyLong_FromUnsignedLong(
            wp_proxy_get_bound_id(WP_PROXY(object)))) ||
        !set_owned(record, "properties", copy_properties(
            wp_pipewire_object_get_properties(pipewire_object))) ||
        !set_owned(record, "parameter_ids", copy_parameter_ids(pipewire_object))) {
        Py_XDECREF(record);
        return NULL;
    }

    if (WP_IS_NODE(object)) {
        const gchar *error = NULL;
        const WpNodeState state = wp_node_get_state(WP_NODE(object), &error);
        if (!set_owned(record, "state", PyLong_FromLong(state)) ||
            !set_owned(record, "error", error ? PyUnicode_FromString(error) : Py_NewRef(Py_None))) {
            Py_DECREF(record);
            return NULL;
        }
    } else if (WP_IS_PORT(object)) {
        if (!set_owned(record, "direction", PyLong_FromLong(
                wp_port_get_direction(WP_PORT(object))))) {
            Py_DECREF(record);
            return NULL;
        }
    } else if (WP_IS_LINK(object)) {
        guint32 output_node = 0;
        guint32 output_port = 0;
        guint32 input_node = 0;
        guint32 input_port = 0;
        const gchar *error = NULL;
        wp_link_get_linked_object_ids(
            WP_LINK(object), &output_node, &output_port, &input_node, &input_port);
        const WpLinkState state = wp_link_get_state(WP_LINK(object), &error);
        const WpManagedLinkSpec *managed =
            wp_connection_managed_link_lookup_endpoints(
                conn, output_node, output_port, input_node, input_port);
        PyObject *properties = PyDict_GetItemString(record, "properties");
        if (managed && properties &&
            (!set_owned(
                 properties,
                 "open-cinema.owner",
                 PyUnicode_FromString(managed->owner)) ||
             !set_owned(
                 properties,
                 "open-cinema.desired-id",
                 PyUnicode_FromString(managed->desired_id)))) {
            Py_DECREF(record);
            PyErr_Clear();
            return NULL;
        }
        if (!set_owned(record, "output_node_id", PyLong_FromUnsignedLong(output_node)) ||
            !set_owned(record, "output_port_id", PyLong_FromUnsignedLong(output_port)) ||
            !set_owned(record, "input_node_id", PyLong_FromUnsignedLong(input_node)) ||
            !set_owned(record, "input_port_id", PyLong_FromUnsignedLong(input_port)) ||
            !set_owned(record, "state", PyLong_FromLong(state)) ||
            !set_owned(record, "error", error ? PyUnicode_FromString(error) : Py_NewRef(Py_None))) {
            Py_DECREF(record);
            return NULL;
        }
    }
    return record;
}


static PyObject *new_event(
    WPConnection *conn,
    const gchar *kind,
    const gchar *event_object_kind,
    PyObject *event_object_id,
    PyObject *current,
    PyObject *previous,
    gboolean requires_resnapshot,
    const gchar *reason)
{
    g_autoptr(GDateTime) now = g_date_time_new_now_utc();
    g_autofree gchar *occurred_at = now ? g_date_time_format_iso8601(now) : NULL;
    PyObject *payload = PyDict_New();
    const guint64 sequence = ++conn->sequence;
    if (!payload || !occurred_at ||
        !set_owned(payload, "payload_version", PyLong_FromLong(1)) ||
        !set_owned(payload, "generation", PyLong_FromUnsignedLongLong(conn->generation)) ||
        !set_owned(payload, "sequence", PyLong_FromUnsignedLongLong(sequence)) ||
        !set_owned(payload, "occurred_at", PyUnicode_FromString(occurred_at)) ||
        !set_owned(payload, "kind", PyUnicode_FromString(kind)) ||
        !set_owned(payload, "object_kind", PyUnicode_FromString(event_object_kind)) ||
        !set_owned(payload, "object_id", event_object_id) ||
        !set_owned(payload, "current", current ? current : Py_NewRef(Py_None)) ||
        !set_owned(payload, "previous", previous ? previous : Py_NewRef(Py_None)) ||
        !set_owned(payload, "requires_resnapshot", PyBool_FromLong(requires_resnapshot)) ||
        !set_owned(payload, "reason", reason ? PyUnicode_FromString(reason) : Py_NewRef(Py_None))) {
        Py_XDECREF(payload);
        return NULL;
    }
    return payload;
}


static void clear_locked(WPConnection *conn) {
    PyObject *payload = NULL;
    while ((payload = g_queue_pop_head(conn->runtime_events))) {
        Py_DECREF(payload);
    }
}


static void make_discontinuity(PyObject *payload, guint capacity) {
    gchar *reason = g_strdup_printf(
        "native event queue capacity %u exceeded", capacity);
    set_owned(payload, "kind", PyUnicode_FromString("discontinuity"));
    set_owned(payload, "object_kind", PyUnicode_FromString("runtime"));
    set_owned(payload, "object_id", PyUnicode_FromString("runtime"));
    set_owned(payload, "current", Py_NewRef(Py_None));
    set_owned(payload, "previous", Py_NewRef(Py_None));
    set_owned(payload, "requires_resnapshot", PyBool_FromLong(TRUE));
    set_owned(payload, "reason", PyUnicode_FromString(reason));
    g_free(reason);
}


static void enqueue(WPConnection *conn, PyObject *payload) {
    if (!payload) return;
    g_mutex_lock(&conn->event_lock);
    if (conn->runtime_event_closed || conn->runtime_event_invalid) {
        g_mutex_unlock(&conn->event_lock);
        Py_DECREF(payload);
        return;
    }
    if (g_queue_get_length(conn->runtime_events) >= conn->runtime_event_capacity) {
        clear_locked(conn);
        make_discontinuity(payload, conn->runtime_event_capacity);
        conn->runtime_event_invalid = TRUE;
    }
    g_queue_push_tail(conn->runtime_events, payload);
    g_cond_broadcast(&conn->event_cond);
    g_mutex_unlock(&conn->event_lock);
}


static void publish_object_event(
    WPConnection *conn, GObject *object, const gchar *kind)
{
    const gchar *event_object_kind = object_kind(object);
    if (!event_object_kind || !conn->started || conn->stop_requested) return;
    const PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *record = copy_object_record(conn, object);
    PyObject *object_id = NULL;
    if (WP_IS_PROXY(object)) {
        object_id = PyLong_FromUnsignedLong(wp_proxy_get_bound_id(WP_PROXY(object)));
    }
    if (!object_id && record) {
        object_id = Py_NewRef(PyDict_GetItemString(record, "id"));
    }
    if (!object_id) object_id = PyUnicode_FromString("unknown");
    PyObject *payload = new_event(
        conn, kind, event_object_kind, object_id,
        g_str_equal(kind, "object_removed") ? NULL : record,
        g_str_equal(kind, "object_removed") ? record : NULL,
        FALSE, NULL);
    enqueue(conn, payload);
    PyGILState_Release(gil);
}


static void on_object_properties_changed(
    GObject *object, GParamSpec *pspec, gpointer user_data)
{
    publish_object_event(user_data, object, "object_changed");
}


static void on_params_changed(
    WpPipewireObject *object, const gchar *parameter_id, gpointer user_data)
{
    WPConnection *conn = user_data;
    if (!conn->started || conn->stop_requested) return;
    const gchar *owner_type = object_kind(G_OBJECT(object));
    if (!owner_type) return;

    const PyGILState_STATE gil = PyGILState_Ensure();
    const guint32 owner_id = wp_proxy_get_bound_id(WP_PROXY(object));
    PyObject *current = PyDict_New();
    PyObject *values = copy_raw_parameter_values(object, parameter_id);
    gboolean copied = current && values &&
        set_owned(current, "owner_type", PyUnicode_FromString(owner_type)) &&
        set_owned(current, "owner_id", PyLong_FromUnsignedLong(owner_id)) &&
        set_owned(current, "id", PyUnicode_FromString(parameter_id ? parameter_id : "")) &&
        set_owned(current, "permissions", PyUnicode_FromString("r")) &&
        set_owned(current, "complete", PyBool_FromLong(TRUE));
    if (copied) {
        copied = set_owned(current, "values", values);
        values = NULL;
    }
    if (copied) {
        gchar *identity = g_strdup_printf(
            "%s:%u:%s", owner_type, owner_id,
            parameter_id ? parameter_id : "");
        enqueue(conn, new_event(
            conn, "parameter_changed", "parameter",
            PyUnicode_FromString(identity), current, NULL, FALSE, NULL));
        g_free(identity);
    } else {
        Py_XDECREF(current);
        Py_XDECREF(values);
        PyErr_Clear();
        enqueue(conn, new_event(
            conn, "resnapshot_required", "runtime",
            PyUnicode_FromString("runtime"), NULL, NULL, TRUE,
            "failed to detach changed parameter"));
    }
    PyGILState_Release(gil);
}


static void on_metadata_changed(
    WpMetadata *metadata,
    guint32 subject,
    const gchar *key,
    const gchar *type,
    const gchar *value,
    gpointer user_data)
{
    WPConnection *conn = user_data;
    if (!conn->started || conn->stop_requested) return;
    const PyGILState_STATE gil = PyGILState_Ensure();
    const guint32 metadata_id = wp_proxy_get_bound_id(WP_PROXY(metadata));
    PyObject *current = Py_BuildValue(
        "{sI,sI,s:s,s:z,s:z}",
        "metadata_id", metadata_id,
        "subject", subject,
        "key", key ? key : "",
        "type", type,
        "value", value);
    gchar *identity = g_strdup_printf(
        "%u:%u:%s", metadata_id, subject, key ? key : "");
    enqueue(conn, new_event(
        conn, "metadata_changed", "metadata",
        PyUnicode_FromString(identity), current, NULL, FALSE, NULL));
    if (key && g_str_has_prefix(key, "default.")) {
        PyObject *default_current = Py_BuildValue(
            "{sI,sI,s:s,s:z,s:z}",
            "metadata_id", metadata_id,
            "subject", subject,
            "key", key,
            "type", type,
            "value", value);
        enqueue(conn, new_event(
            conn, "default_changed", "defaults",
            PyUnicode_FromString(key), default_current, NULL, FALSE, NULL));
    }
    g_free(identity);
    PyGILState_Release(gil);
}


void wp_connection_runtime_events_on_object_added(
    WpObjectManager *om, GObject *object, gpointer user_data)
{
    if (WP_IS_PIPEWIRE_OBJECT(object)) {
        g_signal_connect(object, "params-changed", G_CALLBACK(on_params_changed), user_data);
        g_signal_connect(
            object, "notify::properties",
            G_CALLBACK(on_object_properties_changed), user_data);
    }
    if (WP_IS_METADATA(object)) {
        g_signal_connect(object, "changed", G_CALLBACK(on_metadata_changed), user_data);
    }
    publish_object_event(user_data, object, "object_added");
}


void wp_connection_runtime_events_on_object_removed(
    WpObjectManager *om, GObject *object, gpointer user_data)
{
    WPConnection *conn = user_data;
    publish_object_event(conn, object, "object_removed");
    if (WP_IS_LINK(object) &&
        (wp_object_get_active_features(WP_OBJECT(object)) &
         WP_PIPEWIRE_OBJECT_FEATURE_INFO)) {
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
        wp_connection_managed_link_forget_endpoints(
            conn, output_node, output_port, input_node, input_port);
    }
}


void wp_connection_runtime_events_publish_connection(
    WPConnection *conn, const gchar *state, const gchar *reason)
{
    const PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *health = PyDict_New();
    if (health &&
        set_owned(health, "state", PyUnicode_FromString(state)) &&
        set_owned(health, "generation", PyLong_FromUnsignedLongLong(conn->generation)) &&
        set_owned(health, "reason", reason ? PyUnicode_FromString(reason) : Py_NewRef(Py_None)) &&
        set_owned(health, "details", PyDict_New())) {
        enqueue(conn, new_event(
            conn, "connection_changed", "connection",
            PyUnicode_FromString("connection"), health, NULL, FALSE, reason));
    } else {
        Py_XDECREF(health);
        PyErr_Clear();
    }
    PyGILState_Release(gil);
}


void wp_connection_runtime_events_reset(WPConnection *conn) {
    g_mutex_lock(&conn->event_lock);
    clear_locked(conn);
    conn->runtime_event_invalid = FALSE;
    g_mutex_unlock(&conn->event_lock);
}


void wp_connection_runtime_events_close(WPConnection *conn) {
    g_mutex_lock(&conn->event_lock);
    conn->runtime_event_closed = TRUE;
    g_cond_broadcast(&conn->event_cond);
    g_mutex_unlock(&conn->event_lock);
}


void wp_connection_runtime_events_clear(WPConnection *conn) {
    g_mutex_lock(&conn->event_lock);
    clear_locked(conn);
    g_mutex_unlock(&conn->event_lock);
}


PyObject *WPConnection_next_runtime_event_payload(
    WPConnection *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"block", "timeout", NULL};
    int block = TRUE;
    PyObject *timeout_object = Py_None;
    if (!PyArg_ParseTupleAndKeywords(
            args, kwargs, "|pO:next_runtime_event_payload",
            kwlist, &block, &timeout_object)) {
        return NULL;
    }

    gint64 deadline = -1;
    if (timeout_object != Py_None) {
        const double timeout = PyFloat_AsDouble(timeout_object);
        if (PyErr_Occurred()) return NULL;
        if (timeout < 0) {
            PyErr_SetString(PyExc_ValueError, "timeout must be non-negative");
            return NULL;
        }
        if (!block) {
            PyErr_SetString(PyExc_ValueError, "timeout cannot be used with a non-blocking read");
            return NULL;
        }
        deadline = g_get_monotonic_time() + (gint64) (timeout * G_TIME_SPAN_SECOND);
    }

    PyObject *payload = NULL;
    gboolean closed = FALSE;
    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&self->event_lock);
    while (g_queue_is_empty(self->runtime_events) &&
           !self->runtime_event_closed && block) {
        if (deadline >= 0) {
            if (!g_cond_wait_until(&self->event_cond, &self->event_lock, deadline)) {
                break;
            }
        } else {
            g_cond_wait(&self->event_cond, &self->event_lock);
        }
    }
    payload = g_queue_pop_head(self->runtime_events);
    closed = self->runtime_event_closed;
    g_mutex_unlock(&self->event_lock);
    Py_END_ALLOW_THREADS

    if (payload) return payload;
    if (closed) {
        PyErr_SetString(PyExc_RuntimeError, "runtime event publication is closed");
        return NULL;
    }
    Py_RETURN_NONE;
}


PyObject *WPConnection_drain_runtime_event_payloads(
    WPConnection *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"max_events", NULL};
    Py_ssize_t max_events = 0;
    if (!PyArg_ParseTupleAndKeywords(
            args, kwargs, "|n:drain_runtime_event_payloads",
            kwlist, &max_events)) {
        return NULL;
    }
    if (max_events < 0) {
        PyErr_SetString(PyExc_ValueError, "max_events must be non-negative");
        return NULL;
    }

    PyObject *result = PyList_New(0);
    if (!result) return NULL;
    g_mutex_lock(&self->event_lock);
    while (!g_queue_is_empty(self->runtime_events) &&
           (max_events == 0 || PyList_GET_SIZE(result) < max_events)) {
        PyObject *payload = g_queue_pop_head(self->runtime_events);
        if (PyList_Append(result, payload) < 0) {
            Py_DECREF(payload);
            g_mutex_unlock(&self->event_lock);
            Py_DECREF(result);
            return NULL;
        }
        Py_DECREF(payload);
    }
    g_mutex_unlock(&self->event_lock);
    return result;
}
