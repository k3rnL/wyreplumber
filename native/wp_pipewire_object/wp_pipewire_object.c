#include "wp_pipewire_object.h"

#include <spa/pod/pod.h>

#include "../wp_connection/wp_connection.h"

typedef struct {
    WPConnection *conn;
    WpPipewireObject *pipewire_object;
    const char *param_id;
    PyObject *result;
    GError *error;
} EnumParamsData;

static void WPPipewireObject_dealloc(WPPipewireObject *self);
static PyObject *WPPipewireObject_get_id(WPPipewireObject *self, void *closure);
static PyObject *WPPipewireObject_get_properties(WPPipewireObject *self, void *closure);
static PyObject *WPPipewireObject_enum_params(WPPipewireObject *self, PyObject *args, PyObject *kwargs);

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

    PyObject *list = PyList_New(0);
    if (!list) {
        data->error = g_error_new_literal(
            G_IO_ERROR, G_DBUS_ERROR_NO_MEMORY, "Failed to allocate list for enum_params");
        PyGILState_Release(gstate);
        goto done;
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
            data->error = g_error_new_literal(
                G_IO_ERROR, G_DBUS_ERROR_NO_MEMORY, "Failed to allocate bytes for enum_params pod");
            g_value_unset(&val);
            Py_DECREF(list);
            list = NULL;
            break;
        }

        PyObject *pod_dict = Py_BuildValue(
            "{sI,sI,sO}",
            "type", spa_pod->type,
            "size", spa_pod->size,
            "data", pod_bytes);
        Py_DECREF(pod_bytes);

        if (!pod_dict || PyList_Append(list, pod_dict) < 0) {
            data->error = g_error_new_literal(
                G_IO_ERROR, G_DBUS_ERROR_NO_MEMORY, "Failed to append enum_params item");
            Py_XDECREF(pod_dict);
            g_value_unset(&val);
            Py_DECREF(list);
            list = NULL;
            break;
        }

        Py_DECREF(pod_dict);
        g_value_unset(&val);
    }

    data->result = list;
    PyGILState_Release(gstate);

done:
    g_mutex_lock(&data->conn->call_lock);
    data->conn->call_completed = TRUE;
    g_cond_signal(&data->conn->call_cond);
    g_mutex_unlock(&data->conn->call_lock);

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

    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_enum_params_on_wp_thread, &data, NULL);
    g_source_attach(source, conn->ctx);
    g_source_unref(source);

    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&conn->call_lock);
    while (!conn->call_completed) {
        g_cond_wait(&conn->call_cond, &conn->call_lock);
    }
    g_mutex_unlock(&conn->call_lock);
    Py_END_ALLOW_THREADS

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

static PyGetSetDef WPPipewireObject_getsetters[] = {
    {"id", (getter) WPPipewireObject_get_id, NULL, "Global object ID", NULL},
    {"properties", (getter) WPPipewireObject_get_properties, NULL, "Object properties", NULL},
    {NULL}
};

static PyMethodDef WPPipewireObject_methods[] = {
    {
        "enum_params",
        (PyCFunction) WPPipewireObject_enum_params,
        METH_VARARGS | METH_KEYWORDS,
        "Enumerate PipeWire params by id and return list of spa pod dictionaries"
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
