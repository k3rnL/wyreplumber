//
// Created by edaniel on 2/6/26.
//

#include "wp_connection.h"
#include "../wp_module/wp_module.h"

typedef struct {
    WPConnection *conn;
    PyObject *result;
} GetModulesData;

// This runs on the WP thread (in the GMainLoop context)
static gboolean do_get_modules_on_wp_thread(gpointer user_data) {
    GetModulesData *data = user_data;
    WPConnection *conn = data->conn;

    // We're on the WP thread, safe to access conn->om
    g_autoptr(WpIterator) it = wp_object_manager_new_iterator(conn->om);
    g_auto(GValue) val = G_VALUE_INIT;

    // Create Python list (must acquire GIL since we're creating Python objects)
    PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *list = PyList_New(0);
    if (!list) {
        PyGILState_Release(gstate);
        data->result = NULL;
        goto done;
    }

    // Iterate over all modules
    while (wp_iterator_next(it, &val)) {
        WpImplModule *module = g_value_get_object(&val);
        if (!WP_IS_IMPL_MODULE(module)) {
            g_value_unset(&val);
            continue;
        }

        // WpImplModule is a GObject, not a WpObject, so no features to check

        // Create WPModule Python object
        PyObject *py_module = WPModule_from_wp_module(module, conn->core);
        if (!py_module) {
            g_value_unset(&val);
            Py_DECREF(list);
            list = NULL;
            break;
        }

        PyList_Append(list, py_module);
        Py_DECREF(py_module);

        g_value_unset(&val);
    }

    data->result = list;
    PyGILState_Release(gstate);

done:
    // Signal that the call is complete
    g_mutex_lock(&conn->call_lock);
    conn->call_completed = TRUE;
    g_cond_signal(&conn->call_cond);
    g_mutex_unlock(&conn->call_lock);

    return G_SOURCE_REMOVE;
}

PyObject *WPConnection_get_modules(WPConnection *self, PyObject *Py_UNUSED(ignored)) {
    GetModulesData data = {
        .conn = self,
        .result = NULL
    };

    // Reset call state
    g_mutex_lock(&self->call_lock);
    self->call_completed = FALSE;
    g_mutex_unlock(&self->call_lock);

    // Schedule the work on the WP thread's main context
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_get_modules_on_wp_thread, &data, NULL);
    g_source_attach(source, self->ctx);
    g_source_unref(source);

    // Release GIL and wait for the WP thread to complete the work
    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&self->call_lock);
    while (!self->call_completed) {
        g_cond_wait(&self->call_cond, &self->call_lock);
    }
    g_mutex_unlock(&self->call_lock);
    Py_END_ALLOW_THREADS

    // Return the result (or NULL if error occurred)
    if (!data.result) {
        if (!PyErr_Occurred()) {
            PyErr_SetString(PyExc_RuntimeError, "Failed to retrieve modules");
        }
        return NULL;
    }

    return data.result;
}
