#include "wp_connection.h"


static void set_error(GError **error, const gchar *message) {
    if (error && !*error) {
        *error = g_error_new_literal(G_IO_ERROR, G_IO_ERROR_FAILED, message);
    }
    PyErr_Clear();
}


static gboolean dict_set_owned(
    PyObject *dict, const gchar *key, PyObject *value, GError **error)
{
    if (!value) {
        set_error(error, "Failed to allocate mixer state value");
        return FALSE;
    }
    const int result = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    if (result < 0) {
        set_error(error, "Failed to append mixer state value");
        return FALSE;
    }
    return TRUE;
}


PyObject *wp_connection_copy_mixer_state(
    WPConnection *conn, guint32 node_id, GError **error)
{
    if (!conn || !conn->mixer_api) Py_RETURN_NONE;

    g_autoptr(GVariant) state = NULL;
    g_signal_emit_by_name(conn->mixer_api, "get-volume", node_id, &state);
    if (!state) Py_RETURN_NONE;

    gdouble volume = 0.0;
    gdouble base = 0.0;
    gdouble step = 0.0;
    gboolean mute = FALSE;
    if (!g_variant_lookup(state, "volume", "d", &volume) ||
        !g_variant_lookup(state, "mute", "b", &mute)) {
        Py_RETURN_NONE;
    }

    PyObject *result = PyDict_New();
    if (!result ||
        !dict_set_owned(result, "volume", PyFloat_FromDouble(volume), error) ||
        !dict_set_owned(result, "mute", PyBool_FromLong(mute), error)) {
        Py_XDECREF(result);
        return NULL;
    }
    if (g_variant_lookup(state, "base", "d", &base) &&
        !dict_set_owned(result, "base", PyFloat_FromDouble(base), error)) {
        Py_DECREF(result);
        return NULL;
    }
    if (g_variant_lookup(state, "step", "d", &step) &&
        !dict_set_owned(result, "step", PyFloat_FromDouble(step), error)) {
        Py_DECREF(result);
        return NULL;
    }
    return result;
}


gboolean wp_connection_set_mixer_state(
    WPConnection *conn,
    guint32 node_id,
    gboolean has_volume,
    gdouble volume,
    gboolean has_mute,
    gboolean mute)
{
    if (!conn || !conn->mixer_api || (!has_volume && !has_mute)) return FALSE;

    g_autoptr(GVariant) current = NULL;
    g_signal_emit_by_name(conn->mixer_api, "get-volume", node_id, &current);
    if (!current) return FALSE;

    g_auto(GVariantBuilder) builder =
        G_VARIANT_BUILDER_INIT(G_VARIANT_TYPE_VARDICT);
    if (has_volume) {
        g_variant_builder_add(
            &builder, "{sv}", "volume", g_variant_new_double(volume));
    }
    if (has_mute) {
        g_variant_builder_add(
            &builder, "{sv}", "mute", g_variant_new_boolean(mute));
    }
    g_autoptr(GVariant) requested =
        g_variant_ref_sink(g_variant_builder_end(&builder));
    gboolean accepted = FALSE;
    g_signal_emit_by_name(
        conn->mixer_api, "set-volume", node_id, requested, &accepted);
    return accepted;
}
