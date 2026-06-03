"""Trace serialization and deserialization (task 9)."""

from __future__ import annotations

import gzip
import json
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from google.protobuf import json_format
from google.protobuf.struct_pb2 import Struct

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class SerializationFormat(str, Enum):
    JSON = "json"
    PROTOBUF = "protobuf"


class CompressionType(str, Enum):
    NONE = "none"
    GZIP = "gzip"
    ZSTD = "zstd"


class SerializedTrace(BaseModel):
    schema_version: str = SCHEMA_VERSION
    format: SerializationFormat = SerializationFormat.JSON
    compression: CompressionType = CompressionType.NONE
    session_id: str
    events: List[Dict[str, Any]] = Field(default_factory=list)


def serialize_trace(
    session_id: str,
    events: List[Dict[str, Any]],
    fmt: Union[SerializationFormat, str] = SerializationFormat.JSON,
    compression: Union[CompressionType, str] = CompressionType.GZIP,
) -> bytes:
    """Serialize a trace with optional compression."""
    fmt = SerializationFormat(fmt) if isinstance(fmt, str) else fmt
    compression = CompressionType(compression) if isinstance(compression, str) else compression

    payload = SerializedTrace(
        session_id=session_id,
        events=events,
        format=fmt,
        compression=CompressionType.NONE,
    )
    payload_dict = payload.model_dump(mode="json")
    if fmt == SerializationFormat.JSON:
        body = json.dumps(payload_dict, default=str).encode("utf-8")
    elif fmt == SerializationFormat.PROTOBUF:
        body = _dict_to_protobuf(payload_dict)
    else:
        raise ValueError(f"Unsupported serialization format: {fmt}")

    if compression == CompressionType.GZIP:
        return gzip.compress(body)
    if compression == CompressionType.ZSTD:
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise ValueError("zstd compression requires the zstandard package") from exc
        return zstd.ZstdCompressor().compress(body)
    return body


def deserialize_trace(
    data: bytes,
    compression: Optional[Union[CompressionType, str]] = None,
    fmt: Optional[Union[SerializationFormat, str]] = None,
) -> SerializedTrace:
    """Deserialize trace bytes into a SerializedTrace model."""
    if compression:
        compression = CompressionType(compression)
    else:
        compression = CompressionType.NONE

    if compression == CompressionType.GZIP or data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
        compression = CompressionType.GZIP
    elif compression == CompressionType.ZSTD:
        import zstandard as zstd
        data = zstd.ZstdDecompressor().decompress(data)

    expected_format = SerializationFormat(fmt) if fmt else None
    parsed = _decode_payload(data, expected_format)

    version = parsed.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema version: {version}")

    return SerializedTrace.model_validate(parsed)


def _dict_to_protobuf(payload: Dict[str, Any]) -> bytes:
    message = Struct()
    json_format.ParseDict(payload, message)
    return message.SerializeToString()


def _protobuf_to_dict(data: bytes) -> Dict[str, Any]:
    message = Struct()
    try:
        message.ParseFromString(data)
    except Exception as exc:
        raise ValueError("Invalid protobuf trace serialization payload") from exc
    return json_format.MessageToDict(
        message,
        preserving_proto_field_name=True,
    )


def _decode_payload(
    data: bytes,
    expected_format: Optional[SerializationFormat],
) -> Dict[str, Any]:
    if expected_format == SerializationFormat.PROTOBUF:
        return _protobuf_to_dict(data)

    if expected_format in (None, SerializationFormat.JSON):
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if expected_format == SerializationFormat.JSON:
                raise ValueError("Invalid JSON trace serialization payload")

    return _protobuf_to_dict(data)
