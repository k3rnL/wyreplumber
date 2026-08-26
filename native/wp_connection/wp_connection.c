//
// Created by edaniel on 2/5/26.
//

#include "wp_connection.h"
#include "../wp_compat.h"

// Forward declarations
static void on_om_installed(WpObjectManager *om, gpointer user_data);
static void on_core_connected(WpCore *core, gpointer user_data);
static void on_core_disconnected(WpCore *core, gpointer user_data);
static PyObject *WPConnection_repr(WPConnection *self);
static PyObject *WPConnection_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int WPConnection_init(WPConnection *self, PyObject *args, PyObject *kwds);
static void WPConnection_dealloc(WPConnection *self);

typedef struct {
    GObject **objects;
    guint n_objects;
    GMutex lock;
    GCond cond;
    gboolean completed;
} UnrefObjectsData;

static gboolean unref_objects_on_wp_thread(gpointer user_data) {
    UnrefObjectsData *data = user_data;
    for (guint index = 0; index < data->n_objects; index++) {
        if (data->objects[index]) g_object_unref(data->objects[index]);
    }

    g_mutex_lock(&data->lock);
    data->completed = TRUE;
    g_cond_signal(&data->cond);
    g_mutex_unlock(&data->lock);
    return G_SOURCE_REMOVE;
}

void wp_connection_unref_objects(
    WPConnection *conn, GObject **objects, guint n_objects)
{
    if (!objects || n_objects == 0) return;

    if (!conn || !conn->thread || !conn->ctx ||
        g_main_context_is_owner(conn->ctx)) {
        for (guint index = 0; index < n_objects; index++) {
            if (objects[index]) g_object_unref(objects[index]);
        }
        return;
    }

    UnrefObjectsData data = {
        .objects = objects,
        .n_objects = n_objects,
        .completed = FALSE,
    };
    g_mutex_init(&data.lock);
    g_cond_init(&data.cond);

    GSource *source = g_idle_source_new();
    g_source_set_callback(source, unref_objects_on_wp_thread, &data, NULL);
    g_source_attach(source, conn->ctx);
    g_source_unref(source);

    Py_BEGIN_ALLOW_THREADS
    g_mutex_lock(&data.lock);
    while (!data.completed) g_cond_wait(&data.cond, &data.lock);
    g_mutex_unlock(&data.lock);
    Py_END_ALLOW_THREADS

    g_mutex_clear(&data.lock);
    g_cond_clear(&data.cond);
}

static void on_core_connected(WpCore *core, gpointer user_data) {
    WPConnection *c = user_data;
    if (!wp_core_is_connected(core) || c->om) return;

    c->om = wp_object_manager_new();

    // interested in Nodes with required features
    wp_object_manager_add_interest(c->om, WP_TYPE_NODE, NULL);
    wp_object_manager_request_object_features(c->om, WP_TYPE_NODE,
        WP_PIPEWIRE_OBJECT_FEATURES_ALL);

    // interested in Ports with required features
    wp_object_manager_add_interest(c->om, WP_TYPE_PORT, NULL);
    wp_object_manager_request_object_features(c->om, WP_TYPE_PORT,
        WP_PIPEWIRE_OBJECT_FEATURES_ALL);

    // interested in Devices and Links for orchestration snapshots
    wp_object_manager_add_interest(c->om, WP_TYPE_DEVICE, NULL);
    wp_object_manager_request_object_features(c->om, WP_TYPE_DEVICE,
        WP_PIPEWIRE_OBJECT_FEATURES_ALL);

    wp_object_manager_add_interest(c->om, WP_TYPE_LINK, NULL);
    wp_object_manager_request_object_features(c->om, WP_TYPE_LINK,
        WP_PIPEWIRE_OBJECT_FEATURES_ALL);

    // interested in Metadata with required features
    // Note: Metadata uses WP_METADATA_FEATURE_DATA instead of WP_PIPEWIRE_OBJECT_FEATURE_INFO
    wp_object_manager_add_interest(c->om, WP_TYPE_METADATA, NULL);
    wp_object_manager_request_object_features(c->om, WP_TYPE_METADATA,
        WP_PROXY_FEATURE_BOUND | WP_METADATA_FEATURE_DATA);

    // interested in Modules (WpImplModule is GObject, not WpObject, so no features to request)
    wp_object_manager_add_interest(c->om, WP_TYPE_IMPL_MODULE, NULL);

    g_signal_connect(c->om, "installed", G_CALLBACK(on_om_installed), c);
    g_signal_connect(
        c->om, "object-added",
        G_CALLBACK(wp_connection_runtime_events_on_object_added), c);
    g_signal_connect(
        c->om, "object-removed",
        G_CALLBACK(wp_connection_runtime_events_on_object_removed), c);

    wp_core_install_object_manager(c->core, c->om);
}

static void on_core_disconnected(WpCore *core, gpointer user_data) {
    WPConnection *c = user_data;
    wp_connection_managed_links_reset(c);
    if (c->started && !c->stop_requested) {
        wp_connection_mutations_cancel_pending(
            c, WP_MUTATION_CANCEL_GENERATION_LOST);
        wp_connection_runtime_events_publish_connection(
            c, "disconnected", "WirePlumber core disconnected");
    }
    if (c->om) {
        g_object_unref(c->om);
        c->om = NULL;
    }
    g_mutex_lock(&c->lock);
    g_cond_broadcast(&c->cond);
    g_mutex_unlock(&c->lock);
}

static void on_om_installed(WpObjectManager *om, gpointer user_data) {
    WPConnection *c = user_data;

    // A newly installed manager establishes one coherent connection generation.
    g_mutex_lock(&c->lock);
    c->generation++;
    c->sequence = 0;
    g_mutex_lock(&c->mutation_lock);
    c->mutation_dispatch_order = 0;
    g_mutex_unlock(&c->mutation_lock);
    c->started = TRUE;
    g_cond_broadcast(&c->cond);
    g_mutex_unlock(&c->lock);
    wp_connection_runtime_events_publish_connection(c, "connected", NULL);
}

static gpointer wp_thread_main(gpointer data) {
    WPConnection *c = data;

    c->ctx = g_main_context_new();
    g_main_context_push_thread_default(c->ctx);

    c->loop = g_main_loop_new(c->ctx, FALSE);
    c->core = wyreplumber_core_new(c->ctx);

    // Connect lifecycle signals before connecting.
    g_signal_connect(c->core, "connected", G_CALLBACK(on_core_connected), c);
    g_signal_connect(c->core, "disconnected", G_CALLBACK(on_core_disconnected), c);

    // Start connection - returns FALSE on immediate failure
    if (!wp_core_connect(c->core)) {
        g_mutex_lock(&c->lock);
        c->start_error = g_error_new_literal(G_IO_ERROR, G_IO_ERROR_FAILED, "wp_core_connect failed");
        c->started = TRUE;
        g_cond_broadcast(&c->cond);
        g_mutex_unlock(&c->lock);
        goto cleanup;
    }

    // If already connected (sync case), trigger callback manually
    if (wp_core_is_connected(c->core)) {
        on_core_connected(c->core, c);
    }

    g_main_loop_run(c->loop);

    // cleanup (still on WP thread)
cleanup:
    if (c->om) {
        g_object_unref(c->om);
        c->om = NULL;
    }
    if (c->core) {
        g_object_unref(c->core);
        c->core = NULL;
    }
    if (c->loop) {
        g_main_loop_unref(c->loop);
        c->loop = NULL;
    }

    g_main_context_pop_thread_default(c->ctx);
    if (c->ctx) {
        g_main_context_unref(c->ctx);
        c->ctx = NULL;
    }

    return NULL;
}

static PyObject *WPConnection_new(PyTypeObject *type, PyObject *args, PyObject *kwds) {
    WPConnection *self = (WPConnection *)type->tp_alloc(type, 0);
    if (self != NULL) {
        self->thread = NULL;
        self->ctx = NULL;
        self->loop = NULL;
        self->core = NULL;
        self->om = NULL;
        g_mutex_init(&self->lock);
        g_cond_init(&self->cond);
        self->started = FALSE;
        self->stop_requested = FALSE;
        self->start_error = NULL;
        self->generation = 0;
        self->sequence = 0;
        g_mutex_init(&self->event_lock);
        g_cond_init(&self->event_cond);
        self->runtime_events = g_queue_new();
        self->runtime_event_capacity = 256;
        self->runtime_event_invalid = FALSE;
        self->runtime_event_closed = FALSE;
        g_mutex_init(&self->call_lock);
        g_cond_init(&self->call_cond);
        self->call_completed = FALSE;
        self->call_result = NULL;
        self->call_error = NULL;
        g_mutex_init(&self->mutation_lock);
        self->mutation_queue = g_queue_new();
        self->mutation_source_scheduled = FALSE;
        self->mutation_dispatch_order = 0;
        wp_connection_managed_links_init(self);
    }
    return (PyObject *)self;
}

static int WPConnection_init(WPConnection *self, PyObject *args, PyObject *kwds) {
    static char *kwlist[] = {"event_capacity", NULL};
    unsigned int event_capacity = 256;
    if (!PyArg_ParseTupleAndKeywords(
            args, kwds, "|I:WPConnection", kwlist, &event_capacity)) {
        return -1;
    }
    if (event_capacity == 0) {
        PyErr_SetString(PyExc_ValueError, "event_capacity must be at least one");
        return -1;
    }
    self->runtime_event_capacity = event_capacity;

    // Start the WirePlumber thread
    self->thread = g_thread_new("wp-thread", wp_thread_main, self);
    if (!self->thread) {
        PyErr_SetString(PyExc_RuntimeError, "Failed to create WirePlumber thread");
        return -1;
    }

    // Wait for WP to connect and object manager to be installed
    g_mutex_lock(&self->lock);
    while (!self->started) {
        g_cond_wait(&self->cond, &self->lock);
    }
    GError *error = self->start_error;
    self->start_error = NULL;
    g_mutex_unlock(&self->lock);

    if (error) {
        PyErr_Format(PyExc_RuntimeError, "WirePlumber connection failed: %s", error->message);
        g_error_free(error);
        return -1;
    }

    return 0;
}

static void WPConnection_dealloc(WPConnection *self) {
    wp_connection_runtime_events_close(self);
    if (self->thread) {
        // Signal the thread to stop
        g_mutex_lock(&self->lock);
        self->stop_requested = TRUE;
        g_mutex_unlock(&self->lock);
        wp_connection_mutations_cancel_pending(
            self, WP_MUTATION_CANCEL_RUNTIME_STOPPED);

        // Quit the main loop from the thread's context
        if (self->loop) {
            g_main_loop_quit(self->loop);
        }

        // Wait for thread to finish
        Py_BEGIN_ALLOW_THREADS
        g_thread_join(self->thread);
        Py_END_ALLOW_THREADS
        self->thread = NULL;
    }

    wp_connection_runtime_events_clear(self);
    wp_connection_mutations_clear(self);
    wp_connection_managed_links_clear(self);

    // Free any start error
    if (self->start_error) {
        g_error_free(self->start_error);
        self->start_error = NULL;
    }

    // Free any pending call error
    if (self->call_error) {
        g_error_free(self->call_error);
        self->call_error = NULL;
    }

    g_mutex_clear(&self->lock);
    g_cond_clear(&self->cond);
    g_mutex_clear(&self->event_lock);
    g_cond_clear(&self->event_cond);
    if (self->runtime_events) {
        g_queue_free(self->runtime_events);
        self->runtime_events = NULL;
    }
    g_mutex_clear(&self->call_lock);
    g_cond_clear(&self->call_cond);
    g_mutex_clear(&self->mutation_lock);

    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *WPConnection_repr(WPConnection *self) {
    return PyUnicode_FromFormat("<WPConnection at %p>", self);
}

static PyMemberDef Custom_members[] = {
    // {"name", Py_T_OBJECT_EX, offsetof(WPConnection, name), 0, "Connection name"},
    {NULL} /* Sentinel */
};

static PyMethodDef WPConnection_methods[] = {
    {"sync", (PyCFunction)WPConnection_sync, METH_NOARGS, "Blocking sync to pump/sync all events"},
    {"get_nodes", (PyCFunction)WPConnection_get_nodes, METH_NOARGS, "List nodes"},
    {"get_modules", (PyCFunction)WPConnection_get_modules, METH_NOARGS, "List modules"},
    {"get_metadata", (PyCFunction)WPConnection_get_metadata, METH_NOARGS, "List metadata"},
    {"capture_runtime_payload", (PyCFunction)WPConnection_capture_runtime_payload, METH_NOARGS,
     "Copy a coherent primitive runtime payload on the WirePlumber thread"},
    {"next_runtime_event_payload", (PyCFunction)WPConnection_next_runtime_event_payload,
     METH_VARARGS | METH_KEYWORDS,
     "Read the next detached native runtime event payload"},
    {"drain_runtime_event_payloads", (PyCFunction)WPConnection_drain_runtime_event_payloads,
     METH_VARARGS | METH_KEYWORDS,
     "Drain available detached native runtime event payloads"},
    {"reconnect", (PyCFunction)WPConnection_reconnect,
     METH_VARARGS | METH_KEYWORDS,
     "Reconnect and wait for a new synchronized connection generation"},
    {"stop", (PyCFunction)WPConnection_stop, METH_NOARGS,
     "Stop the WirePlumber thread and release event waiters"},
    {"dispatch_runtime_mutation_payload",
     (PyCFunction)WPConnection_dispatch_runtime_mutation_payload, METH_O,
     "Serialize one detached mutation request onto the WirePlumber context"},
    {"load_module", (PyCFunction)WPConnection_load_module, METH_VARARGS | METH_KEYWORDS, "Load a module"},
    {NULL}
};

PyTypeObject WPConnectionType = {
    PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "_core.WPConnection",
    .tp_doc = "WirePlumber Connection Object",
    .tp_basicsize = sizeof(WPConnection),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_repr = (reprfunc) WPConnection_repr,
    .tp_new = WPConnection_new,
    .tp_init = (initproc) WPConnection_init,
    .tp_dealloc = (destructor) WPConnection_dealloc,
    .tp_methods = WPConnection_methods,
    .tp_members = Custom_members
};
