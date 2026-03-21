#ifndef PYPEWIRE_WP_PIPEWIRE_OBJECT_H
#define PYPEWIRE_WP_PIPEWIRE_OBJECT_H

#include <Python.h>
#include <wp/wp.h>

struct WPConnection;

typedef struct {
    PyObject_HEAD
    WpPipewireObject *pipewire_object;
    WpCore *core;
    PyObject *connection;   // Strong reference to WPConnection
    PyObject *properties;   // Dict of all properties
    guint32 id;
} WPPipewireObject;

extern PyTypeObject WPPipewireObjectType;

gboolean WPPipewireObject_init_from_wp_pipewire_object(
    WPPipewireObject *self,
    WpPipewireObject *wp_pipewire_object,
    WpCore *core,
    struct WPConnection *conn);

void WPPipewireObject_clear(WPPipewireObject *self);

#endif //PYPEWIRE_WP_PIPEWIRE_OBJECT_H
