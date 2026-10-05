import json
from types import SimpleNamespace

import numpy as np
import pytest

from helvox.utils.sync import sync_take
from helvox.utils.takes import archive_take, write_json


@pytest.fixture
def take(tmp_path):
    return archive_take(
        tmp_path,
        speaker_id="test-speaker",
        sample_id="R01.05",
        dialect="ZH",
        text_de="Source",
        text_ch="Transcript",
        audio=np.zeros((4800, 1)),
        raw_audio=np.zeros((5000, 1)),
        sample_rate=48000,
        quality={
            "verdict": "BAD",
            "purpose": "reference",
            "metrics": {"duration_s": 0.1},
        },
        microphone="Synthetic fixture",
    )


def acknowledge(path):
    record = json.loads((path / "take.json").read_text())
    return SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"recording_id": record["recording_id"]}),
        stderr="",
    )


def test_duplicate_receipt_avoids_upload_and_ambient_credentials(monkeypatch, take):
    calls = []
    monkeypatch.setenv("WONDERFUL_API_KEY", "ambient-secret")

    def run(command, **kwargs):
        assert command[:3] == ["wful", "--profile", "swiss-german"]
        assert "WONDERFUL_API_KEY" not in kwargs["env"]
        if command[5].endswith("/asset-session"):
            return SimpleNamespace(
                returncode=0, stdout=' {"token":"test-token"}', stderr=""
            )
        assert "--data-file" in command
        calls.append(command)
        return acknowledge(take)

    monkeypatch.setattr("helvox.utils.sync.subprocess.run", run)
    assert sync_take(take, "swiss-german")["status"] == "synced"
    sync_take(take, "swiss-german")
    assert len(calls) == 1


def test_failed_upload_survives_restart_and_retry(monkeypatch, take):
    monkeypatch.setattr(
        "helvox.utils.sync.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="secret-error"),
    )
    with pytest.raises(RuntimeError, match="queued locally"):
        sync_take(take, "swiss-german")
    assert not (take / "sync.json").exists()
    monkeypatch.setattr(
        "helvox.utils.sync.subprocess.run",
        lambda command, **k: (
            SimpleNamespace(returncode=0, stdout='{"token":"test-token"}', stderr="")
            if command[5].endswith("/asset-session")
            else acknowledge(take)
        ),
    )
    assert sync_take(take, "swiss-german")["status"] == "synced"


def test_speaker_confirmation_resyncs_same_take(monkeypatch, take):
    calls = []
    monkeypatch.setattr(
        "helvox.utils.sync.subprocess.run",
        lambda command, **k: (
            SimpleNamespace(returncode=0, stdout='{"token":"test-token"}', stderr="")
            if command[5].endswith("/asset-session")
            else (calls.append(command) or acknowledge(take))
        ),
    )
    sync_take(take, "swiss-german")
    record = json.loads((take / "take.json").read_text())
    record["human_review"] = "accepted_by_speaker"
    write_json(take / "take.json", record)
    sync_take(take, "swiss-german")
    assert len(calls) == 2


def test_corrupted_audio_is_not_uploaded(take):
    (take / "audio.wav").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="hash changed"):
        sync_take(take, "swiss-german")


def test_unacknowledged_reply_is_not_a_receipt(monkeypatch, take):
    monkeypatch.setattr(
        "helvox.utils.sync.subprocess.run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout='{"error":"no_user_id"}', stderr=""
        ),
    )
    with pytest.raises(RuntimeError):
        sync_take(take, "swiss-german")
    assert not (take / "sync.json").exists()


def test_attempts_are_unique_and_raw_is_kept(take, tmp_path):
    record = json.loads((take / "take.json").read_text())
    assert (take / "raw.wav").exists()
    assert record["human_review"] == "pending"
    assert record["hashes"]["audio.wav"] != record["hashes"]["raw.wav"]
    with pytest.raises(ValueError):
        archive_take(
            tmp_path,
            speaker_id="../escape",
            sample_id="x",
            dialect="ZH",
            text_de="",
            text_ch="",
            audio=np.zeros(10),
            raw_audio=np.zeros(10),
            sample_rate=48000,
            quality={},
            microphone="",
        )


def test_large_take_uses_bounded_parts_and_receipt(monkeypatch, tmp_path):
    path = archive_take(
        tmp_path,
        speaker_id="test",
        sample_id="long",
        dialect="ZH",
        text_de="Test",
        text_ch="Test",
        audio=np.zeros(48000 * 8),
        raw_audio=np.zeros(48000 * 8),
        sample_rate=48000,
        quality={
            "verdict": "BAD",
            "purpose": "reference",
            "metrics": {"duration_s": 8},
        },
        microphone="Synthetic fixture",
    )
    parts = []

    def run(command, **kwargs):
        if command[5].endswith("/asset-session"):
            return SimpleNamespace(
                returncode=0, stdout='{"token":"private-test-token"}', stderr=""
            )
        request = command[command.index("--data-file") + 1]
        from pathlib import Path

        body = Path(request).read_bytes()
        assert len(body) < 1_048_576
        data = json.loads(body)
        if data.get("action") == "upload_part":
            parts.append(data)
            reply = {
                "status": "uploaded",
                "recording_id": data["recording_id"],
                "part": data["part"],
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(reply), stderr="")
        assert data["audio_parts"] == 3 and data["raw_parts"] == 3
        assert "audio_base64" not in data
        return acknowledge(path)

    monkeypatch.setattr("helvox.utils.sync.subprocess.run", run)
    sync_take(path, "swiss-german")
    assert len(parts) == 6
    assert "private-test-token" not in (path / "sync.json").read_text()
