//
// Created by edaniel on 2/11/26.
//

#ifndef PYPEWIRE_WP_PORT_H
#define PYPEWIRE_WP_PORT_H

#include <Python.h>
#include <wp/wp.h>

typedef struct {
    PyObject_HEAD
    WpPort *port;           // The WirePlumber port object
    WpCore *core;           // Reference to core for operations
    PyObject *properties;   // Dict of all properties
    guint32 id;
    WpDirection direction;
} WPPort;

extern PyTypeObject WPPortType;

// Create a new WPPort from a WpPort
PyObject *WPPort_from_wp_port(WpPort *wp_port, WpCore *core);

#endif //PYPEWIRE_WP_PORT_H
