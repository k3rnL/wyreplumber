"""Internal SPA pod constants, property specs, and typed object classes."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
import struct
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


# SPA pod type constants
SPA_TYPE_None = 1
SPA_TYPE_Bool = 2
SPA_TYPE_Id = 3
SPA_TYPE_Int = 4
SPA_TYPE_Long = 5
SPA_TYPE_Float = 6
SPA_TYPE_Double = 7
SPA_TYPE_String = 8
SPA_TYPE_Bytes = 9
SPA_TYPE_Rectangle = 10
SPA_TYPE_Fraction = 11
SPA_TYPE_Bitmap = 12
SPA_TYPE_Array = 13
SPA_TYPE_Struct = 14
SPA_TYPE_Object = 15
SPA_TYPE_Sequence = 16
SPA_TYPE_Pointer = 17
SPA_TYPE_Fd = 18
SPA_TYPE_Choice = 19
SPA_TYPE_Pod = 20

# SPA choice constants
SPA_CHOICE_None = 0
SPA_CHOICE_Range = 1
SPA_CHOICE_Step = 2
SPA_CHOICE_Enum = 3
SPA_CHOICE_Flags = 4

# SPA pointer type constants
SPA_TYPE_POINTER_START = 0x10000
SPA_TYPE_POINTER_Buffer = SPA_TYPE_POINTER_START + 1
SPA_TYPE_POINTER_Meta = SPA_TYPE_POINTER_START + 2
SPA_TYPE_POINTER_Dict = SPA_TYPE_POINTER_START + 3

# SPA object type constants
SPA_TYPE_OBJECT_START = 0x40000
SPA_TYPE_OBJECT_PropInfo = SPA_TYPE_OBJECT_START + 1
SPA_TYPE_OBJECT_Props = SPA_TYPE_OBJECT_START + 2
SPA_TYPE_OBJECT_Format = SPA_TYPE_OBJECT_START + 3
SPA_TYPE_OBJECT_ParamBuffers = SPA_TYPE_OBJECT_START + 4
SPA_TYPE_OBJECT_ParamMeta = SPA_TYPE_OBJECT_START + 5
SPA_TYPE_OBJECT_ParamIO = SPA_TYPE_OBJECT_START + 6
SPA_TYPE_OBJECT_ParamProfile = SPA_TYPE_OBJECT_START + 7
SPA_TYPE_OBJECT_ParamPortConfig = SPA_TYPE_OBJECT_START + 8
SPA_TYPE_OBJECT_ParamRoute = SPA_TYPE_OBJECT_START + 9
SPA_TYPE_OBJECT_Profiler = SPA_TYPE_OBJECT_START + 10
SPA_TYPE_OBJECT_ParamLatency = SPA_TYPE_OBJECT_START + 11
SPA_TYPE_OBJECT_ParamProcessLatency = SPA_TYPE_OBJECT_START + 12
SPA_TYPE_OBJECT_ParamTag = SPA_TYPE_OBJECT_START + 13
SPA_TYPE_OBJECT_ParamDict = SPA_TYPE_OBJECT_START + 14
SPA_TYPE_OBJECT_PeerParam = SPA_TYPE_OBJECT_START + 15

# SPA direction constants
SPA_DIRECTION_INPUT = 0
SPA_DIRECTION_OUTPUT = 1

# SPA param constants
SPA_PARAM_Invalid = 0
SPA_PARAM_PropInfo = 1
SPA_PARAM_Props = 2
SPA_PARAM_EnumFormat = 3
SPA_PARAM_Format = 4
SPA_PARAM_Buffers = 5
SPA_PARAM_Meta = 6
SPA_PARAM_IO = 7
SPA_PARAM_EnumProfile = 8
SPA_PARAM_Profile = 9
SPA_PARAM_EnumPortConfig = 10
SPA_PARAM_PortConfig = 11
SPA_PARAM_EnumRoute = 12
SPA_PARAM_Route = 13
SPA_PARAM_Control = 14
SPA_PARAM_Latency = 15
SPA_PARAM_ProcessLatency = 16
SPA_PARAM_Tag = 17
SPA_PARAM_PeerEnumFormat = 18
SPA_PARAM_Capability = 19
SPA_PARAM_PeerCapability = 20

# Common SPA enums from format.h
SPA_MEDIA_TYPE_unknown = 0
SPA_MEDIA_TYPE_audio = 1
SPA_MEDIA_TYPE_video = 2
SPA_MEDIA_TYPE_image = 3
SPA_MEDIA_TYPE_binary = 4
SPA_MEDIA_TYPE_stream = 5
SPA_MEDIA_TYPE_application = 6

SPA_MEDIA_SUBTYPE_unknown = 0
SPA_MEDIA_SUBTYPE_raw = 1
SPA_MEDIA_SUBTYPE_dsp = 2
SPA_MEDIA_SUBTYPE_iec958 = 3
SPA_MEDIA_SUBTYPE_dsd = 4
SPA_MEDIA_SUBTYPE_mp3 = 5
SPA_MEDIA_SUBTYPE_aac = 6
SPA_MEDIA_SUBTYPE_vorbis = 7
SPA_MEDIA_SUBTYPE_wma = 8
SPA_MEDIA_SUBTYPE_ra = 9
SPA_MEDIA_SUBTYPE_sbc = 10
SPA_MEDIA_SUBTYPE_adpcm = 11
SPA_MEDIA_SUBTYPE_g723 = 12
SPA_MEDIA_SUBTYPE_g726 = 13
SPA_MEDIA_SUBTYPE_g729 = 14
SPA_MEDIA_SUBTYPE_amr = 15
SPA_MEDIA_SUBTYPE_gsm = 16
SPA_MEDIA_SUBTYPE_alac = 17
SPA_MEDIA_SUBTYPE_flac = 18
SPA_MEDIA_SUBTYPE_ape = 19
SPA_MEDIA_SUBTYPE_opus = 20
SPA_MEDIA_SUBTYPE_midi = 21
SPA_MEDIA_SUBTYPE_control = 22
SPA_MEDIA_SUBTYPE_mpegts = 23
SPA_MEDIA_SUBTYPE_h264 = 24
SPA_MEDIA_SUBTYPE_mjpg = 25
SPA_MEDIA_SUBTYPE_dv = 26
SPA_MEDIA_SUBTYPE_mpeg1 = 27
SPA_MEDIA_SUBTYPE_mpeg2 = 28
SPA_MEDIA_SUBTYPE_mpeg4 = 29
SPA_MEDIA_SUBTYPE_xvid = 30
SPA_MEDIA_SUBTYPE_vc1 = 31
SPA_MEDIA_SUBTYPE_vp8 = 32
SPA_MEDIA_SUBTYPE_vp9 = 33
SPA_MEDIA_SUBTYPE_bayer = 34
SPA_MEDIA_SUBTYPE_jpeg = 35
SPA_MEDIA_SUBTYPE_svg = 36
SPA_MEDIA_SUBTYPE_rar = 37
SPA_MEDIA_SUBTYPE_swf = 38
SPA_MEDIA_SUBTYPE_binhex = 39
SPA_MEDIA_SUBTYPE_font_ttf = 40
SPA_MEDIA_SUBTYPE_font_type1 = 41
SPA_MEDIA_SUBTYPE_archive = 42
SPA_MEDIA_SUBTYPE_3gpp = 43
SPA_MEDIA_SUBTYPE_quicktime = 44
SPA_MEDIA_SUBTYPE_webm = 45
SPA_MEDIA_SUBTYPE_riff = 46
SPA_MEDIA_SUBTYPE_smil = 47
SPA_MEDIA_SUBTYPE_wm = 48
SPA_MEDIA_SUBTYPE_h265 = 49
SPA_MEDIA_SUBTYPE_av1 = 50
SPA_MEDIA_SUBTYPE_transport = 51
SPA_MEDIA_SUBTYPE_json = 52

# Port configuration mode constants
SPA_PARAM_PORT_CONFIG_MODE_none = 0
SPA_PARAM_PORT_CONFIG_MODE_passthrough = 1
SPA_PARAM_PORT_CONFIG_MODE_convert = 2
SPA_PARAM_PORT_CONFIG_MODE_dsp = 3

# Availability constants
SPA_PARAM_AVAILABILITY_unknown = 0
SPA_PARAM_AVAILABILITY_no = 1
SPA_PARAM_AVAILABILITY_yes = 2

# Bitorder constants
SPA_PARAM_BITORDER_unknown = 0
SPA_PARAM_BITORDER_msb = 1
SPA_PARAM_BITORDER_lsb = 2

# Control type constants
SPA_CONTROL_Invalid = 0
SPA_CONTROL_Properties = 1
SPA_CONTROL_Midi = 2
SPA_CONTROL_OSC = 3

# PropInfo keys
SPA_PROP_INFO_START = 0
SPA_PROP_INFO_id = SPA_PROP_INFO_START + 1
SPA_PROP_INFO_name = SPA_PROP_INFO_START + 2
SPA_PROP_INFO_type = SPA_PROP_INFO_START + 3
SPA_PROP_INFO_labels = SPA_PROP_INFO_START + 4
SPA_PROP_INFO_container = SPA_PROP_INFO_START + 5
SPA_PROP_INFO_params = SPA_PROP_INFO_START + 6
SPA_PROP_INFO_description = SPA_PROP_INFO_START + 7

# Props keys
SPA_PROP_START = 0
SPA_PROP_unknown = SPA_PROP_START + 1
SPA_PROP_START_Device = 0x100
SPA_PROP_device = SPA_PROP_START_Device + 1
SPA_PROP_deviceName = SPA_PROP_START_Device + 2
SPA_PROP_deviceFd = SPA_PROP_START_Device + 3
SPA_PROP_card = SPA_PROP_START_Device + 4
SPA_PROP_cardName = SPA_PROP_START_Device + 5
SPA_PROP_minLatency = SPA_PROP_START_Device + 6
SPA_PROP_maxLatency = SPA_PROP_START_Device + 7
SPA_PROP_periods = SPA_PROP_START_Device + 8
SPA_PROP_periodSize = SPA_PROP_START_Device + 9
SPA_PROP_periodEvent = SPA_PROP_START_Device + 10
SPA_PROP_live = SPA_PROP_START_Device + 11
SPA_PROP_rate = SPA_PROP_START_Device + 12
SPA_PROP_quality = SPA_PROP_START_Device + 13
SPA_PROP_bluetoothAudioCodec = SPA_PROP_START_Device + 14
SPA_PROP_bluetoothOffloadActive = SPA_PROP_START_Device + 15
SPA_PROP_params = SPA_PROP_START_Device + 16
SPA_PROP_clockId = SPA_PROP_START_Device + 17
SPA_PROP_clockName = SPA_PROP_START_Device + 18
SPA_PROP_clockQuantumLimit = SPA_PROP_START_Device + 19
SPA_PROP_clockMinQuantum = SPA_PROP_START_Device + 20
SPA_PROP_clockMaxQuantum = SPA_PROP_START_Device + 21
SPA_PROP_clockRate = SPA_PROP_START_Device + 22
SPA_PROP_clockAllowedRates = SPA_PROP_START_Device + 23
SPA_PROP_clockForceRates = SPA_PROP_START_Device + 24
SPA_PROP_START_Audio = 0x10000
SPA_PROP_waveType = SPA_PROP_START_Audio + 1
SPA_PROP_frequency = SPA_PROP_START_Audio + 2
SPA_PROP_volume = SPA_PROP_START_Audio + 3
SPA_PROP_mute = SPA_PROP_START_Audio + 4
SPA_PROP_patternType = SPA_PROP_START_Audio + 5
SPA_PROP_ditherType = SPA_PROP_START_Audio + 6
SPA_PROP_truncate = SPA_PROP_START_Audio + 7
SPA_PROP_channelVolumes = SPA_PROP_START_Audio + 8
SPA_PROP_volumeBase = SPA_PROP_START_Audio + 9
SPA_PROP_volumeStep = SPA_PROP_START_Audio + 10
SPA_PROP_channelMap = SPA_PROP_START_Audio + 11
SPA_PROP_monitorMute = SPA_PROP_START_Audio + 12
SPA_PROP_monitorVolumes = SPA_PROP_START_Audio + 13
SPA_PROP_latencyOffsetNsec = SPA_PROP_START_Audio + 14
SPA_PROP_softMute = SPA_PROP_START_Audio + 15
SPA_PROP_softVolumes = SPA_PROP_START_Audio + 16
SPA_PROP_iec958Codecs = SPA_PROP_START_Audio + 17
SPA_PROP_volumeRampSamples = SPA_PROP_START_Audio + 18
SPA_PROP_volumeRampStepSamples = SPA_PROP_START_Audio + 19
SPA_PROP_volumeRampTime = SPA_PROP_START_Audio + 20
SPA_PROP_volumeRampStepTime = SPA_PROP_START_Audio + 21
SPA_PROP_volumeRampScale = SPA_PROP_START_Audio + 22
SPA_PROP_START_Video = 0x20000
SPA_PROP_brightness = SPA_PROP_START_Video + 1
SPA_PROP_contrast = SPA_PROP_START_Video + 2
SPA_PROP_saturation = SPA_PROP_START_Video + 3
SPA_PROP_hue = SPA_PROP_START_Video + 4
SPA_PROP_gamma = SPA_PROP_START_Video + 5
SPA_PROP_exposure = SPA_PROP_START_Video + 6
SPA_PROP_gain = SPA_PROP_START_Video + 7
SPA_PROP_sharpness = SPA_PROP_START_Video + 8

# Format keys
SPA_FORMAT_START = 0
SPA_FORMAT_mediaType = SPA_FORMAT_START + 1
SPA_FORMAT_mediaSubtype = SPA_FORMAT_START + 2
SPA_FORMAT_START_Audio = 0x10000
SPA_FORMAT_AUDIO_format = SPA_FORMAT_START_Audio + 1
SPA_FORMAT_AUDIO_flags = SPA_FORMAT_START_Audio + 2
SPA_FORMAT_AUDIO_rate = SPA_FORMAT_START_Audio + 3
SPA_FORMAT_AUDIO_channels = SPA_FORMAT_START_Audio + 4
SPA_FORMAT_AUDIO_position = SPA_FORMAT_START_Audio + 5
SPA_FORMAT_AUDIO_iec958Codec = SPA_FORMAT_START_Audio + 6
SPA_FORMAT_AUDIO_bitorder = SPA_FORMAT_START_Audio + 7
SPA_FORMAT_AUDIO_interleave = SPA_FORMAT_START_Audio + 8
SPA_FORMAT_AUDIO_bitrate = SPA_FORMAT_START_Audio + 9
SPA_FORMAT_AUDIO_blockAlign = SPA_FORMAT_START_Audio + 10
SPA_FORMAT_AUDIO_AAC_streamFormat = SPA_FORMAT_START_Audio + 11
SPA_FORMAT_AUDIO_WMA_profile = SPA_FORMAT_START_Audio + 12
SPA_FORMAT_AUDIO_AMR_bandMode = SPA_FORMAT_START_Audio + 13
SPA_FORMAT_AUDIO_MP3_channelMode = SPA_FORMAT_START_Audio + 14
SPA_FORMAT_AUDIO_DTS_extType = SPA_FORMAT_START_Audio + 15
SPA_FORMAT_START_Video = 0x20000
SPA_FORMAT_VIDEO_format = SPA_FORMAT_START_Video + 1
SPA_FORMAT_VIDEO_modifier = SPA_FORMAT_START_Video + 2
SPA_FORMAT_VIDEO_size = SPA_FORMAT_START_Video + 3
SPA_FORMAT_VIDEO_framerate = SPA_FORMAT_START_Video + 4
SPA_FORMAT_VIDEO_maxFramerate = SPA_FORMAT_START_Video + 5
SPA_FORMAT_VIDEO_views = SPA_FORMAT_START_Video + 6
SPA_FORMAT_VIDEO_interlaceMode = SPA_FORMAT_START_Video + 7
SPA_FORMAT_VIDEO_pixelAspectRatio = SPA_FORMAT_START_Video + 8
SPA_FORMAT_VIDEO_multiviewMode = SPA_FORMAT_START_Video + 9
SPA_FORMAT_VIDEO_multiviewFlags = SPA_FORMAT_START_Video + 10
SPA_FORMAT_VIDEO_chromaSite = SPA_FORMAT_START_Video + 11
SPA_FORMAT_VIDEO_colorRange = SPA_FORMAT_START_Video + 12
SPA_FORMAT_VIDEO_colorMatrix = SPA_FORMAT_START_Video + 13
SPA_FORMAT_VIDEO_transferFunction = SPA_FORMAT_START_Video + 14
SPA_FORMAT_VIDEO_colorPrimaries = SPA_FORMAT_START_Video + 15
SPA_FORMAT_VIDEO_profile = SPA_FORMAT_START_Video + 16
SPA_FORMAT_VIDEO_level = SPA_FORMAT_START_Video + 17
SPA_FORMAT_VIDEO_H264_streamFormat = SPA_FORMAT_START_Video + 18
SPA_FORMAT_VIDEO_H264_alignment = SPA_FORMAT_START_Video + 19
SPA_FORMAT_VIDEO_H265_streamFormat = SPA_FORMAT_START_Video + 20
SPA_FORMAT_VIDEO_H265_alignment = SPA_FORMAT_START_Video + 21
SPA_FORMAT_VIDEO_deviceId = SPA_FORMAT_START_Video + 22
SPA_FORMAT_START_Image = 0x30000
SPA_FORMAT_START_Binary = 0x40000
SPA_FORMAT_START_Stream = 0x50000
SPA_FORMAT_START_Application = 0x60000
SPA_FORMAT_CONTROL_types = SPA_FORMAT_START_Application + 1

# ParamBuffers keys
SPA_PARAM_BUFFERS_START = 0
SPA_PARAM_BUFFERS_buffers = SPA_PARAM_BUFFERS_START + 1
SPA_PARAM_BUFFERS_blocks = SPA_PARAM_BUFFERS_START + 2
SPA_PARAM_BUFFERS_size = SPA_PARAM_BUFFERS_START + 3
SPA_PARAM_BUFFERS_stride = SPA_PARAM_BUFFERS_START + 4
SPA_PARAM_BUFFERS_align = SPA_PARAM_BUFFERS_START + 5
SPA_PARAM_BUFFERS_dataType = SPA_PARAM_BUFFERS_START + 6
SPA_PARAM_BUFFERS_metaType = SPA_PARAM_BUFFERS_START + 7

# ParamMeta keys
SPA_PARAM_META_START = 0
SPA_PARAM_META_type = SPA_PARAM_META_START + 1
SPA_PARAM_META_size = SPA_PARAM_META_START + 2
SPA_PARAM_META_features = SPA_PARAM_META_START + 3

# ParamIO keys
SPA_PARAM_IO_START = 0
SPA_PARAM_IO_id = SPA_PARAM_IO_START + 1
SPA_PARAM_IO_size = SPA_PARAM_IO_START + 2

# ParamProfile keys
SPA_PARAM_PROFILE_START = 0
SPA_PARAM_PROFILE_index = SPA_PARAM_PROFILE_START + 1
SPA_PARAM_PROFILE_name = SPA_PARAM_PROFILE_START + 2
SPA_PARAM_PROFILE_description = SPA_PARAM_PROFILE_START + 3
SPA_PARAM_PROFILE_priority = SPA_PARAM_PROFILE_START + 4
SPA_PARAM_PROFILE_available = SPA_PARAM_PROFILE_START + 5
SPA_PARAM_PROFILE_info = SPA_PARAM_PROFILE_START + 6
SPA_PARAM_PROFILE_classes = SPA_PARAM_PROFILE_START + 7
SPA_PARAM_PROFILE_save = SPA_PARAM_PROFILE_START + 8

# ParamPortConfig keys
SPA_PARAM_PORT_CONFIG_START = 0
SPA_PARAM_PORT_CONFIG_direction = SPA_PARAM_PORT_CONFIG_START + 1
SPA_PARAM_PORT_CONFIG_mode = SPA_PARAM_PORT_CONFIG_START + 2
SPA_PARAM_PORT_CONFIG_monitor = SPA_PARAM_PORT_CONFIG_START + 3
SPA_PARAM_PORT_CONFIG_control = SPA_PARAM_PORT_CONFIG_START + 4
SPA_PARAM_PORT_CONFIG_format = SPA_PARAM_PORT_CONFIG_START + 5

# ParamRoute keys
SPA_PARAM_ROUTE_START = 0
SPA_PARAM_ROUTE_index = SPA_PARAM_ROUTE_START + 1
SPA_PARAM_ROUTE_direction = SPA_PARAM_ROUTE_START + 2
SPA_PARAM_ROUTE_device = SPA_PARAM_ROUTE_START + 3
SPA_PARAM_ROUTE_name = SPA_PARAM_ROUTE_START + 4
SPA_PARAM_ROUTE_description = SPA_PARAM_ROUTE_START + 5
SPA_PARAM_ROUTE_priority = SPA_PARAM_ROUTE_START + 6
SPA_PARAM_ROUTE_available = SPA_PARAM_ROUTE_START + 7
SPA_PARAM_ROUTE_info = SPA_PARAM_ROUTE_START + 8
SPA_PARAM_ROUTE_profiles = SPA_PARAM_ROUTE_START + 9
SPA_PARAM_ROUTE_props = SPA_PARAM_ROUTE_START + 10
SPA_PARAM_ROUTE_devices = SPA_PARAM_ROUTE_START + 11
SPA_PARAM_ROUTE_profile = SPA_PARAM_ROUTE_START + 12
SPA_PARAM_ROUTE_save = SPA_PARAM_ROUTE_START + 13

# ParamLatency keys
SPA_PARAM_LATENCY_START = 0
SPA_PARAM_LATENCY_direction = SPA_PARAM_LATENCY_START + 1
SPA_PARAM_LATENCY_minQuantum = SPA_PARAM_LATENCY_START + 2
SPA_PARAM_LATENCY_maxQuantum = SPA_PARAM_LATENCY_START + 3
SPA_PARAM_LATENCY_minRate = SPA_PARAM_LATENCY_START + 4
SPA_PARAM_LATENCY_maxRate = SPA_PARAM_LATENCY_START + 5
SPA_PARAM_LATENCY_minNs = SPA_PARAM_LATENCY_START + 6
SPA_PARAM_LATENCY_maxNs = SPA_PARAM_LATENCY_START + 7

# ParamProcessLatency keys
SPA_PARAM_PROCESS_LATENCY_START = 0
SPA_PARAM_PROCESS_LATENCY_quantum = SPA_PARAM_PROCESS_LATENCY_START + 1
SPA_PARAM_PROCESS_LATENCY_rate = SPA_PARAM_PROCESS_LATENCY_START + 2
SPA_PARAM_PROCESS_LATENCY_ns = SPA_PARAM_PROCESS_LATENCY_START + 3

# ParamTag / ParamDict / PeerParam keys
SPA_PARAM_TAG_START = 0
SPA_PARAM_TAG_direction = SPA_PARAM_TAG_START + 1
SPA_PARAM_TAG_info = SPA_PARAM_TAG_START + 2

SPA_PARAM_DICT_START = 0
SPA_PARAM_DICT_info = SPA_PARAM_DICT_START + 1

SPA_PEER_PARAM_START = 0
SPA_PEER_PARAM_END = 0xFFFFFFFE


@dataclass(frozen=True)
class PropertySpec:
    key: int
    name: str
    pod_type: Optional[int] = None
    shape: Optional[str] = None


def _object_property(spec: PropertySpec) -> property:
    def getter(self: "SpaPodObject") -> Any:
        return self.get(spec.name)

    def setter(self: "SpaPodObject", value: Any) -> None:
        self[spec.name] = value

    return property(
        getter,
        setter,
        doc=(
            f"SPA property `{spec.name}` with numeric key `{spec.key}`. "
            "Accessible by attribute, string key, or numeric enum key."
        ),
    )


class SpaPodObject(MutableMapping[Any, Any]):
    """
    Base class for known SPA object pods.

    Instances behave like mutable mappings while also exposing known properties
    as normal Python attributes for convenience and auto-completion.
    """

    SPA_OBJECT_TYPE = SPA_TYPE_Object
    SPA_OBJECT_ID = SPA_PARAM_Invalid
    SPA_OBJECT_NAME: Optional[str] = None
    _property_specs_by_key: Dict[int, PropertySpec] = {}
    _property_specs_by_name: Dict[str, PropertySpec] = {}

    def __init__(
        self,
        properties: Optional[Mapping[Any, Any]] = None,
        *,
        property_flags: Optional[Mapping[Any, int]] = None,
        property_keys: Optional[Mapping[str, int]] = None,
        object_type: Optional[int] = None,
        object_id: Optional[int] = None,
        object_name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        object.__setattr__(self, "_properties", {})
        object.__setattr__(self, "property_flags", dict(property_flags or {}))
        object.__setattr__(self, "property_keys", dict(property_keys or {}))
        object.__setattr__(self, "_object_type", self.SPA_OBJECT_TYPE if object_type is None else int(object_type))
        object.__setattr__(self, "_object_id", self.SPA_OBJECT_ID if object_id is None else int(object_id))
        object.__setattr__(
            self,
            "_object_name",
            self.SPA_OBJECT_NAME if object_name is None else object_name,
        )

        merged: Dict[Any, Any] = {}
        if properties is not None:
            merged.update(dict(properties))
        merged.update(kwargs)
        for key, value in merged.items():
            self[key] = value

    @property
    def object_type(self) -> int:
        return self._object_type

    @property
    def object_id(self) -> int:
        return self._object_id

    @property
    def object_name(self) -> Optional[str]:
        return self._object_name

    def _key_to_storage(self, key: Any) -> Any:
        if isinstance(key, int):
            spec = self._property_specs_by_key.get(key)
            if spec is not None:
                self.property_keys.setdefault(spec.name, key)
                return spec.name
            return key
        if isinstance(key, str):
            spec = self._property_specs_by_name.get(key)
            if spec is not None:
                self.property_keys.setdefault(spec.name, spec.key)
                return spec.name
            return key
        raise KeyError(key)

    def _resolve_existing_key(self, key: Any) -> Any:
        if key in self._properties:
            return key
        if isinstance(key, int):
            spec = self._property_specs_by_key.get(key)
            if spec is not None and spec.name in self._properties:
                return spec.name
            return key
        if isinstance(key, str):
            spec = self._property_specs_by_name.get(key)
            if spec is not None and spec.name in self._properties:
                return spec.name
            return key
        raise KeyError(key)

    def __getitem__(self, key: Any) -> Any:
        return self._properties[self._resolve_existing_key(key)]

    def __setitem__(self, key: Any, value: Any) -> None:
        storage_key = self._key_to_storage(key)
        self._properties[storage_key] = value
        if storage_key not in self.property_flags:
            flag_key = storage_key if storage_key in self._property_specs_by_name else key
            self.property_flags[storage_key] = int(self.property_flags.get(flag_key, 0))

    def __delitem__(self, key: Any) -> None:
        storage_key = self._resolve_existing_key(key)
        del self._properties[storage_key]
        self.property_flags.pop(storage_key, None)
        if isinstance(storage_key, str):
            self.property_keys.pop(storage_key, None)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._properties)

    def __len__(self) -> int:
        return len(self._properties)

    def __getattr__(self, name: str) -> Any:
        spec = self._property_specs_by_name.get(name)
        if spec is not None:
            return self.get(name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name in {"property_flags", "property_keys"}:
            object.__setattr__(self, name, value)
            return
        if name in self._property_specs_by_name:
            self[name] = value
            return
        object.__setattr__(self, name, value)

    def __dir__(self) -> List[str]:
        return sorted(set(super().__dir__()) | set(self._property_specs_by_name) | set(self._properties))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._properties!r})"

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> Any:
        return self._properties.keys()

    def items(self) -> Any:
        return self._properties.items()

    def values(self) -> Any:
        return self._properties.values()

    def as_pod_mapping(self) -> Dict[str, Any]:
        """Return the generic mapping form used internally for raw SPA object pods."""
        return {
            "_pod_type": SPA_TYPE_Object,
            "_object_type": self.object_type,
            "_object_id": self.object_id,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "properties": dict(self._properties),
            "property_flags": dict(self.property_flags),
            "property_keys": dict(self.property_keys),
        }


def _align(value: int, alignment: int = 8) -> int:
    """Align a value to the specified alignment."""
    return (value + alignment - 1) & ~(alignment - 1)


def _parse_pod_header(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Parse a SPA pod header and return `(size, type)`."""
    if len(data) < offset + 8:
        raise ValueError("Data too short for SPA pod header")
    return struct.unpack_from("<II", data, offset)


def _ensure_available(data: bytes, offset: int, size: int) -> None:
    if len(data) < offset + size:
        raise ValueError("Data too short for SPA pod body")


def _pack_pod(pod_type: int, body: bytes) -> bytes:
    padding = _align(8 + len(body)) - (8 + len(body))
    return struct.pack("<II", len(body), pod_type) + body + (b"\x00" * padding)


def _explicit_pod_type(value: Any) -> Optional[int]:
    if isinstance(value, Mapping):
        pod_type = value.get("_pod_type")
        if isinstance(pod_type, int):
            return pod_type
        pod_type = value.get("pod_type")
        if isinstance(pod_type, int):
            return pod_type
    return None


def _object_param_name(object_id: int) -> Optional[str]:
    return OBJECT_ID_TO_NAME.get(object_id)


def _object_type_for_id(object_id: int) -> Optional[int]:
    return OBJECT_ID_TO_TYPE.get(object_id)


def _property_spec_by_key(object_id: int, prop_key: int) -> Optional[PropertySpec]:
    return OBJECT_PROPERTY_SPECS.get(object_id, {}).get(prop_key)


def _property_spec_by_name(object_id: int, name: str) -> Optional[PropertySpec]:
    return OBJECT_PROPERTY_NAMES.get(object_id, {}).get(name)


def _make_property_table(specs: Sequence[PropertySpec]) -> Tuple[Dict[int, PropertySpec], Dict[str, PropertySpec]]:
    by_key = {spec.key: spec for spec in specs}
    by_name = {spec.name: spec for spec in specs}
    return by_key, by_name


PROP_INFO_SPECS = [
    PropertySpec(SPA_PROP_INFO_id, "id", SPA_TYPE_Id),
    PropertySpec(SPA_PROP_INFO_name, "name", SPA_TYPE_String),
    PropertySpec(SPA_PROP_INFO_type, "type"),
    PropertySpec(SPA_PROP_INFO_labels, "labels", SPA_TYPE_Struct, "labels"),
    PropertySpec(SPA_PROP_INFO_container, "container", SPA_TYPE_Id),
    PropertySpec(SPA_PROP_INFO_params, "params", SPA_TYPE_Bool),
    PropertySpec(SPA_PROP_INFO_description, "description", SPA_TYPE_String),
]

PROPS_SPECS = [
    PropertySpec(SPA_PROP_unknown, "unknown"),
    PropertySpec(SPA_PROP_device, "device", SPA_TYPE_String),
    PropertySpec(SPA_PROP_deviceName, "deviceName", SPA_TYPE_String),
    PropertySpec(SPA_PROP_deviceFd, "deviceFd", SPA_TYPE_Fd),
    PropertySpec(SPA_PROP_card, "card", SPA_TYPE_String),
    PropertySpec(SPA_PROP_cardName, "cardName", SPA_TYPE_String),
    PropertySpec(SPA_PROP_minLatency, "minLatency", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_maxLatency, "maxLatency", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_periods, "periods", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_periodSize, "periodSize", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_periodEvent, "periodEvent", SPA_TYPE_Bool),
    PropertySpec(SPA_PROP_live, "live", SPA_TYPE_Bool),
    PropertySpec(SPA_PROP_rate, "rate", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_quality, "quality", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_bluetoothAudioCodec, "bluetoothAudioCodec", SPA_TYPE_Id),
    PropertySpec(SPA_PROP_bluetoothOffloadActive, "bluetoothOffloadActive", SPA_TYPE_Bool),
    PropertySpec(SPA_PROP_params, "params", SPA_TYPE_Struct, "params"),
    PropertySpec(SPA_PROP_clockId, "clockId", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_clockName, "clockName", SPA_TYPE_String),
    PropertySpec(SPA_PROP_clockQuantumLimit, "clockQuantumLimit", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_clockMinQuantum, "clockMinQuantum", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_clockMaxQuantum, "clockMaxQuantum", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_clockRate, "clockRate", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_clockAllowedRates, "clockAllowedRates", SPA_TYPE_Array, "array_int"),
    PropertySpec(SPA_PROP_clockForceRates, "clockForceRates", SPA_TYPE_Array, "array_int"),
    PropertySpec(SPA_PROP_waveType, "waveType", SPA_TYPE_Id),
    PropertySpec(SPA_PROP_frequency, "frequency", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_volume, "volume", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_mute, "mute", SPA_TYPE_Bool),
    PropertySpec(SPA_PROP_patternType, "patternType", SPA_TYPE_Id),
    PropertySpec(SPA_PROP_ditherType, "ditherType", SPA_TYPE_Id),
    PropertySpec(SPA_PROP_truncate, "truncate", SPA_TYPE_Bool),
    PropertySpec(SPA_PROP_channelVolumes, "channelVolumes", SPA_TYPE_Array, "array_float"),
    PropertySpec(SPA_PROP_volumeBase, "volumeBase", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_volumeStep, "volumeStep", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_channelMap, "channelMap", SPA_TYPE_Array, "array_id"),
    PropertySpec(SPA_PROP_monitorMute, "monitorMute", SPA_TYPE_Bool),
    PropertySpec(SPA_PROP_monitorVolumes, "monitorVolumes", SPA_TYPE_Array, "array_float"),
    PropertySpec(SPA_PROP_latencyOffsetNsec, "latencyOffsetNsec", SPA_TYPE_Long),
    PropertySpec(SPA_PROP_softMute, "softMute", SPA_TYPE_Bool),
    PropertySpec(SPA_PROP_softVolumes, "softVolumes", SPA_TYPE_Array, "array_float"),
    PropertySpec(SPA_PROP_iec958Codecs, "iec958Codecs", SPA_TYPE_Array, "array_id"),
    PropertySpec(SPA_PROP_volumeRampSamples, "volumeRampSamples", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_volumeRampStepSamples, "volumeRampStepSamples", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_volumeRampTime, "volumeRampTime", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_volumeRampStepTime, "volumeRampStepTime", SPA_TYPE_Int),
    PropertySpec(SPA_PROP_volumeRampScale, "volumeRampScale", SPA_TYPE_Id),
    PropertySpec(SPA_PROP_brightness, "brightness", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_contrast, "contrast", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_saturation, "saturation", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_hue, "hue", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_gamma, "gamma", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_exposure, "exposure", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_gain, "gain", SPA_TYPE_Float),
    PropertySpec(SPA_PROP_sharpness, "sharpness", SPA_TYPE_Float),
]

FORMAT_SPECS = [
    PropertySpec(SPA_FORMAT_mediaType, "mediaType", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_mediaSubtype, "mediaSubtype", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_AUDIO_format, "audio_format", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_AUDIO_flags, "audio_flags", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_AUDIO_rate, "audio_rate", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_AUDIO_channels, "audio_channels", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_AUDIO_position, "audio_position", SPA_TYPE_Array, "array_id"),
    PropertySpec(SPA_FORMAT_AUDIO_iec958Codec, "audio_iec958Codec", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_AUDIO_bitorder, "audio_bitorder", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_AUDIO_interleave, "audio_interleave", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_AUDIO_bitrate, "audio_bitrate", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_AUDIO_blockAlign, "audio_blockAlign", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_AUDIO_AAC_streamFormat, "audio_AAC_streamFormat", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_AUDIO_WMA_profile, "audio_WMA_profile", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_AUDIO_AMR_bandMode, "audio_AMR_bandMode", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_AUDIO_MP3_channelMode, "audio_MP3_channelMode", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_AUDIO_DTS_extType, "audio_DTS_extType", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_format, "video_format", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_modifier, "video_modifier", SPA_TYPE_Long),
    PropertySpec(SPA_FORMAT_VIDEO_size, "video_size", SPA_TYPE_Rectangle),
    PropertySpec(SPA_FORMAT_VIDEO_framerate, "video_framerate", SPA_TYPE_Fraction),
    PropertySpec(SPA_FORMAT_VIDEO_maxFramerate, "video_maxFramerate", SPA_TYPE_Fraction),
    PropertySpec(SPA_FORMAT_VIDEO_views, "video_views", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_VIDEO_interlaceMode, "video_interlaceMode", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_pixelAspectRatio, "video_pixelAspectRatio", SPA_TYPE_Fraction),
    PropertySpec(SPA_FORMAT_VIDEO_multiviewMode, "video_multiviewMode", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_multiviewFlags, "video_multiviewFlags", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_chromaSite, "video_chromaSite", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_colorRange, "video_colorRange", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_colorMatrix, "video_colorMatrix", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_transferFunction, "video_transferFunction", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_colorPrimaries, "video_colorPrimaries", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_profile, "video_profile", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_VIDEO_level, "video_level", SPA_TYPE_Int),
    PropertySpec(SPA_FORMAT_VIDEO_H264_streamFormat, "video_H264_streamFormat", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_H264_alignment, "video_H264_alignment", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_H265_streamFormat, "video_H265_streamFormat", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_H265_alignment, "video_H265_alignment", SPA_TYPE_Id),
    PropertySpec(SPA_FORMAT_VIDEO_deviceId, "video_deviceId", SPA_TYPE_Bytes),
    PropertySpec(SPA_FORMAT_CONTROL_types, "control_types", SPA_TYPE_Choice),
]

BUFFERS_SPECS = [
    PropertySpec(SPA_PARAM_BUFFERS_buffers, "buffers", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_BUFFERS_blocks, "blocks", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_BUFFERS_size, "size", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_BUFFERS_stride, "stride", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_BUFFERS_align, "align", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_BUFFERS_dataType, "dataType", SPA_TYPE_Choice),
    PropertySpec(SPA_PARAM_BUFFERS_metaType, "metaType", SPA_TYPE_Int),
]

META_SPECS = [
    PropertySpec(SPA_PARAM_META_type, "type", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_META_size, "size", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_META_features, "features", SPA_TYPE_Int),
]

IO_SPECS = [
    PropertySpec(SPA_PARAM_IO_id, "id", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_IO_size, "size", SPA_TYPE_Int),
]

PROFILE_SPECS = [
    PropertySpec(SPA_PARAM_PROFILE_index, "index", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_PROFILE_name, "name", SPA_TYPE_String),
    PropertySpec(SPA_PARAM_PROFILE_description, "description", SPA_TYPE_String),
    PropertySpec(SPA_PARAM_PROFILE_priority, "priority", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_PROFILE_available, "available", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_PROFILE_info, "info", SPA_TYPE_Struct, "dict_info"),
    PropertySpec(SPA_PARAM_PROFILE_classes, "classes", SPA_TYPE_Struct, "profile_classes"),
    PropertySpec(SPA_PARAM_PROFILE_save, "save", SPA_TYPE_Bool),
]

PORT_CONFIG_SPECS = [
    PropertySpec(SPA_PARAM_PORT_CONFIG_direction, "direction", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_PORT_CONFIG_mode, "mode", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_PORT_CONFIG_monitor, "monitor", SPA_TYPE_Bool),
    PropertySpec(SPA_PARAM_PORT_CONFIG_control, "control", SPA_TYPE_Bool),
    PropertySpec(SPA_PARAM_PORT_CONFIG_format, "format", SPA_TYPE_Object, "object_format"),
]

ROUTE_SPECS = [
    PropertySpec(SPA_PARAM_ROUTE_index, "index", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_ROUTE_direction, "direction", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_ROUTE_device, "device", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_ROUTE_name, "name", SPA_TYPE_String),
    PropertySpec(SPA_PARAM_ROUTE_description, "description", SPA_TYPE_String),
    PropertySpec(SPA_PARAM_ROUTE_priority, "priority", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_ROUTE_available, "available", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_ROUTE_info, "info", SPA_TYPE_Struct, "dict_info"),
    PropertySpec(SPA_PARAM_ROUTE_profiles, "profiles", SPA_TYPE_Array, "array_int"),
    PropertySpec(SPA_PARAM_ROUTE_props, "props", SPA_TYPE_Object, "object_props"),
    PropertySpec(SPA_PARAM_ROUTE_devices, "devices", SPA_TYPE_Array, "array_int"),
    PropertySpec(SPA_PARAM_ROUTE_profile, "profile", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_ROUTE_save, "save", SPA_TYPE_Bool),
]

LATENCY_SPECS = [
    PropertySpec(SPA_PARAM_LATENCY_direction, "direction", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_LATENCY_minQuantum, "minQuantum", SPA_TYPE_Float),
    PropertySpec(SPA_PARAM_LATENCY_maxQuantum, "maxQuantum", SPA_TYPE_Float),
    PropertySpec(SPA_PARAM_LATENCY_minRate, "minRate", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_LATENCY_maxRate, "maxRate", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_LATENCY_minNs, "minNs", SPA_TYPE_Long),
    PropertySpec(SPA_PARAM_LATENCY_maxNs, "maxNs", SPA_TYPE_Long),
]

PROCESS_LATENCY_SPECS = [
    PropertySpec(SPA_PARAM_PROCESS_LATENCY_quantum, "quantum", SPA_TYPE_Float),
    PropertySpec(SPA_PARAM_PROCESS_LATENCY_rate, "rate", SPA_TYPE_Int),
    PropertySpec(SPA_PARAM_PROCESS_LATENCY_ns, "ns", SPA_TYPE_Long),
]

TAG_SPECS = [
    PropertySpec(SPA_PARAM_TAG_direction, "direction", SPA_TYPE_Id),
    PropertySpec(SPA_PARAM_TAG_info, "info", SPA_TYPE_Struct, "dict_info"),
]

PARAM_DICT_SPECS = [
    PropertySpec(SPA_PARAM_DICT_info, "info", SPA_TYPE_Struct, "dict_info"),
]

OBJECT_ID_TO_NAME = {
    SPA_PARAM_PropInfo: "PropInfo",
    SPA_PARAM_Props: "Props",
    SPA_PARAM_EnumFormat: "Format",
    SPA_PARAM_Format: "Format",
    SPA_PARAM_Buffers: "Buffers",
    SPA_PARAM_Meta: "Meta",
    SPA_PARAM_IO: "IO",
    SPA_PARAM_EnumProfile: "Profile",
    SPA_PARAM_Profile: "Profile",
    SPA_PARAM_EnumPortConfig: "PortConfig",
    SPA_PARAM_PortConfig: "PortConfig",
    SPA_PARAM_EnumRoute: "Route",
    SPA_PARAM_Route: "Route",
    SPA_PARAM_Latency: "Latency",
    SPA_PARAM_ProcessLatency: "ProcessLatency",
    SPA_PARAM_Tag: "Tag",
    SPA_PARAM_Capability: "Capability",
    SPA_PARAM_PeerEnumFormat: "PeerEnumFormat",
    SPA_PARAM_PeerCapability: "PeerCapability",
}

OBJECT_ID_TO_TYPE = {
    SPA_PARAM_PropInfo: SPA_TYPE_OBJECT_PropInfo,
    SPA_PARAM_Props: SPA_TYPE_OBJECT_Props,
    SPA_PARAM_EnumFormat: SPA_TYPE_OBJECT_Format,
    SPA_PARAM_Format: SPA_TYPE_OBJECT_Format,
    SPA_PARAM_Buffers: SPA_TYPE_OBJECT_ParamBuffers,
    SPA_PARAM_Meta: SPA_TYPE_OBJECT_ParamMeta,
    SPA_PARAM_IO: SPA_TYPE_OBJECT_ParamIO,
    SPA_PARAM_EnumProfile: SPA_TYPE_OBJECT_ParamProfile,
    SPA_PARAM_Profile: SPA_TYPE_OBJECT_ParamProfile,
    SPA_PARAM_EnumPortConfig: SPA_TYPE_OBJECT_ParamPortConfig,
    SPA_PARAM_PortConfig: SPA_TYPE_OBJECT_ParamPortConfig,
    SPA_PARAM_EnumRoute: SPA_TYPE_OBJECT_ParamRoute,
    SPA_PARAM_Route: SPA_TYPE_OBJECT_ParamRoute,
    SPA_PARAM_Latency: SPA_TYPE_OBJECT_ParamLatency,
    SPA_PARAM_ProcessLatency: SPA_TYPE_OBJECT_ParamProcessLatency,
    SPA_PARAM_Tag: SPA_TYPE_OBJECT_ParamTag,
    SPA_PARAM_Capability: SPA_TYPE_OBJECT_ParamDict,
    SPA_PARAM_PeerEnumFormat: SPA_TYPE_OBJECT_PeerParam,
    SPA_PARAM_PeerCapability: SPA_TYPE_OBJECT_PeerParam,
}

OBJECT_PROPERTY_SPECS: Dict[int, Dict[int, PropertySpec]] = {}
OBJECT_PROPERTY_NAMES: Dict[int, Dict[str, PropertySpec]] = {}

for object_id, specs in (
    (SPA_PARAM_PropInfo, PROP_INFO_SPECS),
    (SPA_PARAM_Props, PROPS_SPECS),
    (SPA_PARAM_EnumFormat, FORMAT_SPECS),
    (SPA_PARAM_Format, FORMAT_SPECS),
    (SPA_PARAM_Buffers, BUFFERS_SPECS),
    (SPA_PARAM_Meta, META_SPECS),
    (SPA_PARAM_IO, IO_SPECS),
    (SPA_PARAM_EnumProfile, PROFILE_SPECS),
    (SPA_PARAM_Profile, PROFILE_SPECS),
    (SPA_PARAM_EnumPortConfig, PORT_CONFIG_SPECS),
    (SPA_PARAM_PortConfig, PORT_CONFIG_SPECS),
    (SPA_PARAM_EnumRoute, ROUTE_SPECS),
    (SPA_PARAM_Route, ROUTE_SPECS),
    (SPA_PARAM_Latency, LATENCY_SPECS),
    (SPA_PARAM_ProcessLatency, PROCESS_LATENCY_SPECS),
    (SPA_PARAM_Tag, TAG_SPECS),
    (SPA_PARAM_Capability, PARAM_DICT_SPECS),
):
    by_key, by_name = _make_property_table(specs)
    OBJECT_PROPERTY_SPECS[object_id] = by_key
    OBJECT_PROPERTY_NAMES[object_id] = by_name


def _create_object_class(
    class_name: str,
    object_type: int,
    object_id: int,
    specs: Sequence[PropertySpec],
) -> type[SpaPodObject]:
    property_names = ", ".join(spec.name for spec in specs)
    namespace = {
        "SPA_OBJECT_TYPE": object_type,
        "SPA_OBJECT_ID": object_id,
        "SPA_OBJECT_NAME": OBJECT_ID_TO_NAME.get(object_id),
        "__module__": "wyreplumber.spa_pod",
        "__doc__": (
            f"Typed SPA object for `{OBJECT_ID_TO_NAME.get(object_id, class_name)}`.\n\n"
            "Properties can be accessed by attribute, string key, or numeric "
            f"enum key. Known properties: {property_names}."
        ),
        "__annotations__": {spec.name: Any for spec in specs},
    }
    cls = type(class_name, (SpaPodObject,), namespace)
    cls._property_specs_by_key = OBJECT_PROPERTY_SPECS.get(object_id, {})
    cls._property_specs_by_name = OBJECT_PROPERTY_NAMES.get(object_id, {})
    for spec in specs:
        setattr(cls, spec.name, _object_property(spec))
    return cls


SpaPropInfo = _create_object_class("SpaPropInfo", SPA_TYPE_OBJECT_PropInfo, SPA_PARAM_PropInfo, PROP_INFO_SPECS)
SpaProps = _create_object_class("SpaProps", SPA_TYPE_OBJECT_Props, SPA_PARAM_Props, PROPS_SPECS)
SpaFormat = _create_object_class("SpaFormat", SPA_TYPE_OBJECT_Format, SPA_PARAM_Format, FORMAT_SPECS)
SpaParamBuffers = _create_object_class("SpaParamBuffers", SPA_TYPE_OBJECT_ParamBuffers, SPA_PARAM_Buffers, BUFFERS_SPECS)
SpaParamMeta = _create_object_class("SpaParamMeta", SPA_TYPE_OBJECT_ParamMeta, SPA_PARAM_Meta, META_SPECS)
SpaParamIO = _create_object_class("SpaParamIO", SPA_TYPE_OBJECT_ParamIO, SPA_PARAM_IO, IO_SPECS)
SpaParamProfile = _create_object_class("SpaParamProfile", SPA_TYPE_OBJECT_ParamProfile, SPA_PARAM_Profile, PROFILE_SPECS)
SpaParamPortConfig = _create_object_class("SpaParamPortConfig", SPA_TYPE_OBJECT_ParamPortConfig, SPA_PARAM_PortConfig, PORT_CONFIG_SPECS)
SpaParamRoute = _create_object_class("SpaParamRoute", SPA_TYPE_OBJECT_ParamRoute, SPA_PARAM_Route, ROUTE_SPECS)
SpaParamLatency = _create_object_class("SpaParamLatency", SPA_TYPE_OBJECT_ParamLatency, SPA_PARAM_Latency, LATENCY_SPECS)
SpaParamProcessLatency = _create_object_class(
    "SpaParamProcessLatency",
    SPA_TYPE_OBJECT_ParamProcessLatency,
    SPA_PARAM_ProcessLatency,
    PROCESS_LATENCY_SPECS,
)
SpaParamTag = _create_object_class("SpaParamTag", SPA_TYPE_OBJECT_ParamTag, SPA_PARAM_Tag, TAG_SPECS)
SpaParamDict = _create_object_class("SpaParamDict", SPA_TYPE_OBJECT_ParamDict, SPA_PARAM_Capability, PARAM_DICT_SPECS)

OBJECT_CLASSES_BY_ID: Dict[int, type[SpaPodObject]] = {
    SPA_PARAM_PropInfo: SpaPropInfo,
    SPA_PARAM_Props: SpaProps,
    SPA_PARAM_EnumFormat: SpaFormat,
    SPA_PARAM_Format: SpaFormat,
    SPA_PARAM_Buffers: SpaParamBuffers,
    SPA_PARAM_Meta: SpaParamMeta,
    SPA_PARAM_IO: SpaParamIO,
    SPA_PARAM_EnumProfile: SpaParamProfile,
    SPA_PARAM_Profile: SpaParamProfile,
    SPA_PARAM_EnumPortConfig: SpaParamPortConfig,
    SPA_PARAM_PortConfig: SpaParamPortConfig,
    SPA_PARAM_EnumRoute: SpaParamRoute,
    SPA_PARAM_Route: SpaParamRoute,
    SPA_PARAM_Latency: SpaParamLatency,
    SPA_PARAM_ProcessLatency: SpaParamProcessLatency,
    SPA_PARAM_Tag: SpaParamTag,
    SPA_PARAM_Capability: SpaParamDict,
}

__all__ = [
    name
    for name in globals()
    if name.startswith("SPA_") or name in {"PropertySpec", "SpaPodObject"} or name.startswith("Spa")
]
