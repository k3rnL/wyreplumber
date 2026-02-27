import time
import pytest
from wyreplumber._core import WPConnection


def test_connection_creation(pipewire_socket):
    """Test creating a WPConnection."""
    conn = WPConnection()
    assert conn is not None, "Connection should be created"



def test_connection_sync(pipewire_socket):
    """Test sync method."""
    conn = WPConnection()

    # Call sync multiple times - should not crash
    conn.sync()
    conn.sync()
    conn.sync()



def test_multiple_connections_sequential(pipewire_socket):
    """Test creating multiple connections sequentially."""
    # First connection
    conn1 = WPConnection()
    nodes1 = conn1.get_nodes()
    assert isinstance(nodes1, list), "Should get nodes from first connection"
    del conn1

    # Second connection
    conn2 = WPConnection()
    nodes2 = conn2.get_nodes()
    assert isinstance(nodes2, list), "Should get nodes from second connection"
    del conn2

    # Third connection
    conn3 = WPConnection()
    nodes3 = conn3.get_nodes()
    assert isinstance(nodes3, list), "Should get nodes from third connection"
    del conn3


def test_connection_get_all_types(pipewire_socket):
    """Test getting all object types from a single connection."""
    conn = WPConnection()

    # Get all types
    nodes = conn.get_nodes()
    modules = conn.get_modules()
    metadata = conn.get_metadata()

    # Verify they're all lists
    assert isinstance(nodes, list), "nodes should be a list"
    assert isinstance(modules, list), "modules should be a list"
    assert isinstance(metadata, list), "metadata should be a list"



def test_connection_sync_idempotent(pipewire_socket):
    """Test that sync can be called multiple times safely."""
    conn = WPConnection()

    # Call sync many times in a row
    for _ in range(10):
        conn.sync()

    # Should still work after many syncs
    nodes = conn.get_nodes()
    assert isinstance(nodes, list), "Should still get nodes after multiple syncs"



def test_connection_operations_after_creation(pipewire_socket):
    """Test that operations work immediately after connection creation."""
    conn = WPConnection()

    # Should be able to query immediately
    nodes = conn.get_nodes()
    assert isinstance(nodes, list), "Should get nodes immediately"

    modules = conn.get_modules()
    assert isinstance(modules, list), "Should get modules immediately"

    metadata = conn.get_metadata()
    assert isinstance(metadata, list), "Should get metadata immediately"



def test_connection_rapid_operations(pipewire_socket):
    """Test rapid successive operations on the same connection."""
    conn = WPConnection()

    # Rapid queries
    for _ in range(5):
        nodes = conn.get_nodes()
        assert isinstance(nodes, list)

    for _ in range(5):
        modules = conn.get_modules()
        assert isinstance(modules, list)

    for _ in range(5):
        metadata = conn.get_metadata()
        assert isinstance(metadata, list)

