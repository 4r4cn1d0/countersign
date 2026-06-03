"""Tests for archive storage behavior."""

import gzip
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import archive_service
from services.archive_service import _upload_to_s3


def test_upload_to_s3_writes_gzipped_json():
    client = MagicMock()
    payload = {"session": {"session_id": "s1"}, "events": []}

    with patch("boto3.client", return_value=client):
        _upload_to_s3("s1", payload)

    kwargs = client.put_object.call_args.kwargs
    assert kwargs["Key"] == "sessions/s1.json.gz"
    assert kwargs["ContentEncoding"] == "gzip"
    assert kwargs["ContentType"] == "application/json"
    assert json.loads(gzip.decompress(kwargs["Body"]).decode("utf-8")) == payload


@pytest.mark.asyncio
async def test_archive_worker_start_and_stop(monkeypatch):
    archive_service._archive_task = None
    archive_calls = AsyncMock(return_value=0)
    monkeypatch.setattr(archive_service.settings, "ARCHIVE_ENABLED", True)
    monkeypatch.setattr(archive_service, "archive_sessions_older_than", archive_calls)

    task = await archive_service.start_archive_worker(interval_seconds=999)
    assert task is not None

    await archive_service.stop_archive_worker()
    assert archive_service._archive_task is None
