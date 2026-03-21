//
// Created by edaniel on 2/11/26.
//

#include "wp_port.h"

// Forward declarations
static void WPPort_dealloc(WPPort *self);
static PyObject *WPPort_repr(WPPort *self);
static PyObject *WPPort_get_direction(WPPort *self, void *closure);

static void WPPort_dealloc(WPPort *self) {
    WPPipewireObject_clear(&self->base);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *WPPort_repr(WPPort *self) {
    const char *direction_str = (self->direction == WP_DIRECTION_INPUT) ? "input" : "output";
    return PyUnicode_FromFormat("<WPPort id=%u direction=%s>", self->base.id, direction_str);
}

static PyObject *WPPort_get_direction(WPPort *self, void *closure) {
    return PyLong_FromLong(self->direction);
}

static PyGetSetDef WPPort_getsetters[] = {
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
    .tp_base = &WPPipewireObjectType,
    .tp_repr = (reprfunc)WPPort_repr,
    .tp_dealloc = (destructor)WPPort_dealloc,
    .tp_methods = WPPort_methods,
    .tp_getset = WPPort_getsetters,
};

PyObject *WPPort_from_wp_port(WpPort *wp_port, WpCore *core, struct WPConnection *conn) {
    WPPort *self = (WPPort *)WPPortType.tp_alloc(&WPPortType, 0);
    if (!self) return NULL;

    if (!WPPipewireObject_init_from_wp_pipewire_object(
            &self->base, WP_PIPEWIRE_OBJECT(wp_port), core, conn)) {
        Py_DECREF(self);
        return NULL;
    }

    // Get port direction
    self->direction = wp_port_get_direction(wp_port);

    return (PyObject *)self;
}
