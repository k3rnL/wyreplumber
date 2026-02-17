//
// Created by edaniel on 2/17/26.
//

#include "../wp_connection/wp_connection.h"
#include "wp_metadata.h"

typedef struct {
    WPConnection *conn;
    WPMetadata *self;
    gint32 subject;
    PyObject *result;
} IterateData;

// This runs on the WP thread (in the GMainLoop context)
static gboolean do_iterate_on_wp_thread(gpointer user_data) {
    IterateData *data = user_data;

    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *list = PyList_New(0);
    if (!list) {
        data->result = NULL;
        PyGILState_Release(gstate);
        goto done;
    }

    WpIterator *it = wp_metadata_new_iterator(data->self->metadata, data->subject);
    g_auto(GValue) val = G_VALUE_INIT;

    while (wp_iterator_next(it, &val)) {
        guint32 item_subject;
        const gchar *item_key = NULL;
        const gchar *item_type = NULL;
        const gchar *item_value = NULL;

        // Use wp_metadata_iterator_item_extract for older WirePlumber versions
        wp_metadata_iterator_item_extract(&val, &item_subject, &item_key, &item_type, &item_value);

        PyObject *dict = PyDict_New();
        if (!dict) {
            g_value_unset(&val);
            Py_DECREF(list);
            wp_iterator_unref(it);
            data->result = NULL;
            PyGILState_Release(gstate);
            goto done;
        }

        PyObject *py_subject = PyLong_FromUnsignedLong(item_subject);
        PyObject *py_key = PyUnicode_FromString(item_key ? item_key : "");
        PyObject *py_type = item_type ? PyUnicode_FromString(item_type) : Py_None;
        PyObject *py_value = item_value ? PyUnicode_FromString(item_value) : Py_None;

        if (py_type == Py_None) Py_INCREF(Py_None);
        if (py_value == Py_None) Py_INCREF(Py_None);

        PyDict_SetItemString(dict, "subject", py_subject);
        PyDict_SetItemString(dict, "key", py_key);
        PyDict_SetItemString(dict, "type", py_type);
        PyDict_SetItemString(dict, "value", py_value);

        Py_DECREF(py_subject);
        Py_DECREF(py_key);
        Py_DECREF(py_type);
        Py_DECREF(py_value);

        PyList_Append(list, dict);
        Py_DECREF(dict);

        g_value_unset(&val);
    }

    wp_iterator_unref(it);
    data->result = list;

    PyGILState_Release(gstate);

done:
    // Signal that the call is complete
    g_mutex_lock(&data->conn->call_lock);
    data->conn->call_completed = TRUE;
    g_cond_signal(&data->conn->call_cond);
    g_mutex_unlock(&data->conn->call_lock);

    return G_SOURCE_REMOVE;
}

PyObject *WPMetadata_iterate(WPMetadata *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"subject", NULL};
    PyObject *subject_obj = NULL;
    gint32 subject = -1; // -1 means iterate all

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|O", kwlist, &subject_obj)) {
        return NULL;
    }

    if (subject_obj && subject_obj != Py_None) {
        if (!PyLong_Check(subject_obj)) {
            PyErr_SetString(PyExc_TypeError, "subject must be an integer");
            return NULL;
        }
        subject = PyLong_AsLong(subject_obj);
    }

    if (!self->metadata) {
        PyErr_SetString(PyExc_RuntimeError, "Metadata object is invalid");
        return NULL;
    }

    if (!self->conn) {
        PyErr_SetString(PyExc_RuntimeError, "Connection object is invalid");
        return NULL;
    }

    WPConnection *conn = (WPConnection *)self->conn;

    IterateData data = {
        .conn = conn,
        .self = self,
        .subject = subject,
        .result = NULL
    };

    // Reset call state
    g_mutex_lock(&conn->call_lock);
    conn->call_completed = FALSE;
    g_mutex_unlock(&conn->call_lock);

    // Schedule the work on the WP thread's main context
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_iterate_on_wp_thread, &data, NULL);
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
            PyErr_SetString(PyExc_RuntimeError, "Failed to iterate metadata");
        }
        return NULL;
    }

    return data.result;
}
