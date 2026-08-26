//
// Created by edaniel on 2/11/26.
//

#ifndef PYPEWIRE_WP_METADATA_H
#define PYPEWIRE_WP_METADATA_H

#include <Python.h>
#include <wp/wp.h>

// Forward declaration (only declare the struct tag, not the typedef)
struct WPConnection;

typedef struct {
    PyObject_HEAD
    WpMetadata *metadata;   // The WirePlumber metadata object
    WpCore *core;           // Reference to core for operations
    PyObject *connection;   // Strong reference to connection
    PyObject *properties;   // Dict of all properties
    guint32 id;
} WPMetadata;

extern PyTypeObject WPMetadataType;

// Create a new WPMetadata from a WpMetadata
PyObject *WPMetadata_from_wp_metadata(WpMetadata *wp_metadata, WpCore *core, struct WPConnection *conn);

// Method declarations (implemented in separate files)
PyObject *WPMetadata_find(WPMetadata *self, PyObject *args, PyObject *kwargs);
PyObject *WPMetadata_set(WPMetadata *self, PyObject *args, PyObject *kwargs);
PyObject *WPMetadata_clear(WPMetadata *self, PyObject *Py_UNUSED(ignored));
PyObject *WPMetadata_iterate(WPMetadata *self, PyObject *args, PyObject *kwargs);

#endif //PYPEWIRE_WP_METADATA_H
