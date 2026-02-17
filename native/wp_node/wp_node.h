//
// Created by edaniel on 2/5/26.
//

#ifndef PYPEWIRE_WP_NODE_H
#define PYPEWIRE_WP_NODE_H

#include <Python.h>
#include <wp/wp.h>

typedef struct {
    PyObject_HEAD
    WpNode *node;           // The WirePlumber node object
    WpCore *core;           // Reference to core for operations like delete
    WpObject *om;           // Reference to object manager
    PyObject *properties;   // Dict of all properties
    int state;
    guint n_input_ports;
    guint max_input_ports;
    guint n_output_ports;
    guint max_output_ports;
    char *error_message;
} WPNode;

extern PyTypeObject WPNodeType;

// Create a new WPNode from a WpNode
PyObject *WPNode_from_wp_node(WpNode *wp_node, WpCore *core, WpObject *om);

#endif //PYPEWIRE_WP_NODE_H
