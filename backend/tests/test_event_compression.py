"""Tests for compressed batch event expansion."""

import base64
import gzip
import json

import pytest
from fastapi import HTTPException

from api.routes.event_compression import expand_batch_events
from models.trace_event import EventBatchRequest


def test_expand_gzip_payload():
    events = [{"event_type": "annotation", "session_id": "00000000-0000-0000-0000-000000000001", "sequence_number": 1, "text": "hi"}]
    compressed = base64.b64encode(gzip.compress(json.dumps(events).encode())).decode()
    request = EventBatchRequest(
        events=[],
        compression="gzip",
        compressed_payload=compressed,
    )
    expanded = expand_batch_events(request)
    assert len(expanded) == 1


def test_compressed_payload_requires_compression():
    request = EventBatchRequest(events=[], compressed_payload="abc")
    with pytest.raises(HTTPException):
        expand_batch_events(request)
