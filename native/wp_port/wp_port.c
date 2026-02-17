//
// Created by edaniel on 2/11/26.
//

#include "wp_port.h"

// Forward declarations
static void WPPort_dealloc(WPPort *self);
static PyObject *WPPort_repr(WPPort *self);
static PyObject *WPPort_get_id(WPPort *self, void *closure);
static PyObject *WPPort_get_properties(WPPort *self, void *closure);
static PyObject *WPPort_get_direction(WPPort *self, void *closure);

static void WPPort_dealloc(WPPort *self) {
    if (self->port) {
        g_object_unref(self->port);
        self->port = NULL;
    }
    if (self->core) {
        g_object_unref(self->core);
        self->core = NULL;
    }
    Py_XDECREF(self->properties);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *WPPort_repr(WPPort *self) {
    const char *direction_str = (self->direction == WP_DIRECTION_INPUT) ? "input" : "output";
    return PyUnicode_FromFormat("<WPPort id=%u direction=%s>", self->id, direction_str);
}

static PyObject *WPPort_get_id(WPPort *self, void *closure) {
    return PyLong_FromUnsignedLong(self->id);
}

static PyObject *WPPort_get_properties(WPPort *self, void *closure) {
    Py_INCREF(self->properties);
    return self->properties;
}

static PyObject *WPPort_get_direction(WPPort *self, void *closure) {
    return PyLong_FromLong(self->direction);
}

static PyGetSetDef WPPort_getsetters[] = {
    {"id", (getter)WPPort_get_id, NULL, "Port ID", NULL},
    {"properties", (getter)WPPort_get_properties, NULL, "All port properties", NULL},
    {"direction", (getter)WPPort_get_direction, NULL, "Port direction (WP_DIRECTION_INPUT or WP_DIRECTION_OUTPUT)", NULL},
    {NULL}
};

static PyMethodDef WPPort_methods[] = {
    {NULL}
};

PyTypeObject WPPortType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_core.WPPort",
    .tp_doc = "WirePlumber Port Object",
    .tp_basicsize = sizeof(WPPort),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_repr = (reprfunc)WPPort_repr,
    .tp_dealloc = (destructor)WPPort_dealloc,
    .tp_methods = WPPort_methods,
    .tp_getset = WPPort_getsetters,
};

// Helper to iterate over all properties
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
            PyDict_SetItemString(dict, key, py_value);
            Py_DECREF(py_value);
        }

        g_value_unset(&item);
    }

    wp_iterator_unref(it);
    return dict;
}

PyObject *WPPort_from_wp_port(WpPort *wp_port, WpCore *core) {
    WPPort *self = (WPPort *)WPPortType.tp_alloc(&WPPortType, 0);
    if (!self) return NULL;

    // Store references
    self->port = g_object_ref(wp_port);
    self->core = g_object_ref(core);

    // Get port ID
    self->id = wp_proxy_get_bound_id(WP_PROXY(wp_port));

    // Get port direction
    self->direction = wp_port_get_direction(wp_port);

    // Get all properties
    WpProperties *props = wp_pipewire_object_get_properties(WP_PIPEWIRE_OBJECT(wp_port));
    self->properties = iterate_wp_properties(props);
    if (!self->properties) {
        Py_DECREF(self);
        return NULL;
    }

    return (PyObject *)self;
}
