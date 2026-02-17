//
// Created by edaniel on 2/14/26.
//

#include "wp_connection.h"

typedef struct {
    WPConnection *conn;
} SyncData;

// Async ready callback for wp_core_sync (runs on WP thread / main context)
static void on_sync_done(GObject *source_object, GAsyncResult *res, gpointer user_data) {
    SyncData *data = user_data;
    WPConnection *conn = data->conn;

    GError *error = NULL;
    gboolean ok = wp_core_sync_finish(WP_CORE(source_object), res, &error);

    g_mutex_lock(&conn->call_lock);
    conn->call_result = GINT_TO_POINTER(ok && error == NULL);

    // Store error for the waiting thread (transfer ownership)
    if (conn->call_error) {
        g_error_free(conn->call_error);
    }
    conn->call_error = error;

    conn->call_completed = TRUE;
    g_cond_signal(&conn->call_cond);
    g_mutex_unlock(&conn->call_lock);
}

// Runs on the WP thread (in self->ctx)
static gboolean do_sync_on_wp_thread(gpointer user_data) {
    SyncData *data = user_data;
    WPConnection *conn = data->conn;

    // Launch async sync; completion comes via on_sync_done on same main context
    wp_core_sync(conn->core, NULL, on_sync_done, data);

    return G_SOURCE_REMOVE;
}

// Python-exposed method: blocks caller thread until sync completes
gboolean wp_connection_sync(WPConnection *conn) {
    if (!conn || !conn->core || !conn->ctx) {
        PyErr_SetString(PyExc_RuntimeError, "Invalid WPConnection (missing core/ctx)");
        return FALSE;
    }

    // Reset call state
    g_mutex_lock(&conn->call_lock);
    conn->call_completed = FALSE;
    conn->call_result = NULL;
    if (conn->call_error) {
        g_error_free(conn->call_error);
        conn->call_error = NULL;
    }
    g_mutex_unlock(&conn->call_lock);

    SyncData data = {.conn = conn};

    // Schedule sync start on WP thread/context
    GSource *source = g_idle_source_new();
    g_source_set_callback(source, do_sync_on_wp_thread, &data, NULL);
    g_source_attach(source, conn->ctx);
    g_source_unref(source);

    // Wait for completion (release GIL while waiting)
    GError *error = NULL;
    gboolean success = FALSE;
    Py_BEGIN_ALLOW_THREADS
        g_mutex_lock(&conn->call_lock);
        while (!conn->call_completed) {
            g_cond_wait(&conn->call_cond, &conn->call_lock);
        }
        success = GPOINTER_TO_INT(conn->call_result);
        error = conn->call_error;
        conn->call_error = NULL;
        g_mutex_unlock(&conn->call_lock);
    Py_END_ALLOW_THREADS

    if (error) {
        PyErr_Format(PyExc_RuntimeError, "WirePlumber sync failed: %s", error->message);
        g_error_free(error);
        return FALSE;
    }

    return success;
}
