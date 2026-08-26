#ifndef WYREPLUMBER_WP_COMPAT_H
#define WYREPLUMBER_WP_COMPAT_H

#include <wp/wp.h>

#ifndef WYREPLUMBER_WP_API_0_5
#define WYREPLUMBER_WP_API_0_5 0
#endif

static inline WpCore *wyreplumber_core_new(GMainContext *context) {
#if WYREPLUMBER_WP_API_0_5
    return wp_core_new(context, NULL, NULL);
#else
    return wp_core_new(context, NULL);
#endif
}

static inline gboolean wyreplumber_metadata_item_extract(
    const GValue *value,
    guint32 *subject,
    const gchar **key,
    const gchar **type,
    const gchar **item_value)
{
#if WYREPLUMBER_WP_API_0_5
    WpMetadataItem *item = g_value_get_boxed(value);
    if (!item) return FALSE;
    *subject = wp_metadata_item_get_subject(item);
    *key = wp_metadata_item_get_key(item);
    *type = wp_metadata_item_get_value_type(item);
    *item_value = wp_metadata_item_get_value(item);
    return TRUE;
#else
    wp_metadata_iterator_item_extract(value, subject, key, type, item_value);
    return TRUE;
#endif
}

#endif // WYREPLUMBER_WP_COMPAT_H
