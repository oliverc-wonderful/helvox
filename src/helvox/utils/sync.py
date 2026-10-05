"""Explicit authenticated Wonderful CLI sync; credentials never enter Helvox."""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from helvox.utils.takes import write_json

APP_ID = "a5b3e9f9-50a0-4731-b13a-5ab84a86916c"
FUNCTION_SLUG = "helvox-recording-review/recordings-ingest"
AMBIENT = (
    "WONDERFUL_API_KEY",
    "WONDERFUL_BASE_URL",
    "WONDERFUL_WORKSPACE_ID",
    "WONDERFUL_PROFILE",
    "WONDERFUL_ENV",
)


def sync_take(path, profile, *, cli="wful"):
    path = Path(path)
    if not profile or profile.startswith("-"):
        raise ValueError("An explicit Wonderful profile is required")
    record = json.loads((path / "take.json").read_text(encoding="utf-8"))
    payload = dict(record)
    for key, filename in (("audio_base64", "audio.wav"), ("raw_base64", "raw.wav")):
        content = (path / filename).read_bytes()
        if len(content) > 9_000_000:
            raise ValueError("A take exceeds the 9 MB per-file sync limit")
        if hashlib.sha256(content).hexdigest() != record["hashes"][filename]:
            raise ValueError("Local take hash changed; sync refused")
        payload[key] = base64.b64encode(content).decode("ascii")
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    receipt_path = path / "sync.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if (
            receipt.get("fingerprint") == fingerprint
            and receipt.get("profile") == profile
        ):
            return receipt
    env = {key: value for key, value in os.environ.items() if key not in AMBIENT}
    session = subprocess.run(
        [
            cli,
            "--profile",
            profile,
            "call",
            "post",
            f"/api/v2/apps/{APP_ID}/asset-session",
            "--data",
            "{}",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        check=False,
    )
    if session.returncode:
        raise RuntimeError(
            "Wonderful app access failed; the take remains queued locally."
        )
    session_data = json.loads(session.stdout)
    if isinstance(session_data, dict) and "data" in session_data:
        session_data = session_data["data"]
    token = session_data.get("token") if isinstance(session_data, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError(
            "Wonderful app access was not acknowledged; "
            "the take remains queued locally."
        )
    # Signed-in, expiring token; never persist it or print subprocess output.
    function_path = f"/app-functions/{token}/{FUNCTION_SLUG}"
    with tempfile.TemporaryDirectory(prefix="helvox-sync-") as temporary:
        request = Path(temporary) / "request.json"
        for variant, filename in (("audio", "audio.wav"), ("raw", "raw.wav")):
            encoded = payload.pop(variant + "_base64")
            if len(encoded) < 450000 and len(json.dumps(payload)) < 450000:
                payload[variant + "_base64"] = encoded
                continue
            content = base64.b64decode(encoded)
            count = (len(content) + 393215) // 393216
            for part in range(count):
                write_json(
                    request,
                    {
                        "action": "upload_part",
                        "recording_id": record["recording_id"],
                        "hash": record["hashes"][filename],
                        "part": part,
                        "base64": base64.b64encode(
                            content[part * 393216 : (part + 1) * 393216]
                        ).decode("ascii"),
                    },
                )
                request.chmod(0o600)
                uploaded = subprocess.run(
                    [
                        cli,
                        "--profile",
                        profile,
                        "call",
                        "post",
                        function_path,
                        "--data-file",
                        str(request),
                        "--json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env=env,
                    check=False,
                )
                if uploaded.returncode:
                    raise RuntimeError(
                        "Audio upload failed; the take remains queued locally."
                    )
                reply = json.loads(uploaded.stdout)
                if (
                    not isinstance(reply, dict)
                    or reply.get("status") != "uploaded"
                    or reply.get("part") != part
                    or reply.get("recording_id") != record["recording_id"]
                ):
                    raise RuntimeError(
                        "Audio part not acknowledged; the take remains queued locally."
                    )
            payload[variant + "_parts"] = count
        write_json(request, payload)
        request.chmod(0o600)
        completed = subprocess.run(
            [
                cli,
                "--profile",
                profile,
                "call",
                "post",
                function_path,
                "--data-file",
                str(request),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=90,
            env=env,
            check=False,
        )
    if completed.returncode:
        # Do not echo CLI stderr: it may contain URLs, tokens or request bodies.
        raise RuntimeError(
            "Wonderful sync failed. Check profile authentication/connectivity; the take"
            " remains queued locally."
        )
    response = json.loads(completed.stdout)
    if isinstance(response, dict) and "result" in response:
        response = response["result"]
    if (
        not isinstance(response, dict)
        or response.get("error")
        or response.get("recording_id") != record["recording_id"]
    ):
        raise RuntimeError(
            "Wonderful did not acknowledge this take; it remains queued locally."
        )
    receipt = {
        "profile": profile,
        "fingerprint": fingerprint,
        "recording_id": response["recording_id"],
        "status": "synced",
    }
    write_json(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(
        description="Retry durable Helvox takes to Wonderful"
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    failures = 0
    for path in sorted(args.folder.rglob("take.json")):
        try:
            sync_take(path.parent, args.profile)
            print(f"Synced {path.parent.name}")
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            failures += 1
            print(f"Pending {path.parent.name}; retry after checking Wonderful access")
    raise SystemExit(1 if failures else 0)
