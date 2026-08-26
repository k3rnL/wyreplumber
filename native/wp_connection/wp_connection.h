//
// Created by edaniel on 2/5/26.
//

#ifndef PYPEWIRE_WP_CONNECTION_H
#define PYPEWIRE_WP_CONNECTION_H

#include <Python.h>
#include <wp/wp.h>

typedef struct {
    gchar *owner;
    gchar *desired_id;
    WpLink *proxy;
    guint32 output_node_id;
    guint32 output_port_id;
    guint32 input_node_id;
    guint32 input_port_id;
} WpManagedLinkSpec;

typedef struct {
    PyObject_HEAD
    GThread *thread;
    GMainContext *ctx;
    GMainLoop *loop;

    // WirePlumber objects (ONLY touched on WP thread)
    WpCore *core;
    WpObjectManager *om;

    // State / sync
    GMutex lock;
    GCond cond;
    gboolean started;
    gboolean stop_requested;
    GError *start_error;
    guint64 generation;
    guint64 sequence;

    // Detached native event payloads (Python objects, protected by event_lock)
    GMutex event_lock;
    GCond event_cond;
    GQueue *runtime_events;
    guint runtime_event_capacity;
    gboolean runtime_event_invalid;
    gboolean runtime_event_closed;

    // For async calls from Python thread to WP thread
    GMutex call_lock;
    GCond call_cond;
    gboolean call_completed;
    gpointer call_result;
    GError *call_error;  // For storing errors from async operations

    // FIFO mutation preparation/execution boundary
    GMutex mutation_lock;
    GQueue *mutation_queue;
    gboolean mutation_source_scheduled;
    guint64 mutation_dispatch_order;
    GHashTable *managed_links;
} WPConnection;

extern PyTypeObject WPConnectionType;

// Method declarations
PyObject *WPConnection_sync(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_get_nodes(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_get_modules(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_get_metadata(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_capture_runtime_payload(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_next_runtime_event_payload(WPConnection *self, PyObject *args, PyObject *kwargs);
PyObject *WPConnection_drain_runtime_event_payloads(WPConnection *self, PyObject *args, PyObject *kwargs);
PyObject *WPConnection_reconnect(WPConnection *self, PyObject *args, PyObject *kwargs);
PyObject *WPConnection_stop(WPConnection *self, PyObject *Py_UNUSED(ignored));
PyObject *WPConnection_dispatch_runtime_mutation_payload(
    WPConnection *self, PyObject *request);
PyObject *WPConnection_load_module(WPConnection *self, PyObject *args, PyObject *kwargs);

// Runtime event signal and queue helpers
void wp_connection_runtime_events_on_object_added(
    WpObjectManager *om, GObject *object, gpointer user_data);
void wp_connection_runtime_events_on_object_removed(
    WpObjectManager *om, GObject *object, gpointer user_data);
void wp_connection_runtime_events_publish_connection(
    WPConnection *conn, const gchar *state, const gchar *reason);
void wp_connection_runtime_events_reset(WPConnection *conn);
void wp_connection_runtime_events_close(WPConnection *conn);
void wp_connection_runtime_events_clear(WPConnection *conn);

typedef enum {
    WP_MUTATION_CANCEL_GENERATION_LOST,
    WP_MUTATION_CANCEL_RUNTIME_STOPPED,
} WpMutationCancelReason;

void wp_connection_mutations_cancel_pending(
    WPConnection *conn, WpMutationCancelReason reason);
void wp_connection_mutations_clear(WPConnection *conn);
void wp_connection_managed_links_init(WPConnection *conn);
void wp_connection_managed_links_reset(WPConnection *conn);
void wp_connection_managed_links_clear(WPConnection *conn);
const WpManagedLinkSpec *wp_connection_managed_link_lookup_identity(
    WPConnection *conn, const gchar *owner, const gchar *desired_id);
const WpManagedLinkSpec *wp_connection_managed_link_lookup_endpoints(
    WPConnection *conn,
    guint32 output_node_id,
    guint32 output_port_id,
    guint32 input_node_id,
    guint32 input_port_id);
void wp_connection_managed_link_forget_endpoints(
    WPConnection *conn,
    guint32 output_node_id,
    guint32 output_port_id,
    guint32 input_node_id,
    guint32 input_port_id);

// Helper function for synchronous wp_core_sync
gboolean wp_connection_sync(WPConnection *conn);

// Release WirePlumber/PipeWire GObjects on the connection's owning context.
// Legacy Python proxy wrappers use this from their destructors so that their
// final native references never cross the PipeWire thread boundary.
void wp_connection_unref_objects(
    WPConnection *conn, GObject **objects, guint n_objects);

#endif //PYPEWIRE_WP_CONNECTION_H
