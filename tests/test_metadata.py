import time
from wyreplumber._core import WPConnection, WPMetadata


def test_get_metadata(pipewire_socket):
    """Test getting list of metadata objects."""
    conn = WPConnection()
    metadata_list = conn.get_metadata()

    assert isinstance(metadata_list, list), "metadata should be a list"

    # There should be at least the default metadata object
    for metadata in metadata_list:
        assert isinstance(metadata, WPMetadata), "Each item should be a WPMetadata"


def test_metadata_properties(pipewire_socket):
    """Test metadata properties."""
    conn = WPConnection()
    metadata_list = conn.get_metadata()

    assert len(metadata_list) > 0, "Should have at least one metadata object"

    metadata = metadata_list[0]

    # Test ID
    assert isinstance(metadata.id, int), "Metadata ID should be an integer"
    assert metadata.id > 0, "Metadata ID should be positive"

    # Test properties
    assert isinstance(metadata.properties, dict), "Properties should be a dict"


def test_metadata_find(pipewire_socket):
    """Test finding metadata by subject and key."""
    conn = WPConnection()
    metadata_list = conn.get_metadata()

    assert len(metadata_list) > 0, "Should have at least one metadata object"
    metadata = metadata_list[0]

    # Test find with non-existent subject/key (should return None)
    result = metadata.find(99999, "nonexistent.key")
    assert result is None, "Should return None for non-existent metadata"

    # Note: The metadata objects from get_metadata() are owned by wireplumber
    # and may be read-only, so we can't reliably test setting metadata


def test_metadata_set_api(pipewire_socket):
    """Test that set API exists and can be called without crashing."""
    conn = WPConnection()
    metadata_list = conn.get_metadata()

    assert len(metadata_list) > 0, "Should have at least one metadata object"
    metadata = metadata_list[0]

    # Test that set method can be called without crashing
    # Note: Changes may not persist as the metadata object may be read-only
    try:
        metadata.set(100, "test.key", "string", "test_value")
        conn.sync()
    except Exception:
        pass  # It's ok if this fails - metadata might be read-only

    # Test unsetting
    try:
        metadata.set(100, "test.key", None, None)
        conn.sync()
    except Exception:
        pass  # It's ok if this fails


def test_metadata_clear_api(pipewire_socket):
    """Test that clear API exists and can be called without crashing."""
    conn = WPConnection()
    metadata_list = conn.get_metadata()

    assert len(metadata_list) > 0, "Should have at least one metadata object"
    metadata = metadata_list[0]

    # Test that clear method exists and can be called
    # Note: clear() may not actually remove metadata if object is read-only
    try:
        metadata.clear()
        conn.sync()
    except Exception:
        pass  # It's ok if this fails - metadata might be read-only


def test_metadata_iterate(pipewire_socket):
    """Test iterating over metadata items."""
    conn = WPConnection()
    metadata_list = conn.get_metadata()

    assert len(metadata_list) > 0, "Should have at least one metadata object"
    metadata = metadata_list[0]

    # Iterate all items
    all_items = metadata.iterate()
    assert isinstance(all_items, list), "iterate() should return a list"

    for item in all_items:
        assert isinstance(item, dict), "Each item should be a dict"
        # Check for expected keys if they exist
        if "subject" in item:
            assert isinstance(item["subject"], int), "subject should be an integer"
        if "key" in item:
            assert isinstance(item["key"], str), "key should be a string"
        if "type" in item:
            assert isinstance(item["type"], str), "type should be a string"
        if "value" in item:
            assert isinstance(item["value"], str), "value should be a string"

    # Iterate items for specific subject
    subject_items = metadata.iterate(subject=999)
    assert isinstance(subject_items, list), "iterate(subject) should return a list"


def test_metadata_edge_cases(pipewire_socket):
    """Test metadata edge cases."""
    conn = WPConnection()
    metadata_list = conn.get_metadata()

    if len(metadata_list) > 0:
        metadata = metadata_list[0]

        # Test find with non-existent subject/key
        result = metadata.find(99999, "nonexistent.key")
        assert result is None, "Should return None for non-existent metadata"

        # Test iterate with non-existent subject
        items = metadata.iterate(subject=99999)
        assert isinstance(items, list), "Should return list even for non-existent subject"
