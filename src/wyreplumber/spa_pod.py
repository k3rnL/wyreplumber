"""
SPA Pod parser/builder for PipeWire and WirePlumber.

The module exposes low-level SPA type constants together with Python helpers
that can parse raw SPA pods into Python values and build raw SPA pods back from
those values.
"""

from __future__ import annotations

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


def parse_spa_pod(data: bytes, offset: int = 0) -> Any:
    """
    Parse a SPA pod from bytes and return a Python representation.

    Scalar pods become Python scalars. Structured pods use dictionaries with a
    `_pod_type` marker so they can be round-tripped back into raw SPA data.
    """

    size, pod_type = _parse_pod_header(data, offset)
    value_offset = offset + 8
    _ensure_available(data, value_offset, size)

    if pod_type == SPA_TYPE_None:
        return None
    if pod_type == SPA_TYPE_Bool:
        return bool(struct.unpack_from("<i", data, value_offset)[0])
    if pod_type == SPA_TYPE_Id:
        return struct.unpack_from("<I", data, value_offset)[0]
    if pod_type == SPA_TYPE_Int:
        return struct.unpack_from("<i", data, value_offset)[0]
    if pod_type == SPA_TYPE_Long:
        return struct.unpack_from("<q", data, value_offset)[0]
    if pod_type == SPA_TYPE_Float:
        return struct.unpack_from("<f", data, value_offset)[0]
    if pod_type == SPA_TYPE_Double:
        return struct.unpack_from("<d", data, value_offset)[0]
    if pod_type == SPA_TYPE_String:
        string_data = data[value_offset:value_offset + size]
        if b"\x00" in string_data:
            string_data = string_data.split(b"\x00", 1)[0]
        return string_data.decode("utf-8", errors="replace")
    if pod_type == SPA_TYPE_Bytes:
        return data[value_offset:value_offset + size]
    if pod_type == SPA_TYPE_Rectangle:
        width, height = struct.unpack_from("<II", data, value_offset)
        return {"_pod_type": SPA_TYPE_Rectangle, "width": width, "height": height}
    if pod_type == SPA_TYPE_Fraction:
        num, denom = struct.unpack_from("<II", data, value_offset)
        return {"_pod_type": SPA_TYPE_Fraction, "num": num, "denom": denom}
    if pod_type == SPA_TYPE_Bitmap:
        return {"_pod_type": SPA_TYPE_Bitmap, "data": data[value_offset:value_offset + size]}
    if pod_type == SPA_TYPE_Array:
        return _parse_array(data, value_offset, size)
    if pod_type == SPA_TYPE_Struct:
        return _parse_struct(data, value_offset, size)
    if pod_type == SPA_TYPE_Object:
        return _parse_object(data, value_offset, size)
    if pod_type == SPA_TYPE_Sequence:
        return _parse_sequence(data, value_offset, size)
    if pod_type == SPA_TYPE_Pointer:
        return _parse_pointer(data, value_offset, size)
    if pod_type == SPA_TYPE_Fd:
        return struct.unpack_from("<q", data, value_offset)[0]
    if pod_type == SPA_TYPE_Choice:
        return _parse_choice(data, value_offset, size)
    if pod_type == SPA_TYPE_Pod:
        return _parse_embedded_pod(data, value_offset, size)

    return {
        "_pod_type": pod_type,
        "_type": pod_type,
        "_size": size,
        "_data": data[value_offset:value_offset + size],
    }


def _parse_array(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {"_pod_type": SPA_TYPE_Array, "child_size": 0, "child_type": SPA_TYPE_None, "values": []}

    child_size, child_type = struct.unpack_from("<II", data, offset)
    values: List[Any] = []
    current = offset + 8
    end = offset + size

    if child_size == 0:
        return {"_pod_type": SPA_TYPE_Array, "child_size": 0, "child_type": child_type, "values": []}

    while current + child_size <= end:
        pod_data = struct.pack("<II", child_size, child_type) + data[current:current + child_size]
        values.append(parse_spa_pod(pod_data, 0))
        current += child_size

    return {
        "_pod_type": SPA_TYPE_Array,
        "child_size": child_size,
        "child_type": child_type,
        "values": values,
    }


def _parse_struct(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    values: List[Any] = []
    current = offset
    end = offset + size

    while current + 8 <= end:
        pod_size, _ = _parse_pod_header(data, current)
        total_size = _align(8 + pod_size)
        if current + total_size > end:
            break
        values.append(parse_spa_pod(data, current))
        current += total_size

    return {"_pod_type": SPA_TYPE_Struct, "values": values}


def _parse_object(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {
            "_pod_type": SPA_TYPE_Object,
            "_object_type": 0,
            "_object_id": 0,
            "object_type": 0,
            "object_id": 0,
            "properties": {},
            "property_flags": {},
            "property_keys": {},
        }

    object_type, object_id = struct.unpack_from("<II", data, offset)
    properties: Dict[Any, Any] = {}
    property_flags: Dict[Any, int] = {}
    property_keys: Dict[str, int] = {}
    current = offset + 8
    end = offset + size

    while current + 16 <= end:
        prop_key, flags = struct.unpack_from("<II", data, current)
        current += 8
        pod_size, _ = _parse_pod_header(data, current)
        total_pod_size = _align(8 + pod_size)
        if current + total_pod_size > end:
            break

        parsed_value = parse_spa_pod(data, current)
        key_name = _resolve_property_name(object_id, prop_key)
        if isinstance(key_name, str):
            parsed_value = _specialize_property_value(object_id, prop_key, parsed_value)
            target_key: Any = key_name
            property_keys[key_name] = prop_key
        else:
            target_key = prop_key

        properties[target_key] = parsed_value
        property_flags[target_key] = flags
        current += total_pod_size

    result = {
        "_pod_type": SPA_TYPE_Object,
        "_object_type": object_type,
        "_object_id": object_id,
        "object_type": object_type,
        "object_id": object_id,
        "properties": properties,
        "property_flags": property_flags,
        "property_keys": property_keys,
    }
    object_name = _object_param_name(object_id)
    if object_name is not None:
        result["object_name"] = object_name
    return result


def _parse_choice(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 16:
        return {
            "_pod_type": SPA_TYPE_Choice,
            "choice_type": SPA_CHOICE_None,
            "flags": 0,
            "child_size": 0,
            "child_type": SPA_TYPE_None,
            "values": [],
        }

    choice_type, flags, child_size, child_type = struct.unpack_from("<IIII", data, offset)
    values: List[Any] = []
    current = offset + 16
    end = offset + size

    if child_size > 0:
        while current + child_size <= end:
            pod_data = struct.pack("<II", child_size, child_type) + data[current:current + child_size]
            values.append(parse_spa_pod(pod_data, 0))
            current += child_size

    result = {
        "_pod_type": SPA_TYPE_Choice,
        "choice_type": choice_type,
        "flags": flags,
        "child_size": child_size,
        "child_type": child_type,
        "values": values,
    }

    if choice_type == SPA_CHOICE_Range and len(values) >= 3:
        result["default"] = values[0]
        result["min"] = values[1]
        result["max"] = values[2]
    elif choice_type == SPA_CHOICE_Step and len(values) >= 4:
        result["default"] = values[0]
        result["min"] = values[1]
        result["max"] = values[2]
        result["step"] = values[3]
    elif choice_type == SPA_CHOICE_Enum and values:
        result["default"] = values[0]
        result["alternatives"] = values[1:]
    elif choice_type == SPA_CHOICE_Flags and values:
        result["default"] = values[0]
        result["flags_values"] = values[1:]
    elif choice_type == SPA_CHOICE_None and values:
        result["value"] = values[0]

    return result


def _parse_sequence(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {"_pod_type": SPA_TYPE_Sequence, "unit": 0, "controls": []}

    unit = struct.unpack_from("<I", data, offset)[0]
    current = offset + 8
    end = offset + size
    controls = []

    while current + 16 <= end:
        control_offset, control_type = struct.unpack_from("<II", data, current)
        current += 8
        pod_size, _ = _parse_pod_header(data, current)
        total_size = _align(8 + pod_size)
        if current + total_size > end:
            break
        controls.append(
            {
                "offset": control_offset,
                "type": control_type,
                "value": parse_spa_pod(data, current),
            }
        )
        current += total_size

    return {"_pod_type": SPA_TYPE_Sequence, "unit": unit, "controls": controls}


def _parse_pointer(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {"_pod_type": SPA_TYPE_Pointer, "pointer_type": 0, "value": 0}

    pointer_type = struct.unpack_from("<I", data, offset)[0]
    if size >= 16:
        pointer_value = struct.unpack_from("<Q", data, offset + 8)[0]
    elif size >= 12:
        pointer_value = struct.unpack_from("<I", data, offset + 8)[0]
    else:
        pointer_value = 0

    return {"_pod_type": SPA_TYPE_Pointer, "pointer_type": pointer_type, "value": pointer_value}


def _parse_embedded_pod(data: bytes, offset: int, size: int) -> Dict[str, Any]:
    if size < 8:
        return {"_pod_type": SPA_TYPE_Pod, "pod": None}

    pod_size, _ = _parse_pod_header(data, offset)
    total_size = _align(8 + pod_size)
    if total_size > size:
        raise ValueError("Embedded SPA pod exceeds container size")

    return {
        "_pod_type": SPA_TYPE_Pod,
        "pod": parse_spa_pod(data, offset),
    }


def _resolve_property_name(object_id: int, prop_key: int) -> Any:
    spec = _property_spec_by_key(object_id, prop_key)
    if spec is not None:
        return spec.name
    if object_id in (SPA_PARAM_PeerEnumFormat, SPA_PARAM_PeerCapability):
        return prop_key
    return prop_key


def _specialize_property_value(object_id: int, prop_key: int, value: Any) -> Any:
    spec = _property_spec_by_key(object_id, prop_key)
    if spec is None or spec.shape is None:
        return value

    if spec.shape == "dict_info":
        return _struct_to_dict_info(value)
    if spec.shape == "params":
        return _struct_to_params(value)
    if spec.shape == "labels":
        return _struct_to_labels(value)
    if spec.shape == "profile_classes":
        return _struct_to_profile_classes(value)
    if spec.shape == "array_int":
        return _array_to_values(value, int)
    if spec.shape == "array_float":
        return _array_to_values(value, float)
    if spec.shape == "array_id":
        return _array_to_values(value, int)
    return value


def _prepare_property_value(object_id: int, prop_key: int, value: Any) -> Any:
    spec = _property_spec_by_key(object_id, prop_key)
    if spec is None or spec.shape is None:
        return value

    if spec.shape == "dict_info":
        return _dict_info_to_struct(value)
    if spec.shape == "params":
        return _params_to_struct(value)
    if spec.shape == "labels":
        return _labels_to_struct(value)
    if spec.shape == "profile_classes":
        return _profile_classes_to_struct(value)
    if spec.shape == "array_int":
        return {"_pod_type": SPA_TYPE_Array, "child_type": SPA_TYPE_Int, "values": list(value)}
    if spec.shape == "array_float":
        return {"_pod_type": SPA_TYPE_Array, "child_type": SPA_TYPE_Float, "values": list(value)}
    if spec.shape == "array_id":
        return {"_pod_type": SPA_TYPE_Array, "child_type": SPA_TYPE_Id, "values": list(value)}
    if spec.shape == "object_props":
        return _ensure_object_value(value, SPA_TYPE_OBJECT_Props, SPA_PARAM_Props)
    if spec.shape == "object_format":
        return _ensure_object_value(value, SPA_TYPE_OBJECT_Format, SPA_PARAM_Format)
    return value


def _array_to_values(value: Any, convert: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Array:
        return value
    return [convert(item) for item in value.get("values", [])]


def _struct_to_dict_info(value: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Struct:
        return value
    items = list(value.get("values", []))
    if not items or not isinstance(items[0], int):
        return value
    count = items[0]
    values = items[1:]
    if len(values) != count * 2 or any(not isinstance(item, str) for item in values):
        return value
    return {values[index]: values[index + 1] for index in range(0, len(values), 2)}


def _dict_info_to_struct(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("_pod_type") == SPA_TYPE_Struct:
        return value
    if not isinstance(value, Mapping):
        return value
    items: List[Any] = [len(value)]
    for key, item_value in value.items():
        items.extend([str(key), str(item_value)])
    return {"_pod_type": SPA_TYPE_Struct, "values": items}


def _struct_to_params(value: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Struct:
        return value
    items = list(value.get("values", []))
    if len(items) % 2 != 0:
        return value
    params: Dict[str, Any] = {}
    for index in range(0, len(items), 2):
        key = items[index]
        if not isinstance(key, str):
            return value
        params[key] = items[index + 1]
    return params


def _params_to_struct(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("_pod_type") == SPA_TYPE_Struct:
        return value
    if not isinstance(value, Mapping):
        return value
    items: List[Any] = []
    for key, item_value in value.items():
        items.extend([str(key), item_value])
    return {"_pod_type": SPA_TYPE_Struct, "values": items}


def _struct_to_labels(value: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Struct:
        return value
    items = list(value.get("values", []))
    if len(items) % 2 != 0:
        return value
    labels = []
    for index in range(0, len(items), 2):
        if not isinstance(items[index + 1], str):
            return value
        labels.append({"value": items[index], "label": items[index + 1]})
    return labels


def _labels_to_struct(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("_pod_type") == SPA_TYPE_Struct:
        return value
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return value
    items: List[Any] = []
    for entry in value:
        if isinstance(entry, Mapping):
            items.extend([entry.get("value"), entry.get("label")])
        elif isinstance(entry, Sequence) and len(entry) == 2:
            items.extend([entry[0], entry[1]])
        else:
            return value
    return {"_pod_type": SPA_TYPE_Struct, "values": items}


def _struct_to_profile_classes(value: Any) -> Any:
    if not isinstance(value, Mapping) or value.get("_pod_type") != SPA_TYPE_Struct:
        return value

    items = list(value.get("values", []))
    if not items or not isinstance(items[0], int):
        return value

    count = items[0]
    classes = []
    nested = items[1:]
    if len(nested) != count:
        return value

    for item in nested:
        if not isinstance(item, Mapping) or item.get("_pod_type") != SPA_TYPE_Struct:
            return value
        entry = list(item.get("values", []))
        if len(entry) != 4 or not isinstance(entry[0], str) or not isinstance(entry[1], int) or not isinstance(entry[2], str):
            return value
        device_indexes = _array_to_values(entry[3], int)
        if not isinstance(device_indexes, list):
            return value
        classes.append(
            {
                "class": entry[0],
                "count": entry[1],
                "property": entry[2],
                "devices": device_indexes,
            }
        )
    return classes


def _profile_classes_to_struct(value: Any) -> Any:
    if isinstance(value, Mapping) and value.get("_pod_type") == SPA_TYPE_Struct:
        return value
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return value
    items: List[Any] = [len(value)]
    for entry in value:
        if not isinstance(entry, Mapping):
            return value
        items.append(
            {
                "_pod_type": SPA_TYPE_Struct,
                "values": [
                    str(entry.get("class")),
                    int(entry.get("count", 0)),
                    str(entry.get("property")),
                    {
                        "_pod_type": SPA_TYPE_Array,
                        "child_type": SPA_TYPE_Int,
                        "values": list(entry.get("devices", [])),
                    },
                ],
            }
        )
    return {"_pod_type": SPA_TYPE_Struct, "values": items}


def _ensure_object_value(value: Any, object_type: int, object_id: int) -> Any:
    if isinstance(value, Mapping) and (
        "object_type" in value
        or "_object_type" in value
        or "object_id" in value
        or "_object_id" in value
    ):
        return value
    if isinstance(value, Mapping):
        return {
            "_pod_type": SPA_TYPE_Object,
            "_object_type": object_type,
            "_object_id": object_id,
            "object_type": object_type,
            "object_id": object_id,
            "properties": dict(value),
            "property_flags": {},
            "property_keys": {},
        }
    return value


def parse_spa_pod_dict(pod_dict: Dict[str, Any]) -> Any:
    """Parse a SPA pod stored in a `{'type', 'size', 'data'}` dictionary."""
    if not isinstance(pod_dict, dict):
        return pod_dict
    data = pod_dict.get("data")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        return pod_dict
    try:
        return parse_spa_pod(bytes(data), 0)
    except Exception:
        return pod_dict


def build_spa_pod(value: Any, pod_type: Optional[int] = None) -> bytes:
    """Build a raw SPA pod from a Python value."""

    explicit_type = _explicit_pod_type(value)
    if pod_type is None and explicit_type is not None:
        pod_type = explicit_type
    if pod_type is None:
        pod_type = _infer_spa_type(value)

    if pod_type == SPA_TYPE_None:
        return _pack_pod(SPA_TYPE_None, b"")
    if pod_type == SPA_TYPE_Bool:
        return _pack_pod(SPA_TYPE_Bool, struct.pack("<i", 1 if value else 0))
    if pod_type == SPA_TYPE_Id:
        return _pack_pod(SPA_TYPE_Id, struct.pack("<I", int(value)))
    if pod_type == SPA_TYPE_Int:
        return _pack_pod(SPA_TYPE_Int, struct.pack("<i", int(value)))
    if pod_type == SPA_TYPE_Long:
        return _pack_pod(SPA_TYPE_Long, struct.pack("<q", int(value)))
    if pod_type == SPA_TYPE_Float:
        return _pack_pod(SPA_TYPE_Float, struct.pack("<f", float(value)))
    if pod_type == SPA_TYPE_Double:
        return _pack_pod(SPA_TYPE_Double, struct.pack("<d", float(value)))
    if pod_type == SPA_TYPE_String:
        return _pack_pod(SPA_TYPE_String, str(value).encode("utf-8") + b"\x00")
    if pod_type == SPA_TYPE_Bytes:
        return _pack_pod(SPA_TYPE_Bytes, bytes(value))
    if pod_type == SPA_TYPE_Rectangle:
        width, height = _rectangle_parts(value)
        return _pack_pod(SPA_TYPE_Rectangle, struct.pack("<II", width, height))
    if pod_type == SPA_TYPE_Fraction:
        num, denom = _fraction_parts(value)
        return _pack_pod(SPA_TYPE_Fraction, struct.pack("<II", num, denom))
    if pod_type == SPA_TYPE_Bitmap:
        body = value.get("data") if isinstance(value, Mapping) else value
        return _pack_pod(SPA_TYPE_Bitmap, bytes(body))
    if pod_type == SPA_TYPE_Array:
        return _build_array_pod(value)
    if pod_type == SPA_TYPE_Struct:
        return _build_struct_pod(value)
    if pod_type == SPA_TYPE_Object:
        return _build_object_pod(value)
    if pod_type == SPA_TYPE_Sequence:
        return _build_sequence_pod(value)
    if pod_type == SPA_TYPE_Pointer:
        return _build_pointer_pod(value)
    if pod_type == SPA_TYPE_Fd:
        return _pack_pod(SPA_TYPE_Fd, struct.pack("<q", int(value)))
    if pod_type == SPA_TYPE_Choice:
        return _build_choice_pod(value)
    if pod_type == SPA_TYPE_Pod:
        return _build_embedded_pod(value)

    raise ValueError(f"Unsupported SPA type for building: {pod_type}")


def _rectangle_parts(value: Any) -> Tuple[int, int]:
    if isinstance(value, Mapping):
        return int(value["width"]), int(value["height"])
    if isinstance(value, Sequence) and len(value) == 2:
        return int(value[0]), int(value[1])
    raise ValueError("Rectangle pod expects {'width', 'height'} or a 2-item sequence")


def _fraction_parts(value: Any) -> Tuple[int, int]:
    if isinstance(value, Mapping):
        return int(value["num"]), int(value["denom"])
    if isinstance(value, Sequence) and len(value) == 2:
        return int(value[0]), int(value[1])
    raise ValueError("Fraction pod expects {'num', 'denom'} or a 2-item sequence")


def _build_array_pod(value: Any) -> bytes:
    if isinstance(value, Mapping):
        values = list(value.get("values", []))
        child_type = value.get("child_type")
        child_size = value.get("child_size")
    else:
        values = list(value)
        child_type = None
        child_size = None

    if child_type is None and values:
        child_type = _infer_spa_type(values[0])
    if child_type is None:
        raise ValueError("Array pods require 'child_type' when empty")

    bodies = []
    for item in values:
        pod_bytes = build_spa_pod(item, child_type)
        item_size, item_type = _parse_pod_header(pod_bytes, 0)
        if item_type != child_type:
            raise ValueError("Array items must all use the same child type")
        if child_size is None:
            child_size = item_size
        elif child_size != item_size:
            raise ValueError("Array items must all use the same child size")
        bodies.append(pod_bytes[8:8 + item_size])

    if child_size is None:
        child_size = 0

    body = struct.pack("<II", int(child_size), int(child_type)) + b"".join(bodies)
    return _pack_pod(SPA_TYPE_Array, body)


def _build_struct_pod(value: Any) -> bytes:
    if isinstance(value, Mapping):
        values = list(value.get("values", []))
    else:
        values = list(value)
    body = b"".join(build_spa_pod(item) for item in values)
    return _pack_pod(SPA_TYPE_Struct, body)


def _build_choice_pod(value: Any) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("Choice pods require a mapping with choice metadata")

    values = list(value.get("values", []))
    if not values and "value" in value:
        values = [value["value"]]

    choice_type = int(value.get("choice_type", SPA_CHOICE_None))
    flags = int(value.get("flags", 0))
    child_type = value.get("child_type")
    child_size = value.get("child_size")

    if child_type is None and values:
        child_type = _infer_spa_type(values[0])
    if child_type is None:
        raise ValueError("Choice pods require 'child_type' when empty")

    bodies = []
    for item in values:
        pod_bytes = build_spa_pod(item, child_type)
        item_size, item_type = _parse_pod_header(pod_bytes, 0)
        if item_type != child_type:
            raise ValueError("Choice values must all use the same child type")
        if child_size is None:
            child_size = item_size
        elif child_size != item_size:
            raise ValueError("Choice values must all use the same child size")
        bodies.append(pod_bytes[8:8 + item_size])

    if child_size is None:
        child_size = 0

    body = struct.pack("<IIII", choice_type, flags, int(child_size), int(child_type)) + b"".join(bodies)
    return _pack_pod(SPA_TYPE_Choice, body)


def _build_object_pod(value: Any) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("Object pods require a mapping")

    object_type = value.get("object_type", value.get("_object_type"))
    object_id = value.get("object_id", value.get("_object_id"))
    if object_id is None:
        raise ValueError("Object pod requires 'object_id'")
    if object_type is None:
        object_type = _object_type_for_id(int(object_id))
    if object_type is None:
        raise ValueError("Object pod requires 'object_type'")

    properties = value.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ValueError("Object pod 'properties' must be a mapping")

    property_flags = value.get("property_flags", {})
    property_keys = value.get("property_keys", {})
    if not isinstance(property_flags, Mapping):
        property_flags = {}
    if not isinstance(property_keys, Mapping):
        property_keys = {}

    chunks = [struct.pack("<II", int(object_type), int(object_id))]

    for key, raw_value in properties.items():
        if isinstance(key, int):
            prop_key = key
            spec = _property_spec_by_key(int(object_id), prop_key)
            flag_key: Any = key
        else:
            spec = _property_spec_by_name(int(object_id), str(key))
            prop_key = property_keys.get(key)
            if prop_key is None and spec is not None:
                prop_key = spec.key
            if prop_key is None:
                raise ValueError(f"Unknown SPA object property '{key}' for object id {object_id}")
            flag_key = key

        prepared_value = _prepare_property_value(int(object_id), int(prop_key), raw_value)
        nested_type = _explicit_pod_type(prepared_value)
        if nested_type is None and spec is not None:
            nested_type = spec.pod_type

        property_pod = build_spa_pod(prepared_value, nested_type)
        chunks.append(struct.pack("<II", int(prop_key), int(property_flags.get(flag_key, 0))))
        chunks.append(property_pod)

    return _pack_pod(SPA_TYPE_Object, b"".join(chunks))


def _build_sequence_pod(value: Any) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("Sequence pods require a mapping")
    unit = int(value.get("unit", 0))
    controls = value.get("controls", [])
    if not isinstance(controls, Sequence):
        raise ValueError("Sequence pods require a 'controls' sequence")

    chunks = [struct.pack("<II", unit, 0)]
    for control in controls:
        if not isinstance(control, Mapping):
            raise ValueError("Sequence control entries must be mappings")
        control_value = control.get("value")
        control_pod = build_spa_pod(control_value)
        chunks.append(struct.pack("<II", int(control.get("offset", 0)), int(control.get("type", 0))))
        chunks.append(control_pod)
    return _pack_pod(SPA_TYPE_Sequence, b"".join(chunks))


def _build_pointer_pod(value: Any) -> bytes:
    if not isinstance(value, Mapping):
        raise ValueError("Pointer pods require a mapping")
    pointer_type = int(value.get("pointer_type", 0))
    pointer_value = int(value.get("value", 0))
    return _pack_pod(SPA_TYPE_Pointer, struct.pack("<IIQ", pointer_type, 0, pointer_value))


def _build_embedded_pod(value: Any) -> bytes:
    embedded = value.get("pod") if isinstance(value, Mapping) else value
    if isinstance(embedded, (bytes, bytearray, memoryview)):
        embedded_pod = bytes(embedded)
    else:
        embedded_pod = build_spa_pod(embedded)
    pod_size, _ = _parse_pod_header(embedded_pod, 0)
    total_size = _align(8 + pod_size)
    return _pack_pod(SPA_TYPE_Pod, embedded_pod[:total_size])


def _infer_spa_type(value: Any) -> int:
    explicit_type = _explicit_pod_type(value)
    if explicit_type is not None:
        return explicit_type
    if value is None:
        return SPA_TYPE_None
    if isinstance(value, bool):
        return SPA_TYPE_Bool
    if isinstance(value, int):
        if -2147483648 <= value <= 2147483647:
            return SPA_TYPE_Int
        return SPA_TYPE_Long
    if isinstance(value, float):
        return SPA_TYPE_Float
    if isinstance(value, str):
        return SPA_TYPE_String
    if isinstance(value, (bytes, bytearray, memoryview)):
        return SPA_TYPE_Bytes
    if isinstance(value, Mapping):
        if "width" in value and "height" in value:
            return SPA_TYPE_Rectangle
        if "num" in value and "denom" in value:
            return SPA_TYPE_Fraction
        if "choice_type" in value:
            return SPA_TYPE_Choice
        if "controls" in value:
            return SPA_TYPE_Sequence
        if "pointer_type" in value:
            return SPA_TYPE_Pointer
        if "object_type" in value or "_object_type" in value or "object_id" in value or "_object_id" in value or "properties" in value:
            return SPA_TYPE_Object
        if "pod" in value:
            return SPA_TYPE_Pod
        if "values" in value and "child_type" in value:
            return SPA_TYPE_Array
        if "values" in value:
            return SPA_TYPE_Struct
    if isinstance(value, Sequence):
        return SPA_TYPE_Struct
    raise ValueError(f"Cannot infer SPA type for value: {type(value)!r}")


def build_spa_pod_dict(value: Any, pod_type: Optional[int] = None) -> Dict[str, Any]:
    """Build a `{'type', 'size', 'data'}` dictionary from a Python value."""
    data = build_spa_pod(value, pod_type)
    size, spa_type = _parse_pod_header(data, 0)
    return {"type": spa_type, "size": size, "data": data}
