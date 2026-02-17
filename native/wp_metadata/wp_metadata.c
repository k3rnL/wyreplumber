//
// Created by edaniel on 2/11/26.
//

#include "../wp_connection/wp_connection.h"
#include "wp_metadata.h"

// Forward declarations
static void WPMetadata_dealloc(WPMetadata *self);
static PyObject *WPMetadata_repr(WPMetadata *self);
static PyObject *WPMetadata_get_id(WPMetadata *self, void *closure);
static PyObject *WPMetadata_get_properties(WPMetadata *self, void *closure);

static void WPMetadata_dealloc(WPMetadata *self) {
    if (self->metadata) {
        g_object_unref(self->metadata);
        self->metadata = NULL;
    }
    if (self->core) {
        g_object_unref(self->core);
        self->core = NULL;
    }
    Py_XDECREF(self->properties);
    // Note: conn is not ref-counted, it's a weak reference
    self->conn = NULL;
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *WPMetadata_repr(WPMetadata *self) {
    return PyUnicode_FromFormat("<WPMetadata id=%u>", self->id);
}

static PyObject *WPMetadata_get_id(WPMetadata *self, void *closure) {
    return PyLong_FromUnsignedLong(self->id);
}

static PyObject *WPMetadata_get_properties(WPMetadata *self, void *closure) {
    Py_INCREF(self->properties);
    return self->properties;
}

static PyGetSetDef WPMetadata_getsetters[] = {
    {"id", (getter)WPMetadata_get_id, NULL, "Metadata ID", NULL},
    {"properties", (getter)WPMetadata_get_properties, NULL, "All metadata properties", NULL},
    {NULL}
};

static PyMethodDef WPMetadata_methods[] = {
    {"find", (PyCFunction)WPMetadata_find, METH_VARARGS | METH_KEYWORDS,
     "Find metadata value by subject and key. Returns tuple (value, type) or None."},
    {"set", (PyCFunction)WPMetadata_set, METH_VARARGS | METH_KEYWORDS,
     "Set metadata for a subject and key. Pass None as value to unset."},
    {"clear", (PyCFunction)WPMetadata_clear, METH_NOARGS,
     "Remove all stored metadata."},
    {"iterate", (PyCFunction)WPMetadata_iterate, METH_VARARGS | METH_KEYWORDS,
     "Iterate metadata items, optionally filtered by subject. Returns list of dicts."},
    {NULL}
};

PyTypeObject WPMetadataType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_core.WPMetadata",
    .tp_doc = "WirePlumber Metadata Object",
    .tp_basicsize = sizeof(WPMetadata),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_repr = (reprfunc)WPMetadata_repr,
    .tp_dealloc = (destructor)WPMetadata_dealloc,
    .tp_methods = WPMetadata_methods,
    .tp_getset = WPMetadata_getsetters,
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

PyObject *WPMetadata_from_wp_metadata(WpMetadata *wp_metadata, WpCore *core, struct WPConnection *conn) {
    WPMetadata *self = (WPMetadata *)WPMetadataType.tp_alloc(&WPMetadataType, 0);
    if (!self) return NULL;

    // Store references
    self->metadata = g_object_ref(wp_metadata);
    self->core = g_object_ref(core);
    self->conn = conn;  // Weak reference, no ref counting

    // Get metadata ID
    self->id = wp_proxy_get_bound_id(WP_PROXY(wp_metadata));

    // Get all properties - use wp_global_proxy_get_global_properties since metadata is a WpGlobalProxy
    WpProperties *props = wp_global_proxy_get_global_properties(WP_GLOBAL_PROXY(wp_metadata));
    self->properties = iterate_wp_properties(props);
    if (!self->properties) {
        Py_DECREF(self);
        return NULL;
    }

    return (PyObject *)self;
}
