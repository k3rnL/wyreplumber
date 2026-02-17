//
// Created by edaniel on 2/5/26.
//

#include "wp_connection.h"

// Forward declarations
static void on_om_installed(WpObjectManager *om, gpointer user_data);
static PyObject *WPConnection_repr(WPConnection *self);
static PyObject *WPConnection_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int WPConnection_init(WPConnection *self, PyObject *args, PyObject *kwds);
static void WPConnection_dealloc(WPConnection *self);

static void on_core_connected(WpCore *core, GParamSpec *pspec, gpointer user_data) {
    WPConnection *c = user_data;

    // Check if we're actually connected
    if (!wp_core_is_connected(core)) {
        return;
    }

    c->om = wp_object_manager_new();

    // interested in Nodes with required features
    wp_object_manager_add_interest(c->om, WP_TYPE_NODE, NULL);
    wp_object_manager_request_object_features(c->om, WP_TYPE_NODE,
        WP_PROXY_FEATURE_BOUND | WP_PIPEWIRE_OBJECT_FEATURE_INFO);

    // interested in Ports with required features
    wp_object_manager_add_interest(c->om, WP_TYPE_PORT, NULL);
    wp_object_manager_request_object_features(c->om, WP_TYPE_PORT,
        WP_PROXY_FEATURE_BOUND | WP_PIPEWIRE_OBJECT_FEATURE_INFO);

    // interested in Metadata with required features
    // Note: Metadata uses WP_METADATA_FEATURE_DATA instead of WP_PIPEWIRE_OBJECT_FEATURE_INFO
    wp_object_manager_add_interest(c->om, WP_TYPE_METADATA, NULL);
    wp_object_manager_request_object_features(c->om, WP_TYPE_METADATA,
        WP_PROXY_FEATURE_BOUND | WP_METADATA_FEATURE_DATA);

    // interested in Modules (WpImplModule is GObject, not WpObject, so no features to request)
    wp_object_manager_add_interest(c->om, WP_TYPE_IMPL_MODULE, NULL);

    g_signal_connect(c->om, "installed", G_CALLBACK(on_om_installed), c);

    wp_core_install_object_manager(core, c->om);
}

static void on_om_installed(WpObjectManager *om, gpointer user_data) {
    WPConnection *c = user_data;

    // Now we have an initial snapshot of nodes available
    g_mutex_lock(&c->lock);
    c->started = TRUE;
    g_cond_broadcast(&c->cond);
    g_mutex_unlock(&c->lock);
}

static gpointer wp_thread_main(gpointer data) {
    WPConnection *c = data;

    c->ctx = g_main_context_new();
    g_main_context_push_thread_default(c->ctx);

    c->loop = g_main_loop_new(c->ctx, FALSE);
    c->core = wp_core_new(c->ctx, NULL);

    // Connect to the "connected" signal before connecting
    g_signal_connect(c->core, "notify::connected", G_CALLBACK(on_core_connected), c);

    // Start connection - returns FALSE on immediate failure
    if (!wp_core_connect(c->core)) {
        g_mutex_lock(&c->lock);
        c->start_error = g_error_new_literal(G_IO_ERROR, G_IO_ERROR_FAILED, "wp_core_connect failed");
        c->started = TRUE;
        g_cond_broadcast(&c->cond);
        g_mutex_unlock(&c->lock);
        return NULL;
    }

    // If already connected (sync case), trigger callback manually
    if (wp_core_is_connected(c->core)) {
        on_core_connected(c->core, NULL, c);
    }

    g_main_loop_run(c->loop);

    // cleanup (still on WP thread)
    if (c->om) g_object_unref(c->om);
    if (c->core) g_object_unref(c->core);
    if (c->loop) g_main_loop_unref(c->loop);

    g_main_context_pop_thread_default(c->ctx);
    if (c->ctx) g_main_context_unref(c->ctx);

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
        g_mutex_init(&self->call_lock);
        g_cond_init(&self->call_cond);
        self->call_completed = FALSE;
        self->call_result = NULL;
        self->call_error = NULL;
    }
    return (PyObject *)self;
}

static int WPConnection_init(WPConnection *self, PyObject *args, PyObject *kwds) {
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
    if (self->thread) {
        // Signal the thread to stop
        g_mutex_lock(&self->lock);
        self->stop_requested = TRUE;
        g_mutex_unlock(&self->lock);

        // Quit the main loop from the thread's context
        if (self->loop) {
            g_main_loop_quit(self->loop);
        }

        // Wait for thread to finish
        g_thread_join(self->thread);
        self->thread = NULL;
    }

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
    g_mutex_clear(&self->call_lock);
    g_cond_clear(&self->call_cond);

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
