//
// Created by edaniel on 2/6/26.
//

#include "wp_connection.h"
#include "../wp_module/wp_module.h"

typedef struct {
    WPConnection *conn;
    const char *name;
    const char *arguments;
    WpImplModule *result;
    GError *error;
} LoadModuleData;

// This runs on the WP thread (in the GMainLoop context)
static gboolean do_load_module_on_wp_thread(gpointer user_data) {
    LoadModuleData *data = user_data;
    WPConnection *conn = data->conn;

    // Load the module on the WP thread
    WpImplModule *module = wp_impl_module_load(conn->core, data->name, data->arguments, NULL);

    if (!module) {
        data->error = g_error_new(G_IO_ERROR, G_IO_ERROR_FAILED,
                                  "Failed to load module '%s'", data->name);
        data->result = NULL;
    } else {
        data->result = module;
    }

    // Signal that the call is complete
    g_mutex_lock(&conn->call_lock);
    conn->call_completed = TRUE;
    g_cond_signal(&conn->call_cond);
    g_mutex_unlock(&conn->call_lock);

    return G_SOURCE_REMOVE;
}

PyObject *WPConnection_load_module(WPConnection *self, PyObject *args, PyObject *kwargs) {
    const char *name = NULL;
    const char *arguments = NULL;

    static char *kwlist[] = {"name", "arguments", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s|z", kwlist, &name, &arguments)) {
        return NULL;
    }

    LoadModuleData data = {
        .conn = self,
        .name = name,
        .arguments = arguments,
        .result = NULL,
        .error = NULL
    };

    // Reset call state
    g_mutex_lock(&self->call_lock);
    self->call_completed = FALSE;
    g_mutex_unlock(&self->call_lock);

    // Schedule the work on the WP thread's main context
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_load_module_on_wp_thread, &data, NULL);
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

    // Check for errors
    if (data.error) {
        PyErr_SetString(PyExc_RuntimeError, data.error->message);
        g_error_free(data.error);
        return NULL;
    }

    if (!data.result) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to load module");
        return NULL;
    }

    // Create Python wrapper for the module
    PyObject *py_module = WPModule_from_wp_module(data.result, self->core);

    // We don't unref data.result here because WPModule_from_wp_module refs it
    // and it's now managed by the object manager

    return py_module;
}
