//
// Created by edaniel on 2/17/26.
//

#include "../wp_connection/wp_connection.h"
#include "wp_metadata.h"

typedef struct {
    WPConnection *conn;
    WPMetadata *self;
    guint32 subject;
    const char *key;
    PyObject *result;
} FindData;

// This runs on the WP thread (in the GMainLoop context)
static gboolean do_find_on_wp_thread(gpointer user_data) {
    FindData *data = user_data;

    PyGILState_STATE gstate = PyGILState_Ensure();

    const gchar *type = NULL;
    const gchar *value = wp_metadata_find(data->self->metadata, data->subject, data->key, &type);

    if (!value) {
        Py_INCREF(Py_None);
        data->result = Py_None;
    } else {
        PyObject *py_value = PyUnicode_FromString(value);
        PyObject *py_type = type ? PyUnicode_FromString(type) : Py_None;
        if (py_type == Py_None) {
            Py_INCREF(Py_None);
        }

        data->result = PyTuple_Pack(2, py_value, py_type);
        Py_DECREF(py_value);
        Py_DECREF(py_type);
    }

    PyGILState_Release(gstate);

    // Signal that the call is complete
    g_mutex_lock(&data->conn->call_lock);
    data->conn->call_completed = TRUE;
    g_cond_signal(&data->conn->call_cond);
    g_mutex_unlock(&data->conn->call_lock);

    return G_SOURCE_REMOVE;
}

PyObject *WPMetadata_find(WPMetadata *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"subject", "key", NULL};
    guint32 subject;
    const char *key;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "Is", kwlist, &subject, &key)) {
        return NULL;
    }

    if (!self->metadata) {
        PyErr_SetString(PyExc_RuntimeError, "Metadata object is invalid");
        return NULL;
    }

    if (!self->connection) {
        PyErr_SetString(PyExc_RuntimeError, "Connection object is invalid");
        return NULL;
    }

    WPConnection *conn = (WPConnection *)self->connection;

    FindData data = {
        .conn = conn,
        .self = self,
        .subject = subject,
        .key = key,
        .result = NULL
    };

    // Reset call state
    g_mutex_lock(&conn->call_lock);
    conn->call_completed = FALSE;
    g_mutex_unlock(&conn->call_lock);

    // Schedule the work on the WP thread's main context
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_find_on_wp_thread, &data, NULL);
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

    // Return the result
    if (!data.result) {
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_RuntimeError, "Failed to find metadata");
        }
        return NULL;
    }

    return data.result;
}
