//
// Created by edaniel on 2/11/26.
//

#ifndef PYPEWIRE_WP_PORT_H
#define PYPEWIRE_WP_PORT_H

#include <Python.h>
#include <wp/wp.h>
#include "../wp_pipewire_object/wp_pipewire_object.h"

struct WPConnection;

typedef struct {
    WPPipewireObject base;
    WpDirection direction;
} WPPort;

extern PyTypeObject WPPortType;

// Create a new WPPort from a WpPort
PyObject *WPPort_from_wp_port(WpPort *wp_port, WpCore *core, struct WPConnection *conn);

#endif //PYPEWIRE_WP_PORT_H
