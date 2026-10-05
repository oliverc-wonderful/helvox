"""Immutable local takes and atomic receipts keep retries safe and offline."""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import soundfile as sf


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def validate_component(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", str(value)):
        raise ValueError("Use letters, numbers, dots, underscores or dashes for IDs.")
    return str(value)


def archive_take(
    folder,
    *,
    speaker_id,
    sample_id,
    dialect,
    text_de,
    text_ch,
    audio,
    raw_audio,
    sample_rate,
    quality,
    microphone,
):
    validate_component(speaker_id)
    validate_component(sample_id)
    recording_id = str(uuid.uuid4())
    path = Path(folder) / speaker_id / "takes" / recording_id
    path.mkdir(parents=True, exist_ok=False)
    for name, samples in (("audio.wav", audio), ("raw.wav", raw_audio)):
        sf.write(path / name, samples, sample_rate, subtype="PCM_24")
    hashes = {
        name: hashlib.sha256((path / name).read_bytes()).hexdigest()
        for name in ("audio.wav", "raw.wav")
    }
    record = {
        "recording_id": recording_id,
        "sample_id": str(sample_id),
        "speaker_id": speaker_id,
        "dialect": dialect.lower(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "text_de": text_de,
        "text_ch": text_ch,
        "sample_rate": sample_rate,
        "microphone": microphone,
        "quality": quality,
        "hashes": hashes,
        "human_review": "pending",
        "review_note": "",
    }
    write_json(path / "take.json", record)
    return path
