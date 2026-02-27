//
// Created by edaniel on 2/5/26.
//

#include "wp_node.h"
#include "../wp_port/wp_port.h"
#include <pipewire/keys.h>

// Forward declarations
static void WPNode_dealloc(WPNode *self);
static PyObject *WPNode_repr(WPNode *self);
static PyObject *WPNode_get_id(WPNode *self, void *closure);
static PyObject *WPNode_get_properties(WPNode *self, void *closure);
static PyObject *WPNode_get_state(WPNode *self, void *closure);
static PyObject *WPNode_get_n_input_ports(WPNode *self, void *closure);
static PyObject *WPNode_get_max_input_ports(WPNode *self, void *closure);
static PyObject *WPNode_get_n_output_ports(WPNode *self, void *closure);
static PyObject *WPNode_get_max_output_ports(WPNode *self, void *closure);
static PyObject *WPNode_get_error_message(WPNode *self, void *closure);
static PyObject *WPNode_delete(WPNode *self, PyObject *Py_UNUSED(ignored));
static PyObject *WPNode_get_ports(WPNode *self, PyObject *args, PyObject *kwargs);

static void WPNode_dealloc(WPNode *self) {
    if (self->node) {
        g_object_unref(self->node);
        self->node = NULL;
    }
    if (self->core) {
        g_object_unref(self->core);
        self->core = NULL;
    }
    if (self->om) {
        g_object_unref(self->om);
        self->om = NULL;
    }
    Py_XDECREF(self->properties);
    if (self->error_message) {
        free(self->error_message);
        self->error_message = NULL;
    }
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *WPNode_repr(WPNode *self) {
    guint32 id = wp_proxy_get_bound_id(WP_PROXY(self->node));
    return PyUnicode_FromFormat("<WPNode id=%u>", id);
}

static PyObject *WPNode_get_id(WPNode *self, void *closure) {
    guint32 id = wp_proxy_get_bound_id(WP_PROXY(self->node));
    return PyLong_FromUnsignedLong(id);
}

static PyObject *WPNode_get_properties(WPNode *self, void *closure) {
    Py_INCREF(self->properties);
    return self->properties;
}

static PyObject *WPNode_get_state(WPNode *self, void *closure) {
    return PyLong_FromLong(self->state);
}

static PyObject *WPNode_get_n_input_ports(WPNode *self, void *closure) {
    return PyLong_FromUnsignedLong(self->n_input_ports);
}

static PyObject *WPNode_get_max_input_ports(WPNode *self, void *closure) {
    return PyLong_FromUnsignedLong(self->max_input_ports);
}

static PyObject *WPNode_get_n_output_ports(WPNode *self, void *closure) {
    return PyLong_FromUnsignedLong(self->n_output_ports);
}

static PyObject *WPNode_get_max_output_ports(WPNode *self, void *closure) {
    return PyLong_FromUnsignedLong(self->max_output_ports);
}

static PyObject *WPNode_get_error_message(WPNode *self, void *closure) {
    if (self->error_message) {
        return PyUnicode_FromString(self->error_message);
    }
    Py_RETURN_NONE;
}

static PyObject *WPNode_delete(WPNode *self, PyObject *Py_UNUSED(ignored)) {
    if (!self->node) {
        PyErr_SetString(PyExc_RuntimeError, "Node already deleted or invalid");
        return NULL;
    }

    // Request destruction of the node
    wp_global_proxy_request_destroy(WP_GLOBAL_PROXY(self->node));

    // Mark as deleted by unreffing and NULLing the node
    // This prevents double-delete
    g_object_unref(self->node);
    self->node = NULL;

    Py_RETURN_NONE;
}

static PyObject *WPNode_get_ports(WPNode *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"direction", NULL};
    PyObject *direction_obj = NULL;
    int direction_filter = -1; // -1 means no filter

    // Parse optional direction argument
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|O", kwlist, &direction_obj)) {
        return NULL;
    }

    if (direction_obj && direction_obj != Py_None) {
        if (!PyLong_Check(direction_obj)) {
            PyErr_SetString(PyExc_TypeError, "direction must be an integer (WP_DIRECTION_INPUT or WP_DIRECTION_OUTPUT)");
            return NULL;
        }
        direction_filter = PyLong_AsLong(direction_obj);
        if (direction_filter != WP_DIRECTION_INPUT && direction_filter != WP_DIRECTION_OUTPUT) {
            PyErr_SetString(PyExc_ValueError, "direction must be WP_DIRECTION_INPUT or WP_DIRECTION_OUTPUT");
            return NULL;
        }
    }

    if (!self->om) {
        PyErr_SetString(PyExc_RuntimeError, "Object manager not available");
        return NULL;
    }

    // Create Python list to hold ports
    PyObject *list = PyList_New(0);
    if (!list) return NULL;

    // Get node ID for filtering
    guint32 node_id = wp_proxy_get_bound_id(WP_PROXY(self->node));

    // Iterate through all ports in object manager
    g_autoptr(WpIterator) it = wp_object_manager_new_iterator(WP_OBJECT_MANAGER(self->om));
    g_auto(GValue) val = G_VALUE_INIT;

    while (wp_iterator_next(it, &val)) {
        WpPort *port = g_value_get_object(&val);
        if (!WP_IS_PORT(port)) {
            g_value_unset(&val);
            continue;
        }

        // Check if port belongs to this node
        WpProperties *port_props = wp_pipewire_object_get_properties(WP_PIPEWIRE_OBJECT(port));
        const char *port_node_id_str = wp_properties_get(port_props, PW_KEY_NODE_ID);
        if (!port_node_id_str) {
            g_value_unset(&val);
            continue;
        }

        guint32 port_node_id = atoi(port_node_id_str);
        if (port_node_id != node_id) {
            g_value_unset(&val);
            continue;
        }

        // Check if port has required features
        WpObjectFeatures features = wp_object_get_active_features(WP_OBJECT(port));
        if (!(features & WP_PROXY_FEATURE_BOUND) || !(features & WP_PIPEWIRE_OBJECT_FEATURE_INFO)) {
            g_value_unset(&val);
            continue;
        }

        // Filter by direction if specified
        if (direction_filter != -1) {
            WpDirection port_direction = wp_port_get_direction(port);
            if (port_direction != direction_filter) {
                g_value_unset(&val);
                continue;
            }
        }

        // Create WPPort Python object
        PyObject *py_port = WPPort_from_wp_port(port, self->core);
        if (!py_port) {
            g_value_unset(&val);
            Py_DECREF(list);
            return NULL;
        }

        PyList_Append(list, py_port);
        Py_DECREF(py_port);

        g_value_unset(&val);
    }

    return list;
}

static PyGetSetDef WPNode_getsetters[] = {
    {"id", (getter)WPNode_get_id, NULL, "Node ID", NULL},
    {"properties", (getter)WPNode_get_properties, NULL, "All node properties", NULL},
    {"state", (getter)WPNode_get_state, NULL, "Node state (WP_NODE_STATE_*)", NULL},
    {"n_input_ports", (getter)WPNode_get_n_input_ports, NULL, "Number of input ports", NULL},
    {"max_input_ports", (getter)WPNode_get_max_input_ports, NULL, "Maximum input ports", NULL},
    {"n_output_ports", (getter)WPNode_get_n_output_ports, NULL, "Number of output ports", NULL},
    {"max_output_ports", (getter)WPNode_get_max_output_ports, NULL, "Maximum output ports", NULL},
    {"error_message", (getter)WPNode_get_error_message, NULL, "Error message if state is ERROR", NULL},
    {NULL}
};

static PyMethodDef WPNode_methods[] = {
    {"delete", (PyCFunction)WPNode_delete, METH_NOARGS, "Delete this node from the server"},
    {"get_ports", (PyCFunction)WPNode_get_ports, METH_VARARGS | METH_KEYWORDS, "Get ports of this node, optionally filtered by direction"},
    {NULL}
};

PyTypeObject WPNodeType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_core.WPNode",
    .tp_doc = "WirePlumber Node Object",
    .tp_basicsize = sizeof(WPNode),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT,
    .tp_repr = (reprfunc)WPNode_repr,
    .tp_dealloc = (destructor)WPNode_dealloc,
    .tp_methods = WPNode_methods,
    .tp_getset = WPNode_getsetters,
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

PyObject *WPNode_from_wp_node(WpNode *wp_node, WpCore *core, WpObject *om) {
    WPNode *self = (WPNode *)WPNodeType.tp_alloc(&WPNodeType, 0);
    if (!self) return NULL;

    // Store references
    self->node = g_object_ref(wp_node);
    self->core = g_object_ref(core);
    self->om = om ? g_object_ref(om) : NULL;

    // Get all properties
    WpProperties *props = wp_pipewire_object_get_properties(WP_PIPEWIRE_OBJECT(wp_node));
    self->properties = iterate_wp_properties(props);
    if (!self->properties) {
        Py_DECREF(self);
        return NULL;
    }

    // Get state
    const char *error_msg = NULL;
    self->state = wp_node_get_state(wp_node, &error_msg);
    if (error_msg) {
        self->error_message = strdup(error_msg);
    } else {
        self->error_message = NULL;
    }

    // Get port information
    self->n_input_ports = wp_node_get_n_input_ports(wp_node, &self->max_input_ports);
    self->n_output_ports = wp_node_get_n_output_ports(wp_node, &self->max_output_ports);

    return (PyObject *)self;
}
