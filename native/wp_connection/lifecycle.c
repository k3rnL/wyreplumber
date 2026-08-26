#include "wp_connection.h"


typedef struct {
    WPConnection *conn;
    gboolean accepted;
} ReconnectData;


static gboolean reconnect_on_wp_thread(gpointer user_data) {
    ReconnectData *data = user_data;
    WPConnection *conn = data->conn;
    if (wp_core_is_connected(conn->core)) {
        wp_core_disconnect(conn->core);
    }
    data->accepted = wp_core_connect(conn->core);

    g_mutex_lock(&conn->call_lock);
    conn->call_completed = TRUE;
    g_cond_signal(&conn->call_cond);
    g_mutex_unlock(&conn->call_lock);
    return G_SOURCE_REMOVE;
}


PyObject *WPConnection_reconnect(
    WPConnection *self, PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"timeout", NULL};
    double timeout = 5.0;
    if (!PyArg_ParseTupleAndKeywords(
            args, kwargs, "|d:reconnect", kwlist, &timeout)) {
        return NULL;
    }
    if (timeout < 0) {
        PyErr_SetString(PyExc_ValueError, "timeout must be non-negative");
        return NULL;
    }
    if (!self->thread || !self->ctx || !self->core || self->stop_requested) {
        PyErr_SetString(PyExc_RuntimeError, "WirePlumber connection is stopped");
        return NULL;
    }

    wp_connection_mutations_cancel_pending(
        self, WP_MUTATION_CANCEL_GENERATION_LOST);

    g_mutex_lock(&self->lock);
    const guint64 previous_generation = self->generation;
    g_mutex_unlock(&self->lock);
    ReconnectData data = {.conn = self, .accepted = FALSE};

    g_mutex_lock(&self->call_lock);
    self->call_completed = FALSE;
    g_mutex_unlock(&self->call_lock);
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, reconnect_on_wp_thread, &data, NULL);
    g_source_attach(source, self->ctx);
    g_source_unref(source);

    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&self->call_lock);
    while (!self->call_completed) {
        g_cond_wait(&self->call_cond, &self->call_lock);
    }
    g_mutex_unlock(&self->call_lock);
    Py_END_ALLOW_THREADS
    if (!data.accepted) {
        PyErr_SetString(PyExc_RuntimeError, "WirePlumber reconnect was rejected");
        return NULL;
    }

    const gint64 deadline = g_get_monotonic_time() +
        (gint64) (timeout * G_TIME_SPAN_SECOND);
    gboolean connected = FALSE;
    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&self->lock);
    while (self->generation <= previous_generation && !self->stop_requested) {
        if (!g_cond_wait_until(&self->cond, &self->lock, deadline)) break;
    }
    connected = self->generation > previous_generation && self->om != NULL;
    g_mutex_unlock(&self->lock);
    Py_END_ALLOW_THREADS
    if (!connected) {
        PyErr_SetString(PyExc_TimeoutError, "WirePlumber reconnect timed out");
        return NULL;
    }
    return PyLong_FromUnsignedLongLong(self->generation);
}


typedef struct {
    WPConnection *conn;
} StopData;


static gboolean stop_on_wp_thread(gpointer user_data) {
    StopData *data = user_data;
    WPConnection *conn = data->conn;
    if (conn->core && wp_core_is_connected(conn->core)) {
        wp_core_disconnect(conn->core);
    }
    wp_connection_runtime_events_publish_connection(
        conn, "stopped", "runtime connection stopped");
    wp_connection_runtime_events_close(conn);
    if (conn->loop) g_main_loop_quit(conn->loop);
    return G_SOURCE_REMOVE;
}


PyObject *WPConnection_stop(WPConnection *self, PyObject *Py_UNUSED(ignored)) {
    if (!self->thread) Py_RETURN_NONE;

    g_mutex_lock(&self->lock);
    self->stop_requested = TRUE;
    g_cond_broadcast(&self->cond);
    g_mutex_unlock(&self->lock);
    wp_connection_mutations_cancel_pending(
        self, WP_MUTATION_CANCEL_RUNTIME_STOPPED);

    StopData data = {.conn = self};
    if (self->ctx) {
        GSource *source = g_idle_source_new();
        g_source_set_callback(source, stop_on_wp_thread, &data, NULL);
        g_source_attach(source, self->ctx);
        g_source_unref(source);
    } else {
        wp_connection_runtime_events_close(self);
    }

    Py_BEGIN_ALLOW_THREADS
    g_thread_join(self->thread);
    Py_END_ALLOW_THREADS
    self->thread = NULL;
    Py_RETURN_NONE;
}
