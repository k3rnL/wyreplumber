from typing import List, Dict, Optional, Tuple, Any, final

# Node state constants
WP_NODE_STATE_ERROR: int
WP_NODE_STATE_CREATING: int
WP_NODE_STATE_SUSPENDED: int
WP_NODE_STATE_IDLE: int
WP_NODE_STATE_RUNNING: int

# Port direction constants
WP_DIRECTION_INPUT: int
WP_DIRECTION_OUTPUT: int


class WPPipewireObject:
    """
    Base class for wrappers around WpPipewireObject.
    """

    @property
    def id(self) -> int:
        """The global ID of the object."""
        ...

    @property
    def properties(self) -> Dict[str, str]:
        """All object properties as a dictionary."""
        ...

    def enum_params(self, id: str) -> List[Dict[str, Any]]:
        """
        Enumerate params for a given PipeWire param id.

        Args:
            id: Param id string (for example, "Props", "Format", "EnumFormat").

        Returns:
            A list of dicts with:
            - type (int): SPA pod type
            - size (int): SPA pod body size in bytes
            - data (bytes): raw SPA pod bytes (header + body)
        """
        ...

    def get_param_info(self) -> Dict[str, str]:
        """
        Get the available param ids for this object and their access flags.

        Returns:
            A dict where:
            - key (str): param id string
            - value (str): access flags, using \"r\" (readable) and/or \"w\" (writable)
        """
        ...

    def get_params(self) -> Dict[str, "WPParam"]:
        """
        Fetch available params in one call.

        Returns:
            A mapping of param id to WPParam objects.
        """
        ...


@final
class WPParam:
    """
    Structured PipeWire parameter with permissions and values.
    """

    @property
    def id(self) -> str:
        """PipeWire param id."""
        ...

    @property
    def permissions(self) -> str:
        """Access flags, using \"r\" and/or \"w\"."""
        ...

    @property
    def type(self) -> Optional[int]:
        """SPA pod type of the first value, or None when unavailable."""
        ...

    def get(self, parse: bool = True) -> List[Any]:
        """
        Return current values for this param.

        Args:
            parse: If True (default), parse SPA pods into Python types using wyreplumber.spa_pod.
                   If False, return raw SPA pod dictionaries with 'type', 'size', and 'data' keys.

        Returns:
            List of parsed Python values (when parse=True) or SPA pod dictionaries (when parse=False).
        """
        ...

    def set(self, value: Any, flags: int = 0) -> None:
        """
        Set this param using a Python value or SPA pod.

        Args:
            value: Can be any of:
                - Python value (int, float, bool, str, bytes) - automatically converted to SPA pod
                - SPA pod dictionary with 'type', 'size', and 'data' keys
                - bytes/bytearray/memoryview containing raw SPA pod data
            flags: Optional flags for the set operation (default: 0)

        Raises:
            RuntimeError: If the set operation fails
            ValueError: If the value cannot be converted to a SPA pod
        """
        ...


@final
class WPMetadata:
    """
    Represents a WirePlumber metadata object.

    This object wraps a WpMetadata and provides access to metadata
    properties and manipulation methods.
    """

    @property
    def id(self) -> int:
        """The global ID of the metadata object."""
        ...

    @property
    def properties(self) -> Dict[str, str]:
        """All metadata properties as a dictionary."""
        ...

    def find(self, subject: int, key: str) -> Optional[Tuple[str, str]]:
        """
        Find metadata value by subject and key.

        Args:
            subject: The subject ID to search for
            key: The metadata key

        Returns:
            A tuple of (value, type) if found, None otherwise.
        """
        ...

    def set(self, subject: int, key: str, type: Optional[str] = None, value: Optional[str] = None) -> None:
        """
        Set metadata for a subject and key.

        Args:
            subject: The subject ID
            key: The metadata key
            type: Optional type string
            value: Optional value string. Pass None to unset the metadata.

        Note:
            Changes are cached locally and exported to PipeWire when activated
            with WP_PROXY_FEATURE_BOUND.
        """
        ...

    def clear(self) -> None:
        """
        Remove all stored metadata.

        This clears all metadata entries from this metadata object.
        """
        ...

    def iterate(self, subject: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Iterate over metadata items.

        Args:
            subject: Optional subject ID to filter by. If None, iterates all items.

        Returns:
            A list of dictionaries, each containing:
            - subject (int): The subject ID
            - key (str): The metadata key
            - type (str): The metadata type
            - value (str): The metadata value
        """
        ...


@final
class WPPort(WPPipewireObject):
    """
    Represents a WirePlumber port.

    This object wraps a WpPort and provides access to its properties
    and direction information.
    """

    @property
    def direction(self) -> int:
        """
        The direction of the port.

        Returns one of:
        - WP_DIRECTION_INPUT (0): Port is an input (sink)
        - WP_DIRECTION_OUTPUT (1): Port is an output (source)
        """
        ...


@final
class WPModule:
    """
    Represents a WirePlumber module.

    This object wraps a WpImplModule and provides access to its properties.
    """

    @property
    def name(self) -> Optional[str]:
        """Module name."""
        ...

    @property
    def arguments(self) -> Optional[str]:
        """Module arguments passed during loading."""
        ...

    @property
    def properties(self) -> Dict[str, str]:
        """All module properties as a dictionary."""
        ...


@final
class WPNode(WPPipewireObject):
    """
    Represents a WirePlumber node.

    This object wraps a WpNode and provides access to all its properties,
    state information, and port counts.
    """

    @property
    def state(self) -> int:
        """
        The current state of the node.

        Returns one of:
        - WP_NODE_STATE_ERROR (-1)
        - WP_NODE_STATE_CREATING (0)
        - WP_NODE_STATE_SUSPENDED (1)
        - WP_NODE_STATE_IDLE (2)
        - WP_NODE_STATE_RUNNING (3)
        """
        ...

    @property
    def n_input_ports(self) -> int:
        """Current number of input ports."""
        ...

    @property
    def max_input_ports(self) -> int:
        """Maximum number of input ports supported."""
        ...

    @property
    def n_output_ports(self) -> int:
        """Current number of output ports."""
        ...

    @property
    def max_output_ports(self) -> int:
        """Maximum number of output ports supported."""
        ...

    @property
    def error_message(self) -> Optional[str]:
        """Error message if state is WP_NODE_STATE_ERROR, None otherwise."""
        ...

    def delete(self) -> None:
        """
        Delete this node from the PipeWire server.

        Raises:
            RuntimeError: If the node is already deleted or invalid.
        """
        ...

    def get_ports(self, direction: Optional[int] = None) -> List[WPPort]:
        """
        Get the ports of this node.

        Args:
            direction: Optional direction filter. If specified, only returns ports
                      matching the direction (WP_DIRECTION_INPUT or WP_DIRECTION_OUTPUT).
                      If None, returns all ports.

        Returns:
            A list of WPPort objects representing the node's ports.

        Raises:
            RuntimeError: If the object manager is not available.
            TypeError: If direction is not an integer.
            ValueError: If direction is not WP_DIRECTION_INPUT or WP_DIRECTION_OUTPUT.
        """
        ...


@final
class WPConnection:
    """
    WirePlumber connection that manages communication with PipeWire via WirePlumber.

    Creates a dedicated thread for the WirePlumber event loop on initialization.
    All WirePlumber operations are dispatched to this thread while Python methods
    block until completion.
    """

    def __init__(self) -> None:
        """
        Initialize the WirePlumber connection.

        Creates a background thread where the WirePlumber GMainLoop runs.
        Blocks until the connection is established and the object manager is ready.

        Raises:
            RuntimeError: If the connection fails or thread creation fails.
        """
        ...

    def sync(self) -> None:
        """
        Wait for the WirePlumber event loop to finish processing all pending events.
        """

    def get_nodes(self) -> List[WPNode]:
        """
        Fetch the list of nodes from WirePlumber's object manager.

        This method is thread-safe and blocks from Python's perspective while
        releasing the GIL. The actual work is performed on the WirePlumber thread.

        Returns:
            A list of WPNode objects representing all nodes in the PipeWire graph.

        Raises:
            RuntimeError: If the node retrieval fails.
        """
        ...

    def get_modules(self) -> List[WPModule]:
        """
        Fetch the list of loaded modules from WirePlumber's object manager.

        This method is thread-safe and blocks from Python's perspective while
        releasing the GIL. The actual work is performed on the WirePlumber thread.

        Returns:
            A list of WPModule objects representing all loaded modules.

        Raises:
            RuntimeError: If the module retrieval fails.
        """
        ...

    def get_metadata(self) -> List[WPMetadata]:
        """
        Fetch the list of metadata objects from WirePlumber's object manager.

        This method is thread-safe and blocks from Python's perspective while
        releasing the GIL. The actual work is performed on the WirePlumber thread.

        Returns:
            A list of WPMetadata objects representing all metadata in the PipeWire graph.

        Raises:
            RuntimeError: If the metadata retrieval fails.
        """
        ...

    def load_module(self, name: str, arguments: Optional[str] = None) -> WPModule:
        """
        Load a WirePlumber module.

        Args:
            name: The name of the module to load (e.g., 'libpipewire-module-loopback')
            arguments: Optional arguments to pass to the module

        Returns:
            A WPModule object representing the loaded module.

        Raises:
            RuntimeError: If the module fails to load.
        """
        ...
