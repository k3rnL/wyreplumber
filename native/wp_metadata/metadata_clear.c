//
// Created by edaniel on 2/17/26.
//

#include "../wp_connection/wp_connection.h"
#include "wp_metadata.h"

typedef struct {
    WPConnection *conn;
    WPMetadata *self;
    gboolean success;
} ClearData;

// This runs on the WP thread (in the GMainLoop context)
static gboolean do_clear_on_wp_thread(gpointer user_data) {
    ClearData *data = user_data;

    wp_metadata_clear(data->self->metadata);

    data->success = TRUE;

    // Signal that the call is complete
    g_mutex_lock(&data->conn->call_lock);
    data->conn->call_completed = TRUE;
    g_cond_signal(&data->conn->call_cond);
    g_mutex_unlock(&data->conn->call_lock);

    return G_SOURCE_REMOVE;
}

PyObject *WPMetadata_clear(WPMetadata *self, PyObject *Py_UNUSED(ignored)) {
    if (!self->metadata) {
        PyErr_SetString(PyExc_RuntimeError, "Metadata object is invalid");
        return NULL;
    }

    if (!self->conn) {
        PyErr_SetString(PyExc_RuntimeError, "Connection object is invalid");
        return NULL;
    }

    WPConnection *conn = (WPConnection *)self->conn;

    ClearData data = {
        .conn = conn,
        .self = self,
        .success = FALSE
    };

    // Reset call state
    g_mutex_lock(&conn->call_lock);
    conn->call_completed = FALSE;
    g_mutex_unlock(&conn->call_lock);

    // Schedule the work on the WP thread's main context
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_clear_on_wp_thread, &data, NULL);
    g_source_attach(source, conn->ctx);
    g_source_unref(source);

    // Release GIL and wait for the WP thread to complete the work
    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&conn->call_lock);
    while (!conn->call_completed) {
        g_cond_wait(&conn->call_cond, &conn->call_lock);
    }
    g_mutex_unlock(&conn->call_lock);
    Py_END_ALLOW_THREADS

    if (!data.success) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to clear metadata");
        return NULL;
    }

    // Sync to ensure metadata is cleared
    // wp_connection_sync sets Python exception on failure
    if (!wp_connection_sync(conn)) {
        return NULL;
    }

    Py_RETURN_NONE;
}
