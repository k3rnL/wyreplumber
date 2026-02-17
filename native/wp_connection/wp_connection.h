//
// Created by edaniel on 2/5/26.
//

#ifndef PYPEWIRE_WP_CONNECTION_H
#define PYPEWIRE_WP_CONNECTION_H

#include <Python.h>
#include <wp/wp.h>

typedef struct {
    PyObject_HEAD
    GThread *thread;
    GMainContext *ctx;
    GMainLoop *loop;

    // WirePlumber objects (ONLY touched on WP thread)
    WpCore *core;
    WpObjectManager *om;

    // State / sync
    GMutex lock;
    GCond cond;
    gboolean started;
    gboolean stop_requested;
    GError *start_error;

    // For async calls from Python thread to WP thread
    GMutex call_lock;
    GCond call_cond;
    gboolean call_completed;
    gpointer call_result;
    GError *call_error;  // For storing errors from async operations
} WPConnection;

extern PyTypeObject WPConnectionType;

// Method declarations
PyObject *WPConnection_get_nodes(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_get_modules(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_get_metadata(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_load_module(WPConnection *self, PyObject *args, PyObject *kwargs);

// Helper function for synchronous wp_core_sync
gboolean wp_connection_sync(WPConnection *conn);

#endif //PYPEWIRE_WP_CONNECTION_H