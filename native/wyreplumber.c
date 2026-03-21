//
// Created by edaniel on 2/5/26.
//

#include <Python.h>
#include <wp/wp.h>
#include "wp_connection/wp_connection.h"
#include "wp_pipewire_object/wp_pipewire_object.h"
#include "wp_node/wp_node.h"
#include "wp_module/wp_module.h"
#include "wp_port/wp_port.h"
#include "wp_metadata/wp_metadata.h"

static struct PyModuleDef module = { PyModuleDef_HEAD_INIT, "_core", NULL, -1, NULL };

PyMODINIT_FUNC PyInit__core(void) {
    wp_init(WP_INIT_ALL);

    // // Initialize Python threading support for GIL operations
    // if (!PyEval_ThreadsInitialized()) {
    //     PyEval_InitThreads();
    // }

    PyObject *m = PyModule_Create(&module);
    if (!m) return NULL;

    // Register WPConnection type
    if (PyType_Ready(&WPConnectionType) < 0) return NULL;
    Py_INCREF(&WPConnectionType);
    if (PyModule_AddObject(m, "WPConnection", (PyObject *)&WPConnectionType) < 0) {
        Py_DECREF(&WPConnectionType);
        Py_DECREF(m);
        return NULL;
    }

    // Register WPPipewireObject base type
    if (PyType_Ready(&WPPipewireObjectType) < 0) return NULL;
    Py_INCREF(&WPPipewireObjectType);
    if (PyModule_AddObject(m, "WPPipewireObject", (PyObject *)&WPPipewireObjectType) < 0) {
        Py_DECREF(&WPPipewireObjectType);
        Py_DECREF(&WPConnectionType);
        Py_DECREF(m);
        return NULL;
    }

    // Register WPParam type
    if (PyType_Ready(&WPParamType) < 0) return NULL;
    Py_INCREF(&WPParamType);
    if (PyModule_AddObject(m, "WPParam", (PyObject *)&WPParamType) < 0) {
        Py_DECREF(&WPParamType);
        Py_DECREF(&WPPipewireObjectType);
        Py_DECREF(&WPConnectionType);
        Py_DECREF(m);
        return NULL;
    }

    // Register WPNode type
    if (PyType_Ready(&WPNodeType) < 0) return NULL;
    Py_INCREF(&WPNodeType);
    if (PyModule_AddObject(m, "WPNode", (PyObject *)&WPNodeType) < 0) {
        Py_DECREF(&WPNodeType);
        Py_DECREF(&WPParamType);
        Py_DECREF(&WPPipewireObjectType);
        Py_DECREF(&WPConnectionType);
        Py_DECREF(m);
        return NULL;
    }

    // Register WPModule type
    if (PyType_Ready(&WPModuleType) < 0) return NULL;
    Py_INCREF(&WPModuleType);
    if (PyModule_AddObject(m, "WPModule", (PyObject *)&WPModuleType) < 0) {
        Py_DECREF(&WPModuleType);
        Py_DECREF(&WPNodeType);
        Py_DECREF(&WPParamType);
        Py_DECREF(&WPPipewireObjectType);
        Py_DECREF(&WPConnectionType);
        Py_DECREF(m);
        return NULL;
    }

    // Register WPPort type
    if (PyType_Ready(&WPPortType) < 0) return NULL;
    Py_INCREF(&WPPortType);
    if (PyModule_AddObject(m, "WPPort", (PyObject *)&WPPortType) < 0) {
        Py_DECREF(&WPPortType);
        Py_DECREF(&WPModuleType);
        Py_DECREF(&WPNodeType);
        Py_DECREF(&WPParamType);
        Py_DECREF(&WPPipewireObjectType);
        Py_DECREF(&WPConnectionType);
        Py_DECREF(m);
        return NULL;
    }

    // Register WPMetadata type
    if (PyType_Ready(&WPMetadataType) < 0) return NULL;
    Py_INCREF(&WPMetadataType);
    if (PyModule_AddObject(m, "WPMetadata", (PyObject *)&WPMetadataType) < 0) {
        Py_DECREF(&WPMetadataType);
        Py_DECREF(&WPPortType);
        Py_DECREF(&WPModuleType);
        Py_DECREF(&WPNodeType);
        Py_DECREF(&WPParamType);
        Py_DECREF(&WPPipewireObjectType);
        Py_DECREF(&WPConnectionType);
        Py_DECREF(m);
        return NULL;
    }

    // Add node state constants
    PyModule_AddIntConstant(m, "WP_NODE_STATE_ERROR", WP_NODE_STATE_ERROR);
    PyModule_AddIntConstant(m, "WP_NODE_STATE_CREATING", WP_NODE_STATE_CREATING);
    PyModule_AddIntConstant(m, "WP_NODE_STATE_SUSPENDED", WP_NODE_STATE_SUSPENDED);
    PyModule_AddIntConstant(m, "WP_NODE_STATE_IDLE", WP_NODE_STATE_IDLE);
    PyModule_AddIntConstant(m, "WP_NODE_STATE_RUNNING", WP_NODE_STATE_RUNNING);

    // Add direction constants
    PyModule_AddIntConstant(m, "WP_DIRECTION_INPUT", WP_DIRECTION_INPUT);
    PyModule_AddIntConstant(m, "WP_DIRECTION_OUTPUT", WP_DIRECTION_OUTPUT);

    return m;
}
