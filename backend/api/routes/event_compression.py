"""Helpers for compressed event batch payloads."""

from __future__ import annotations

import base64
import gzip
import json
from typing import Any, Dict, List

from fastapi import HTTPException, status

from models.trace_event import EventBatchRequest


def expand_batch_events(request: EventBatchRequest) -> List[Dict[str, Any]]:
    """Return event dicts, decompressing compressed_payload when set."""
    if request.compressed_payload:
        if not request.compression:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="compression is required when compressed_payload is provided",
            )
        try:
            raw = base64.b64decode(request.compressed_payload)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="compressed_payload must be valid base64",
            ) from exc

        if request.compression == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="gzip decompression failed",
                ) from exc
        elif request.compression == "zstd":
            try:
                import zstandard as zstd
            except ImportError as exc:
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="zstd support requires zstandard package",
                ) from exc
            try:
                raw = zstd.ZstdDecompressor().decompress(raw)
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="zstd decompression failed",
                ) from exc
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unsupported compression type",
            )

        try:
            events = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="decompressed payload must be a JSON array of events",
            ) from exc

        if not isinstance(events, list):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="decompressed payload must be a JSON array",
            )
        return events

    return request.events
