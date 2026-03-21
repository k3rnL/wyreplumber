#include "wp_pipewire_object.h"

#include <gio/gio.h>
#include <spa/pod/pod.h>
#include <string.h>

#include "../wp_connection/wp_connection.h"

typedef struct {
    PyObject_HEAD
    WPPipewireObject *owner;  // Strong reference to parent object
    PyObject *id;             // str
    PyObject *permissions;    // str, for example "r", "w", "rw"
    PyObject *type;           // int or None
    PyObject *values;         // list[dict]
} WPParam;

typedef struct {
    WPConnection *conn;
    WpPipewireObject *pipewire_object;
    const char *param_id;
    PyObject *result;
    GError *error;
} EnumParamsData;

typedef struct {
    WPConnection *conn;
    WpPipewireObject *pipewire_object;
    PyObject *result;
    GError *error;
} GetParamInfoData;

typedef struct {
    WPConnection *conn;
    WPPipewireObject *owner;
    WpPipewireObject *pipewire_object;
    PyObject *result;
    GError *error;
} GetParamsData;

typedef struct {
    WPConnection *conn;
    WpPipewireObject *pipewire_object;
    const char *param_id;
    guint32 flags;
    WpSpaPod *param;
    gboolean success;
    GError *error;
} SetParamData;

PyTypeObject WPParamType;

static void WPPipewireObject_dealloc(WPPipewireObject *self);
static PyObject *WPPipewireObject_get_id(WPPipewireObject *self, void *closure);
static PyObject *WPPipewireObject_get_properties(WPPipewireObject *self, void *closure);
static PyObject *WPPipewireObject_enum_params(WPPipewireObject *self, PyObject *args, PyObject *kwargs);
static PyObject *WPPipewireObject_get_param_info(WPPipewireObject *self, PyObject *Py_UNUSED(ignored));
static PyObject *WPPipewireObject_get_params(WPPipewireObject *self, PyObject *Py_UNUSED(ignored));

static void WPParam_dealloc(WPParam *self);
static PyObject *WPParam_repr(WPParam *self);
static PyObject *WPParam_get_id(WPParam *self, void *closure);
static PyObject *WPParam_get_permissions(WPParam *self, void *closure);
static PyObject *WPParam_get_type(WPParam *self, void *closure);
static PyObject *WPParam_get(WPParam *self, PyObject *Py_UNUSED(ignored));
static PyObject *WPParam_set(WPParam *self, PyObject *args, PyObject *kwargs);

static void signal_call_completed(WPConnection *conn) {
    g_mutex_lock(&conn->call_lock);
    conn->call_completed = TRUE;
    g_cond_signal(&conn->call_cond);
    g_mutex_unlock(&conn->call_lock);
}

static void schedule_wp_call(WPConnection *conn, GSourceFunc func, gpointer user_data) {
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, func, user_data, NULL);
    g_source_attach(source, conn->ctx);
    g_source_unref(source);
}

static void wait_wp_call_completion(WPConnection *conn) {
    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&conn->call_lock);
    while (!conn->call_completed) {
        g_cond_wait(&conn->call_cond, &conn->call_lock);
    }
    g_mutex_unlock(&conn->call_lock);
    Py_END_ALLOW_THREADS
}

static void set_oom_error(GError **error, const char *message) {
    if (!*error) {
        *error = g_error_new_literal(G_IO_ERROR, G_IO_ERROR_NO_MEMORY, message);
    }
}

static PyObject *iterate_wp_properties(WpProperties *props) {
    PyObject *dict = PyDict_New();
    if (!dict) return NULL;

    if (!props) return dict;

    WpIterator *it = wp_properties_new_iterator(props);
    g_auto(GValue) item = G_VALUE_INIT;

    while (wp_iterator_next(it, &item)) {
        WpPropertiesItem *prop_item = g_value_get_boxed(&item);
        const char *key = wp_properties_item_get_key(prop_item);
        const char *value = wp_properties_item_get_value(prop_item);

        if (key && value) {
            PyObject *py_value = PyUnicode_FromString(value);
            if (!py_value || PyDict_SetItemString(dict, key, py_value) < 0) {
                Py_XDECREF(py_value);
                g_value_unset(&item);
                wp_iterator_unref(it);
                Py_DECREF(dict);
                return NULL;
            }
            Py_DECREF(py_value);
        }

        g_value_unset(&item);
    }

    wp_iterator_unref(it);
    return dict;
}

static PyObject *py_list_from_wp_iterator(WpIterator *it, GError **error, const char *error_prefix) {
    PyObject *list = PyList_New(0);
    if (!list) {
        set_oom_error(error, error_prefix);
        PyErr_Clear();
        return NULL;
    }

    g_auto(GValue) val = G_VALUE_INIT;
    while (wp_iterator_next(it, &val)) {
        WpSpaPod *pod = g_value_get_boxed(&val);
        const struct spa_pod *spa_pod = pod ? wp_spa_pod_get_spa_pod(pod) : NULL;

        if (!spa_pod) {
            g_value_unset(&val);
            continue;
        }

        const gsize total_size = sizeof(struct spa_pod) + spa_pod->size;
        PyObject *pod_bytes = PyBytes_FromStringAndSize(
            (const char *) spa_pod, (Py_ssize_t) total_size);
        if (!pod_bytes) {
            set_oom_error(error, error_prefix);
            PyErr_Clear();
            g_value_unset(&val);
            Py_DECREF(list);
            return NULL;
        }

        PyObject *pod_dict = Py_BuildValue(
            "{sI,sI,sO}",
            "type", spa_pod->type,
            "size", spa_pod->size,
            "data", pod_bytes);
        Py_DECREF(pod_bytes);

        if (!pod_dict || PyList_Append(list, pod_dict) < 0) {
            set_oom_error(error, error_prefix);
            PyErr_Clear();
            Py_XDECREF(pod_dict);
            g_value_unset(&val);
            Py_DECREF(list);
            return NULL;
        }

        Py_DECREF(pod_dict);
        g_value_unset(&val);
    }

    return list;
}

static void WPParam_update_type_from_values(WPParam *self) {
    PyObject *new_type = Py_None;
    Py_INCREF(Py_None);

    if (self->values && PyList_Check(self->values) && PyList_GET_SIZE(self->values) > 0) {
        PyObject *first_item = PyList_GET_ITEM(self->values, 0);  // borrowed
        if (first_item && PyDict_Check(first_item)) {
            PyObject *type_obj = PyDict_GetItemString(first_item, "type");  // borrowed
            if (type_obj) {
                Py_INCREF(type_obj);
                Py_DECREF(new_type);
                new_type = type_obj;
            }
        }
    }

    Py_XDECREF(self->type);
    self->type = new_type;
}

static PyObject *WPParam_new_from_data(
    WPPipewireObject *owner,
    const char *param_id,
    const char *permissions,
    PyObject *values)
{
    WPParam *self = (WPParam *) WPParamType.tp_alloc(&WPParamType, 0);
    if (!self) return NULL;

    self->owner = owner;
    Py_INCREF(owner);

    self->id = PyUnicode_FromString(param_id ? param_id : "");
    self->permissions = PyUnicode_FromString(permissions ? permissions : "");
    if (!values) {
        self->values = PyList_New(0);
    } else {
        self->values = values;
        Py_INCREF(values);
    }
    self->type = NULL;

    if (!self->id || !self->permissions || !self->values) {
        Py_DECREF(self);
        return NULL;
    }

    WPParam_update_type_from_values(self);
    return (PyObject *) self;
}

static gboolean do_enum_params_on_wp_thread(gpointer user_data) {
    EnumParamsData *data = user_data;

    g_autoptr(WpIterator) it =
        wp_pipewire_object_enum_params_sync(data->pipewire_object, data->param_id, NULL);

    const PyGILState_STATE gstate = PyGILState_Ensure();

    if (!it) {
        data->error = g_error_new(
            G_IO_ERROR, G_IO_ERROR_FAILED,
            "Failed to enumerate params for id '%s' (feature may not be activated)",
            data->param_id);
        PyGILState_Release(gstate);
        goto done;
    }

    data->result = py_list_from_wp_iterator(
        it, &data->error, "Failed to allocate list for enum_params");

    PyGILState_Release(gstate);

done:
    signal_call_completed(data->conn);
    return G_SOURCE_REMOVE;
}

static gboolean do_get_param_info_on_wp_thread(gpointer user_data) {
    GetParamInfoData *data = user_data;
    g_autoptr(GVariant) param_info = wp_pipewire_object_get_param_info(data->pipewire_object);

    const PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *dict = PyDict_New();
    if (!dict) {
        data->error = g_error_new_literal(
            G_IO_ERROR, G_IO_ERROR_NO_MEMORY, "Failed to allocate dict for get_param_info");
        PyErr_Clear();
        PyGILState_Release(gstate);
        goto done;
    }

    if (param_info) {
        if (!g_variant_is_of_type(param_info, G_VARIANT_TYPE("a{ss}"))) {
            data->error = g_error_new_literal(
                G_IO_ERROR, G_IO_ERROR_INVALID_DATA, "Unexpected param info variant type");
            Py_DECREF(dict);
            dict = NULL;
        } else {
            GVariantIter iter;
            const gchar *key = NULL;
            const gchar *value = NULL;

            g_variant_iter_init(&iter, param_info);
            while (g_variant_iter_loop(&iter, "{&s&s}", &key, &value)) {
                PyObject *py_value = PyUnicode_FromString(value ? value : "");
                if (!py_value || PyDict_SetItemString(dict, key, py_value) < 0) {
                    data->error = g_error_new_literal(
                        G_IO_ERROR, G_IO_ERROR_NO_MEMORY,
                        "Failed to append get_param_info item");
                    PyErr_Clear();
                    Py_XDECREF(py_value);
                    Py_DECREF(dict);
                    dict = NULL;
                    break;
                }
                Py_DECREF(py_value);
            }
        }
    }

    data->result = dict;
    PyGILState_Release(gstate);

done:
    signal_call_completed(data->conn);
    return G_SOURCE_REMOVE;
}

static gboolean do_get_params_on_wp_thread(gpointer user_data) {
    GetParamsData *data = user_data;
    g_autoptr(GVariant) param_info = wp_pipewire_object_get_param_info(data->pipewire_object);

    const PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *params = PyDict_New();
    if (!params) {
        data->error = g_error_new_literal(
            G_IO_ERROR, G_IO_ERROR_NO_MEMORY, "Failed to allocate dict for get_params");
        PyErr_Clear();
        PyGILState_Release(gstate);
        goto done;
    }

    if (param_info && !g_variant_is_of_type(param_info, G_VARIANT_TYPE("a{ss}"))) {
        data->error = g_error_new_literal(
            G_IO_ERROR, G_IO_ERROR_INVALID_DATA, "Unexpected param info variant type");
        Py_DECREF(params);
        params = NULL;
        PyGILState_Release(gstate);
        goto done;
    }

    if (param_info) {
        GVariantIter iter;
        const gchar *param_id = NULL;
        const gchar *permissions = NULL;

        g_variant_iter_init(&iter, param_info);
        while (g_variant_iter_loop(&iter, "{&s&s}", &param_id, &permissions)) {
            PyObject *values = PyList_New(0);
            if (!values) {
                data->error = g_error_new_literal(
                    G_IO_ERROR, G_IO_ERROR_NO_MEMORY, "Failed to allocate param values list");
                PyErr_Clear();
                Py_DECREF(params);
                params = NULL;
                break;
            }

            if (permissions && strchr(permissions, 'r')) {
                g_autoptr(WpIterator) it =
                    wp_pipewire_object_enum_params_sync(data->pipewire_object, param_id, NULL);
                if (it) {
                    PyObject *read_values = py_list_from_wp_iterator(
                        it, &data->error, "Failed to allocate values while building get_params");
                    if (!read_values) {
                        Py_DECREF(values);
                        Py_DECREF(params);
                        params = NULL;
                        break;
                    }
                    Py_DECREF(values);
                    values = read_values;
                }
            }

            PyObject *param_obj = WPParam_new_from_data(data->owner, param_id, permissions, values);
            Py_DECREF(values);
            if (!param_obj) {
                if (!data->error) {
                    data->error = g_error_new_literal(
                        G_IO_ERROR, G_IO_ERROR_NO_MEMORY, "Failed to create WPParam object");
                }
                PyErr_Clear();
                Py_DECREF(params);
                params = NULL;
                break;
            }

            if (PyDict_SetItemString(params, param_id, param_obj) < 0) {
                data->error = g_error_new_literal(
                    G_IO_ERROR, G_IO_ERROR_NO_MEMORY, "Failed to append get_params item");
                PyErr_Clear();
                Py_DECREF(param_obj);
                Py_DECREF(params);
                params = NULL;
                break;
            }

            Py_DECREF(param_obj);
        }
    }

    data->result = params;
    PyGILState_Release(gstate);

done:
    signal_call_completed(data->conn);
    return G_SOURCE_REMOVE;
}

static gboolean do_set_param_on_wp_thread(gpointer user_data) {
    SetParamData *data = user_data;

    data->success = wp_pipewire_object_set_param(
        data->pipewire_object,
        data->param_id,
        data->flags,
        data->param);
    data->param = NULL;  // transfer-full ownership was consumed by set_param

    if (!data->success) {
        data->error = g_error_new(
            G_IO_ERROR, G_IO_ERROR_FAILED,
            "Failed to set param '%s'", data->param_id);
    }

    signal_call_completed(data->conn);
    return G_SOURCE_REMOVE;
}

void WPPipewireObject_clear(WPPipewireObject *self) {
    if (!self) return;

    if (self->pipewire_object) {
        g_object_unref(self->pipewire_object);
        self->pipewire_object = NULL;
    }
    if (self->core) {
        g_object_unref(self->core);
        self->core = NULL;
    }
    Py_XDECREF(self->connection);
    self->connection = NULL;
    Py_XDECREF(self->properties);
    self->properties = NULL;
    self->id = 0;
}

gboolean WPPipewireObject_init_from_wp_pipewire_object(
    WPPipewireObject *self,
    WpPipewireObject *wp_pipewire_object,
    WpCore *core,
    struct WPConnection *conn)
{
    if (!self || !wp_pipewire_object || !core) return FALSE;

    self->pipewire_object = g_object_ref(wp_pipewire_object);
    self->core = g_object_ref(core);
    self->connection = conn ? (PyObject *) conn : NULL;
    if (self->connection) Py_INCREF(self->connection);

    self->id = wp_proxy_get_bound_id(WP_PROXY(wp_pipewire_object));

    WpProperties *props = wp_pipewire_object_get_properties(wp_pipewire_object);
    self->properties = iterate_wp_properties(props);
    if (!self->properties) {
        WPPipewireObject_clear(self);
        return FALSE;
    }

    return TRUE;
}

static void WPPipewireObject_dealloc(WPPipewireObject *self) {
    WPPipewireObject_clear(self);
    Py_TYPE(self)->tp_free((PyObject *) self);
}

static PyObject *WPPipewireObject_get_id(WPPipewireObject *self, void *closure) {
    return PyLong_FromUnsignedLong(self->id);
}

static PyObject *WPPipewireObject_get_properties(WPPipewireObject *self, void *closure) {
    Py_INCREF(self->properties);
    return self->properties;
}

static PyObject *WPPipewireObject_enum_params(
    WPPipewireObject *self,
    PyObject *args,
    PyObject *kwargs)
{
    static char *kwlist[] = {"id", NULL};
    const char *param_id = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s", kwlist, &param_id)) {
        return NULL;
    }

    if (!self->pipewire_object) {
        PyErr_SetString(PyExc_RuntimeError, "PipeWire object is invalid");
        return NULL;
    }

    if (!self->connection || !PyObject_TypeCheck(self->connection, &WPConnectionType)) {
        PyErr_SetString(PyExc_RuntimeError, "Connection object is invalid");
        return NULL;
    }

    WPConnection *conn = (WPConnection *) self->connection;
    if (!conn->ctx) {
        PyErr_SetString(PyExc_RuntimeError, "Connection context is invalid");
        return NULL;
    }

    EnumParamsData data = {
        .conn = conn,
        .pipewire_object = self->pipewire_object,
        .param_id = param_id,
        .result = NULL,
        .error = NULL
    };

    g_mutex_lock(&conn->call_lock);
    conn->call_completed = FALSE;
    g_mutex_unlock(&conn->call_lock);

    schedule_wp_call(conn, do_enum_params_on_wp_thread, &data);
    wait_wp_call_completion(conn);

    if (data.error) {
        PyErr_SetString(PyExc_RuntimeError, data.error->message);
        g_error_free(data.error);
        return NULL;
    }

    if (!data.result) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to enumerate params");
        return NULL;
    }

    return data.result;
}

static PyObject *WPPipewireObject_get_param_info(
    WPPipewireObject *self,
    PyObject *Py_UNUSED(ignored))
{
    if (!self->pipewire_object) {
        PyErr_SetString(PyExc_RuntimeError, "PipeWire object is invalid");
        return NULL;
    }

    if (!self->connection || !PyObject_TypeCheck(self->connection, &WPConnectionType)) {
        PyErr_SetString(PyExc_RuntimeError, "Connection object is invalid");
        return NULL;
    }

    WPConnection *conn = (WPConnection *) self->connection;
    if (!conn->ctx) {
        PyErr_SetString(PyExc_RuntimeError, "Connection context is invalid");
        return NULL;
    }

    GetParamInfoData data = {
        .conn = conn,
        .pipewire_object = self->pipewire_object,
        .result = NULL,
        .error = NULL
    };

    g_mutex_lock(&conn->call_lock);
    conn->call_completed = FALSE;
    g_mutex_unlock(&conn->call_lock);

    schedule_wp_call(conn, do_get_param_info_on_wp_thread, &data);
    wait_wp_call_completion(conn);

    if (data.error) {
        PyErr_SetString(PyExc_RuntimeError, data.error->message);
        g_error_free(data.error);
        return NULL;
    }

    if (!data.result) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to get param info");
        return NULL;
    }

    return data.result;
}

static PyObject *WPPipewireObject_get_params(
    WPPipewireObject *self,
    PyObject *Py_UNUSED(ignored))
{
    if (!self->pipewire_object) {
        PyErr_SetString(PyExc_RuntimeError, "PipeWire object is invalid");
        return NULL;
    }

    if (!self->connection || !PyObject_TypeCheck(self->connection, &WPConnectionType)) {
        PyErr_SetString(PyExc_RuntimeError, "Connection object is invalid");
        return NULL;
    }

    WPConnection *conn = (WPConnection *) self->connection;
    if (!conn->ctx) {
        PyErr_SetString(PyExc_RuntimeError, "Connection context is invalid");
        return NULL;
    }

    GetParamsData data = {
        .conn = conn,
        .owner = self,
        .pipewire_object = self->pipewire_object,
        .result = NULL,
        .error = NULL
    };

    g_mutex_lock(&conn->call_lock);
    conn->call_completed = FALSE;
    g_mutex_unlock(&conn->call_lock);

    schedule_wp_call(conn, do_get_params_on_wp_thread, &data);
    wait_wp_call_completion(conn);

    if (data.error) {
        PyErr_SetString(PyExc_RuntimeError, data.error->message);
        g_error_free(data.error);
        return NULL;
    }

    if (!data.result) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to get params");
        return NULL;
    }

    return data.result;
}

static void WPParam_dealloc(WPParam *self) {
    Py_XDECREF(self->owner);
    Py_XDECREF(self->id);
    Py_XDECREF(self->permissions);
    Py_XDECREF(self->type);
    Py_XDECREF(self->values);
    Py_TYPE(self)->tp_free((PyObject *) self);
}

static PyObject *WPParam_repr(WPParam *self) {
    const char *param_id = self->id ? PyUnicode_AsUTF8(self->id) : NULL;
    const char *permissions = self->permissions ? PyUnicode_AsUTF8(self->permissions) : NULL;
    return PyUnicode_FromFormat(
        "<WPParam id='%s' permissions='%s'>",
        param_id ? param_id : "",
        permissions ? permissions : "");
}

static PyObject *WPParam_get_id(WPParam *self, void *closure) {
    Py_INCREF(self->id);
    return self->id;
}

static PyObject *WPParam_get_permissions(WPParam *self, void *closure) {
    Py_INCREF(self->permissions);
    return self->permissions;
}

static PyObject *WPParam_get_type(WPParam *self, void *closure) {
    Py_INCREF(self->type);
    return self->type;
}

static PyObject *WPParam_get(WPParam *self, PyObject *Py_UNUSED(ignored)) {
    return PySequence_List(self->values);
}

static PyObject *WPParam_set(WPParam *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"value", "flags", NULL};
    PyObject *value_obj = NULL;
    guint32 flags = 0;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|I", kwlist, &value_obj, &flags)) {
        return NULL;
    }

    if (!self->owner || !self->owner->pipewire_object) {
        PyErr_SetString(PyExc_RuntimeError, "PipeWire object is invalid");
        return NULL;
    }

    if (!self->owner->connection || !PyObject_TypeCheck(self->owner->connection, &WPConnectionType)) {
        PyErr_SetString(PyExc_RuntimeError, "Connection object is invalid");
        return NULL;
    }

    WPConnection *conn = (WPConnection *) self->owner->connection;
    if (!conn->ctx) {
        PyErr_SetString(PyExc_RuntimeError, "Connection context is invalid");
        return NULL;
    }

    PyObject *data_obj = value_obj;
    if (PyDict_Check(value_obj)) {
        data_obj = PyDict_GetItemString(value_obj, "data");  // borrowed
        if (!data_obj) {
            PyErr_SetString(PyExc_TypeError, "param dict must contain a 'data' field");
            return NULL;
        }
    }

    Py_buffer view;
    if (PyObject_GetBuffer(data_obj, &view, PyBUF_SIMPLE) < 0) {
        PyErr_SetString(PyExc_TypeError, "value must be bytes-like or a dict with 'data' bytes");
        return NULL;
    }

    if (view.len < (Py_ssize_t) sizeof(struct spa_pod)) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_ValueError, "param data is too small to be a valid SPA pod");
        return NULL;
    }

    struct spa_pod header;
    memcpy(&header, view.buf, sizeof(struct spa_pod));
    const gsize total_size = sizeof(struct spa_pod) + header.size;
    if ((gsize) view.len < total_size) {
        PyBuffer_Release(&view);
        PyErr_SetString(PyExc_ValueError, "param data length does not match SPA pod size");
        return NULL;
    }

    gpointer pod_copy = g_malloc(total_size);
    if (pod_copy) {
        memcpy(pod_copy, view.buf, total_size);
    }
    PyBuffer_Release(&view);
    if (!pod_copy) {
        PyErr_NoMemory();
        return NULL;
    }

    WpSpaPod *wrapped = wp_spa_pod_new_wrap((struct spa_pod *) pod_copy);
    if (!wrapped) {
        g_free(pod_copy);
        PyErr_SetString(PyExc_RuntimeError, "Failed to wrap SPA pod data");
        return NULL;
    }

    WpSpaPod *param = wp_spa_pod_copy(wrapped);
    wp_spa_pod_unref(wrapped);
    g_free(pod_copy);
    if (!param) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to copy SPA pod data");
        return NULL;
    }

    const char *param_id = PyUnicode_AsUTF8(self->id);
    if (!param_id) {
        wp_spa_pod_unref(param);
        return NULL;
    }

    SetParamData data = {
        .conn = conn,
        .pipewire_object = self->owner->pipewire_object,
        .param_id = param_id,
        .flags = flags,
        .param = param,
        .success = FALSE,
        .error = NULL
    };

    g_mutex_lock(&conn->call_lock);
    conn->call_completed = FALSE;
    g_mutex_unlock(&conn->call_lock);

    schedule_wp_call(conn, do_set_param_on_wp_thread, &data);
    wait_wp_call_completion(conn);

    if (data.param) {
        // Fallback cleanup in case set_param did not consume ownership.
        wp_spa_pod_unref(data.param);
        data.param = NULL;
    }

    if (data.error) {
        PyErr_SetString(PyExc_RuntimeError, data.error->message);
        g_error_free(data.error);
        return NULL;
    }

    if (!data.success) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to set param");
        return NULL;
    }

    PyObject *fresh_values = PyObject_CallMethod(
        (PyObject *) self->owner, "enum_params", "s", param_id);
    if (fresh_values) {
        Py_XDECREF(self->values);
        self->values = fresh_values;
        WPParam_update_type_from_values(self);
    } else {
        // Keep set() successful even if refreshing values is not available.
        PyErr_Clear();
    }

    Py_RETURN_NONE;
}

static PyGetSetDef WPPipewireObject_getsetters[] = {
    {"id", (getter) WPPipewireObject_get_id, NULL, "Global object ID", NULL},
    {"properties", (getter) WPPipewireObject_get_properties, NULL, "Object properties", NULL},
    {NULL}
};

static PyMethodDef WPPipewireObject_methods[] = {
    {
        "get_params",
        (PyCFunction) WPPipewireObject_get_params,
        METH_NOARGS,
        "Return available PipeWire params with values and permissions as Dict[str, WPParam]"
    },
    {
        "get_param_info",
        (PyCFunction) WPPipewireObject_get_param_info,
        METH_NOARGS,
        "Return available PipeWire params and their read/write flags"
    },
    {
        "enum_params",
        (PyCFunction) WPPipewireObject_enum_params,
        METH_VARARGS | METH_KEYWORDS,
        "Enumerate PipeWire params by id and return list of spa pod dictionaries"
    },
    {NULL}
};

static PyGetSetDef WPParam_getsetters[] = {
    {"id", (getter) WPParam_get_id, NULL, "PipeWire param id", NULL},
    {"permissions", (getter) WPParam_get_permissions, NULL, "PipeWire param permissions", NULL},
    {"type", (getter) WPParam_get_type, NULL, "First SPA pod type from current values, if any", NULL},
    {NULL}
};

static PyMethodDef WPParam_methods[] = {
    {
        "get",
        (PyCFunction) WPParam_get,
        METH_NOARGS,
        "Return current values for this param"
    },
    {
        "set",
        (PyCFunction) WPParam_set,
        METH_VARARGS | METH_KEYWORDS,
        "Set this param from raw SPA pod bytes or a pod dict with 'data'"
    },
    {NULL}
};

PyTypeObject WPPipewireObjectType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_core.WPPipewireObject",
    .tp_doc = "WirePlumber PipeWire object base wrapper",
    .tp_basicsize = sizeof(WPPipewireObject),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_dealloc = (destructor) WPPipewireObject_dealloc,
    .tp_methods = WPPipewireObject_methods,
    .tp_getset = WPPipewireObject_getsetters,
};

PyTypeObject WPParamType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_core.WPParam",
    .tp_doc = "Structured PipeWire parameter wrapper",
    .tp_basicsize = sizeof(WPParam),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_dealloc = (destructor) WPParam_dealloc,
    .tp_repr = (reprfunc) WPParam_repr,
    .tp_methods = WPParam_methods,
    .tp_getset = WPParam_getsetters,
};
