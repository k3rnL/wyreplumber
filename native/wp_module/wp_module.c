//
// Created by edaniel on 2/6/26.
//

#include "wp_module.h"
#include "../wp_connection/wp_connection.h"

// Forward declarations
static void WPModule_dealloc(WPModule *self);
static PyObject *WPModule_repr(WPModule *self);
static PyObject *WPModule_get_name(WPModule *self, void *closure);
static PyObject *WPModule_get_arguments(WPModule *self, void *closure);
static PyObject *WPModule_get_properties(WPModule *self, void *closure);
static PyObject *WPModule_unload(WPModule *self, PyObject *Py_UNUSED(ignored));

static void WPModule_dealloc(WPModule *self) {
    if (self->module && G_IS_OBJECT(self->module)) {
        g_object_unref(self->module);
        self->module = NULL;
    }
    if (self->core && G_IS_OBJECT(self->core)) {
        g_object_unref(self->core);
        self->core = NULL;
    }
    // Don't unref conn - we don't own it, it's just a weak reference
    self->conn = NULL;

    Py_XDECREF(self->properties);
    if (self->name) {
        free(self->name);
        self->name = NULL;
    }
    if (self->arguments) {
        free(self->arguments);
        self->arguments = NULL;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *WPModule_repr(WPModule *self) {
    const char *name = self->name ? self->name : "unknown";
    return PyUnicode_FromFormat("<WPModule name='%s'>", name);
}

static PyObject *WPModule_get_name(WPModule *self, void *closure) {
    if (self->name) {
        return PyUnicode_FromString(self->name);
    }
    Py_RETURN_NONE;
}

static PyObject *WPModule_get_arguments(WPModule *self, void *closure) {
    if (self->arguments) {
        return PyUnicode_FromString(self->arguments);
    }
    Py_RETURN_NONE;
}

static PyObject *WPModule_get_properties(WPModule *self, void *closure) {
    Py_INCREF(self->properties);
    return self->properties;
}

static PyGetSetDef WPModule_getsetters[] = {
    {"name", (getter)WPModule_get_name, NULL, "Module name", NULL},
    {"arguments", (getter)WPModule_get_arguments, NULL, "Module arguments", NULL},
    {"properties", (getter)WPModule_get_properties, NULL, "All module properties", NULL},
    {NULL}
};

static PyMethodDef WPModule_methods[] = {
    {NULL}
};

PyTypeObject WPModuleType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_core.WPModule",
    .tp_doc = "WirePlumber Module Object",
    .tp_basicsize = sizeof(WPModule),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_repr = (reprfunc)WPModule_repr,
    .tp_dealloc = (destructor)WPModule_dealloc,
    .tp_methods = WPModule_methods,
    .tp_getset = WPModule_getsetters,
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

PyObject *WPModule_from_wp_module(WpImplModule *wp_module, WpCore *core, WPConnection *conn) {
    WPModule *self = (WPModule *)WPModuleType.tp_alloc(&WPModuleType, 0);
    if (!self) return NULL;

    // Initialize all pointers to NULL first
    self->module = NULL;
    self->core = NULL;
    self->conn = NULL;
    self->properties = NULL;
    self->name = NULL;
    self->arguments = NULL;

    // Store references
    self->module = g_object_ref(wp_module);
    self->core = g_object_ref(core);
    self->conn = conn;  // Weak reference - don't ref

    // WpImplModule is a GObject, not a WpPipeWireObject, so we get properties using GObject API
    self->properties = PyDict_New();
    if (!self->properties) {
        Py_DECREF(self);
        return NULL;
    }

    // Get name and arguments from GObject properties
    gchar *name = NULL;
    gchar *arguments = NULL;
    g_object_get(G_OBJECT(wp_module),
                 "name", &name,
                 "arguments", &arguments,
                 NULL);

    if (name) {
        self->name = strdup(name);
        PyObject *py_name = PyUnicode_FromString(name);
        PyDict_SetItemString(self->properties, "name", py_name);
        Py_DECREF(py_name);
        g_free(name);
    }

    if (arguments) {
        self->arguments = strdup(arguments);
        PyObject *py_args = PyUnicode_FromString(arguments);
        PyDict_SetItemString(self->properties, "arguments", py_args);
        Py_DECREF(py_args);
        g_free(arguments);
    }

    return (PyObject *)self;
}
