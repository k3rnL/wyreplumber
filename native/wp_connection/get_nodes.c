//
// Created by edaniel on 2/5/26.
//

#include "wp_connection.h"
#include "../wp_node/wp_node.h"

typedef struct {
    WPConnection *conn;
    PyObject *result;
} GetNodesData;

// This runs on the WP thread (in the GMainLoop context)
static gboolean do_get_nodes_on_wp_thread(gpointer user_data) {
    GetNodesData *data = user_data;
    WPConnection *conn = data->conn;

    // We're on the WP thread, safe to access conn->om
    g_autoptr(WpIterator) it = wp_object_manager_new_iterator(conn->om);
    g_auto(GValue) val = G_VALUE_INIT;

    // Create the Python list (must acquire GIL since we're creating Python objects)
    const PyGILState_STATE gstate = PyGILState_Ensure();

    PyObject *list = PyList_New(0);
    if (!list) {
        PyGILState_Release(gstate);
        data->result = NULL;
        goto done;
    }

    // Iterate over all nodes
    while (wp_iterator_next(it, &val)) {
        WpNode *node = g_value_get_object(&val);
        if (!WP_IS_NODE(node)) {
            g_value_unset(&val);
            continue;
        }

        // Check if the object has the required features
        const WpObjectFeatures features = wp_object_get_active_features(WP_OBJECT(node));
        if (!(features & WP_PROXY_FEATURE_BOUND) || !(features & WP_PIPEWIRE_OBJECT_FEATURE_INFO)) {
            // Skip nodes that don't have features activated yet
            g_value_unset(&val);
            continue;
        }

        // Create WPNode Python object
        PyObject *py_node = WPNode_from_wp_node(
            node, conn->core, WP_OBJECT(conn->om), (struct WPConnection *) conn);
        if (!py_node) {
            g_value_unset(&val);
            Py_DECREF(list);
            list = NULL;
            break;
        }

        PyList_Append(list, py_node);
        Py_DECREF(py_node);

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

PyObject *WPConnection_get_nodes(WPConnection *self, PyObject *Py_UNUSED(ignored)) {
    GetNodesData data = {
        .conn = self,
        .result = NULL
    };

    // Reset call state
    g_mutex_lock(&self->call_lock);
    self->call_completed = FALSE;
    g_mutex_unlock(&self->call_lock);

    // Schedule the work on the WP thread's main context
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_get_nodes_on_wp_thread, &data, NULL);
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
            PyErr_SetString(PyExc_RuntimeError, "Failed to retrieve nodes");
        }
        return NULL;
    }

    return data.result;
}
