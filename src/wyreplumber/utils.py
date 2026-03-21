"""Utility functions for common WirePlumber operations."""

import json
from typing import Any, Optional, Dict, List
from wyreplumber._core import WPConnection, WPMetadata, WPNode


class WPUtils:
    """Utility class for common WirePlumber operations."""

    @staticmethod
    def load_module(module_type: str, name: str, args: Dict[str, Any]) -> None:
        """
        Load a PipeWire module onto the WirePlumber instance using sm-objects metadata object.

        This uses the WirePlumber session manager's metadata to load modules, which is
        the proper way to load modules that persist across the session.

        Args:
            module_type: The type of module to load (e.g., "libpipewire-module-loopback")
            name: Unique name for this module instance
            args: Dictionary of arguments to pass to the module

        Raises:
            Exception: If no sm-objects metadata is found
            RuntimeError: If setting metadata fails

        Example:
            >>> WPUtils.load_module(
            ...     "libpipewire-module-loopback",
            ...     "my-loopback-1",
            ...     {
            ...         "node.description": "My Loopback",
            ...         "capture.props": {"node.name": "my_sink"},
            ...         "playback.props": {"node.name": "my_source"}
            ...     }
            ... )
        """
        conn = WPConnection()
        metas = [m for m in conn.get_metadata() if m.properties.get('metadata.name') == 'sm-objects']
        if len(metas) == 0:
            raise Exception('No sm-objects metadata found')

        sm_objects = metas[0]
        sm_objects_args = {
            "type": "pw-module",
            "name": module_type,
            "args": args
        }

        sm_objects.set(0, name, "Spa:String:JSON", json.dumps(sm_objects_args))
        conn.sync()

    @staticmethod
    def unload_module(name: str) -> None:
        """
        Unload a PipeWire module from the WirePlumber instance.

        Args:
            name: The name of the module instance to unload (same name used in load_module)

        Raises:
            Exception: If no sm-objects metadata is found

        Example:
            >>> WPUtils.unload_module("my-loopback-1")
        """
        conn = WPConnection()
        metas = [m for m in conn.get_metadata() if m.properties.get('metadata.name') == 'sm-objects']
        if len(metas) == 0:
            raise Exception('No sm-objects metadata found')

        sm_objects = metas[0]
        # Unset the metadata to unload the module
        sm_objects.set(0, name, None, None)
        conn.sync()

    @staticmethod
    def find_node_by_name(node_name: str) -> Optional[WPNode]:
        """
        Find a node by its node.name property.

        Args:
            node_name: The value of the "node.name" property to search for

        Returns:
            The WPNode if found, None otherwise

        Example:
            >>> node = WPUtils.find_node_by_name("my_sink")
            >>> if node:
            ...     print(f"Found node with ID: {node.id}")
        """
        conn = WPConnection()
        nodes = conn.get_nodes()

        for node in nodes:
            if node.properties.get("node.name") == node_name:
                return node

        return None

    @staticmethod
    def find_nodes_by_media_class(media_class: str) -> List[WPNode]:
        """
        Find all nodes with a specific media.class.

        Args:
            media_class: The media class to filter by (e.g., "Audio/Sink", "Audio/Source")

        Returns:
            List of WPNode objects matching the media class

        Example:
            >>> sinks = WPUtils.find_nodes_by_media_class("Audio/Sink")
            >>> for sink in sinks:
            ...     print(f"Sink: {sink.properties.get('node.description')}")
        """
        conn = WPConnection()
        nodes = conn.get_nodes()

        return [
            node for node in nodes
            if node.properties.get("media.class") == media_class
        ]

    @staticmethod
    def get_default_sink() -> Optional[WPNode]:
        """
        Get the default audio sink node.

        Returns:
            The default sink WPNode if found, None otherwise

        Example:
            >>> sink = WPUtils.get_default_sink()
            >>> if sink:
            ...     print(f"Default sink: {sink.properties.get('node.description')}")
        """
        conn = WPConnection()
        metas = [m for m in conn.get_metadata() if m.properties.get('metadata.name') == 'default']
        if len(metas) == 0:
            return None

        default_metadata = metas[0]
        result = default_metadata.find(0, "default.audio.sink")

        if result is None:
            return None

        default_sink_name, _ = result

        # Find the node by name
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == default_sink_name:
                return node

        return None

    @staticmethod
    def get_default_source() -> Optional[WPNode]:
        """
        Get the default audio source node.

        Returns:
            The default source WPNode if found, None otherwise

        Example:
            >>> source = WPUtils.get_default_source()
            >>> if source:
            ...     print(f"Default source: {source.properties.get('node.description')}")
        """
        conn = WPConnection()
        metas = [m for m in conn.get_metadata() if m.properties.get('metadata.name') == 'default']
        if len(metas) == 0:
            return None

        default_metadata = metas[0]
        result = default_metadata.find(0, "default.audio.source")

        if result is None:
            return None

        default_source_name, _ = result

        # Find the node by name
        nodes = conn.get_nodes()
        for node in nodes:
            if node.properties.get("node.name") == default_source_name:
                return node

        return None

    @staticmethod
    def set_default_sink(node_name: str) -> None:
        """
        Set the default audio sink.

        Args:
            node_name: The node.name of the sink to set as default

        Raises:
            Exception: If no default metadata is found

        Example:
            >>> WPUtils.set_default_sink("my_custom_sink")
        """
        conn = WPConnection()
        metas = [m for m in conn.get_metadata() if m.properties.get('metadata.name') == 'default']
        if len(metas) == 0:
            raise Exception('No default metadata found')

        default_metadata = metas[0]
        default_metadata.set(0, "default.audio.sink", "Spa:String:JSON", json.dumps({"name": node_name}))
        conn.sync()

    @staticmethod
    def set_default_source(node_name: str) -> None:
        """
        Set the default audio source.

        Args:
            node_name: The node.name of the source to set as default

        Raises:
            Exception: If no default metadata is found

        Example:
            >>> WPUtils.set_default_source("my_custom_source")
        """
        conn = WPConnection()
        metas = [m for m in conn.get_metadata() if m.properties.get('metadata.name') == 'default']
        if len(metas) == 0:
            raise Exception('No default metadata found')

        default_metadata = metas[0]
        default_metadata.set(0, "default.audio.source", "Spa:String:JSON", json.dumps({"name": node_name}))
        conn.sync()

    @staticmethod
    def list_all_nodes() -> List[Dict[str, Any]]:
        """
        Get a list of all nodes with their basic information.

        Returns:
            List of dictionaries containing node information

        Example:
            >>> nodes = WPUtils.list_all_nodes()
            >>> for node_info in nodes:
            ...     print(f"{node_info['id']}: {node_info['name']} ({node_info['media_class']})")
        """
        conn = WPConnection()
        nodes = conn.get_nodes()

        return [
            {
                "id": node.id,
                "name": node.properties.get("node.name", "unknown"),
                "description": node.properties.get("node.description", ""),
                "media_class": node.properties.get("media.class", ""),
                "state": node.state,
                "n_input_ports": node.n_input_ports,
                "n_output_ports": node.n_output_ports,
            }
            for node in nodes
        ]

    @staticmethod
    def wait_for_node(node_name: str, timeout: float = 5.0) -> Optional[WPNode]:
        """
        Wait for a node to appear by name.

        Args:
            node_name: The node.name to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            The WPNode if found within timeout, None otherwise

        Example:
            >>> node = WPUtils.wait_for_node("my_new_sink", timeout=10.0)
            >>> if node:
            ...     print("Node appeared!")
            ... else:
            ...     print("Node did not appear within timeout")
        """
        import time
        conn = WPConnection()
        deadline = time.time() + timeout

        while time.time() < deadline:
            nodes = conn.get_nodes()
            for node in nodes:
                if node.properties.get("node.name") == node_name:
                    return node
            conn.sync()
            time.sleep(0.1)

        return None
