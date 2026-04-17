from collections.abc import ItemsView, Iterator, KeysView, MutableMapping, ValuesView
from typing import Any, Optional, TypedDict, TypeAlias

# SPA Type constants
SPA_TYPE_None: int
SPA_TYPE_Bool: int
SPA_TYPE_Id: int
SPA_TYPE_Int: int
SPA_TYPE_Long: int
SPA_TYPE_Float: int
SPA_TYPE_Double: int
SPA_TYPE_String: int
SPA_TYPE_Bytes: int
SPA_TYPE_Rectangle: int
SPA_TYPE_Fraction: int
SPA_TYPE_Bitmap: int
SPA_TYPE_Array: int
SPA_TYPE_Struct: int
SPA_TYPE_Object: int
SPA_TYPE_Sequence: int
SPA_TYPE_Pointer: int
SPA_TYPE_Fd: int
SPA_TYPE_Choice: int
SPA_TYPE_Pod: int

# SPA Choice constants
SPA_CHOICE_None: int
SPA_CHOICE_Range: int
SPA_CHOICE_Step: int
SPA_CHOICE_Enum: int
SPA_CHOICE_Flags: int


class RawSpaPodDict(TypedDict):
    type: int
    size: int
    data: bytes


class SpaRectangle(TypedDict):
    _pod_type: int
    width: int
    height: int


class SpaFraction(TypedDict):
    _pod_type: int
    num: int
    denom: int


class SpaBitmapPod(TypedDict):
    _pod_type: int
    data: bytes


class SpaArrayPod(TypedDict):
    _pod_type: int
    child_size: int
    child_type: int
    values: list[Any]


class SpaStructPod(TypedDict):
    _pod_type: int
    values: list[Any]


class SpaChoicePod(TypedDict, total=False):
    _pod_type: int
    choice_type: int
    flags: int
    child_size: int
    child_type: int
    values: list[Any]
    value: Any
    default: Any
    min: Any
    max: Any
    step: Any
    alternatives: list[Any]
    flags_values: list[Any]


class SpaSequenceControl(TypedDict):
    offset: int
    type: int
    value: Any


class SpaSequencePod(TypedDict):
    _pod_type: int
    unit: int
    controls: list[SpaSequenceControl]


class SpaPointerPod(TypedDict):
    _pod_type: int
    pointer_type: int
    value: int


class SpaEmbeddedPod(TypedDict):
    _pod_type: int
    pod: Any


class SpaGenericObjectPod(TypedDict, total=False):
    _pod_type: int
    _object_type: int
    _object_id: int
    object_type: int
    object_id: int
    object_name: str
    properties: dict[Any, Any]
    property_flags: dict[Any, int]
    property_keys: dict[str, int]


SpaLabel: TypeAlias = dict[str, Any]
SpaInfoDict: TypeAlias = dict[str, Any]
SpaParamsDict: TypeAlias = dict[str, Any]
SpaProfileClass: TypeAlias = dict[str, Any]


def __getattr__(name: str) -> Any: ...


class SpaPodObject(MutableMapping[Any, Any]):
    property_flags: dict[Any, int]
    property_keys: dict[str, int]
    object_type: int
    object_id: int
    object_name: Optional[str]

    def __init__(
        self,
        properties: Optional[dict[Any, Any]] = ...,
        *,
        property_flags: Optional[dict[Any, int]] = ...,
        property_keys: Optional[dict[str, int]] = ...,
        object_type: Optional[int] = ...,
        object_id: Optional[int] = ...,
        object_name: Optional[str] = ...,
        **kwargs: Any,
    ) -> None: ...

    def __getitem__(self, key: Any) -> Any: ...
    def __setitem__(self, key: Any, value: Any) -> None: ...
    def __delitem__(self, key: Any) -> None: ...
    def __iter__(self) -> Iterator[Any]: ...
    def __len__(self) -> int: ...
    def get(self, key: Any, default: Any = ...) -> Any: ...
    def keys(self) -> KeysView[Any]: ...
    def items(self) -> ItemsView[Any, Any]: ...
    def values(self) -> ValuesView[Any]: ...
    def as_pod_mapping(self) -> SpaGenericObjectPod: ...


class SpaPropInfo(SpaPodObject):
    id: int | None
    name: str | None
    type: Any
    labels: list[SpaLabel] | None
    container: int | None
    params: bool | None
    description: str | None


class SpaProps(SpaPodObject):
    unknown: Any | None
    device: str | None
    deviceName: str | None
    deviceFd: int | None
    card: str | None
    cardName: str | None
    minLatency: int | None
    maxLatency: int | None
    periods: int | None
    periodSize: int | None
    periodEvent: bool | None
    live: bool | None
    rate: int | None
    quality: int | None
    bluetoothAudioCodec: int | None
    bluetoothOffloadActive: bool | None
    params: SpaParamsDict | None
    clockId: int | None
    clockName: str | None
    clockQuantumLimit: int | None
    clockMinQuantum: int | None
    clockMaxQuantum: int | None
    clockRate: int | None
    clockAllowedRates: list[int] | None
    clockForceRates: list[int] | None
    waveType: int | None
    frequency: float | None
    volume: float | None
    mute: bool | None
    patternType: int | None
    ditherType: int | None
    truncate: bool | None
    channelVolumes: list[float] | None
    volumeBase: float | None
    volumeStep: float | None
    channelMap: list[int] | None
    monitorMute: bool | None
    monitorVolumes: list[float] | None
    latencyOffsetNsec: int | None
    softMute: bool | None
    softVolumes: list[float] | None
    iec958Codecs: list[int] | None
    volumeRampSamples: int | None
    volumeRampStepSamples: int | None
    volumeRampTime: int | None
    volumeRampStepTime: int | None
    volumeRampScale: int | None
    brightness: float | None
    contrast: float | None
    saturation: float | None
    hue: float | None
    gamma: float | None
    exposure: float | None
    gain: float | None
    sharpness: float | None


class SpaFormat(SpaPodObject):
    mediaType: int | None
    mediaSubtype: int | None
    audio_format: int | None
    audio_flags: int | None
    audio_rate: int | None
    audio_channels: int | None
    audio_position: list[int] | None
    audio_iec958Codec: int | None
    audio_bitorder: int | None
    audio_interleave: int | None
    audio_bitrate: int | None
    audio_blockAlign: int | None
    audio_AAC_streamFormat: int | None
    audio_WMA_profile: int | None
    audio_AMR_bandMode: int | None
    audio_MP3_channelMode: int | None
    audio_DTS_extType: int | None
    video_format: int | None
    video_modifier: int | None
    video_size: SpaRectangle | None
    video_framerate: SpaFraction | None
    video_maxFramerate: SpaFraction | None
    video_views: int | None
    video_interlaceMode: int | None
    video_pixelAspectRatio: SpaFraction | None
    video_multiviewMode: int | None
    video_multiviewFlags: int | None
    video_chromaSite: int | None
    video_colorRange: int | None
    video_colorMatrix: int | None
    video_transferFunction: int | None
    video_colorPrimaries: int | None
    video_profile: int | None
    video_level: int | None
    video_H264_streamFormat: int | None
    video_H264_alignment: int | None
    video_H265_streamFormat: int | None
    video_H265_alignment: int | None
    video_deviceId: bytes | None
    control_types: SpaChoicePod | None


class SpaParamBuffers(SpaPodObject):
    buffers: int | None
    blocks: int | None
    size: int | None
    stride: int | None
    align: int | None
    dataType: SpaChoicePod | None
    metaType: int | None


class SpaParamMeta(SpaPodObject):
    type: int | None
    size: int | None
    features: int | None


class SpaParamIO(SpaPodObject):
    id: int | None
    size: int | None


class SpaParamProfile(SpaPodObject):
    index: int | None
    name: str | None
    description: str | None
    priority: int | None
    available: int | None
    info: SpaInfoDict | None
    classes: list[SpaProfileClass] | None
    save: bool | None


class SpaParamPortConfig(SpaPodObject):
    direction: int | None
    mode: int | None
    monitor: bool | None
    control: bool | None
    format: SpaFormat | None


class SpaParamRoute(SpaPodObject):
    index: int | None
    direction: int | None
    device: int | None
    name: str | None
    description: str | None
    priority: int | None
    available: int | None
    info: SpaInfoDict | None
    profiles: list[int] | None
    props: SpaProps | None
    devices: list[int] | None
    profile: int | None
    save: bool | None


class SpaParamLatency(SpaPodObject):
    direction: int | None
    minQuantum: float | None
    maxQuantum: float | None
    minRate: int | None
    maxRate: int | None
    minNs: int | None
    maxNs: int | None


class SpaParamProcessLatency(SpaPodObject):
    quantum: float | None
    rate: int | None
    ns: int | None


class SpaParamTag(SpaPodObject):
    direction: int | None
    info: SpaInfoDict | None


class SpaParamDict(SpaPodObject):
    info: SpaInfoDict | None


SpaPodValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | bytes
    | SpaRectangle
    | SpaFraction
    | SpaBitmapPod
    | SpaArrayPod
    | SpaStructPod
    | SpaChoicePod
    | SpaSequencePod
    | SpaPointerPod
    | SpaEmbeddedPod
    | SpaGenericObjectPod
    | SpaPodObject
)


def parse_spa_pod(data: bytes, offset: int = 0) -> SpaPodValue: ...
def parse_spa_pod_dict(pod_dict: RawSpaPodDict | dict[str, Any]) -> SpaPodValue | dict[str, Any]: ...
def build_spa_pod(value: SpaPodValue | dict[str, Any], pod_type: Optional[int] = None) -> bytes: ...
def build_spa_pod_dict(value: SpaPodValue | dict[str, Any], pod_type: Optional[int] = None) -> RawSpaPodDict: ...
