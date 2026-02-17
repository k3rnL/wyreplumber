//
// Created by edaniel on 2/6/26.
//

#ifndef PYPEWIRE_WP_MODULE_H
#define PYPEWIRE_WP_MODULE_H

#include <Python.h>
#include <wp/wp.h>

typedef struct {
    PyObject_HEAD
    WpImplModule *module;   // The WirePlumber module object
    WpCore *core;           // Reference to core for operations
    PyObject *properties;   // Dict of all properties
    char *name;
    char *arguments;
} WPModule;

extern PyTypeObject WPModuleType;

// Create a new WPModule from a WpImplModule
PyObject *WPModule_from_wp_module(WpImplModule *wp_module, WpCore *core);

#endif //PYPEWIRE_WP_MODULE_H
