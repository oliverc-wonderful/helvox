"""Authenticated push feedback. No periodic server reads or credential persistence."""

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from helvox.utils.sync import AMBIENT, APP_ID
from helvox.utils.takes import write_json


def get_cli_json(profile, args):
    env = {key: value for key, value in os.environ.items() if key not in AMBIENT}
    result = subprocess.run(
        ["wful", "--profile", profile, *args, "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Wonderful authentication or connectivity failed")
    value = json.loads(result.stdout)
    if isinstance(value, dict) and "data" in value:
        value = value["data"]
    return value


def get_socket_url(profile):
    profiles = get_cli_json(profile, ["profile", "list"])
    selected = next(item for item in profiles if item["name"] == profile)
    base = urlsplit(selected["base_url"])
    if base.scheme not in ("https", "http") or not base.netloc:
        raise ValueError("Invalid Wonderful profile URL")
    session = get_cli_json(
        profile,
        ["call", "post", f"/api/v2/apps/{APP_ID}/asset-session", "--data", "{}"],
    )
    token = session.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Wonderful did not acknowledge app access")
    return urlunsplit(
        (
            "wss" if base.scheme == "https" else "ws",
            base.netloc,
            f"/app-function-sockets/{token}/helvox-recording-review/recordings-live",
            "",
            "",
        )
    )


def save_review(folder, review):
    """A separate mutable review file never changes the frozen take/audio."""
    if review.get("status") not in ("pending", "approved", "re_record"):
        raise ValueError("Invalid review status")
    incoming = review.get("reviewed_ts")
    if not isinstance(incoming, (int, float)) or incoming < 0:
        raise ValueError("Invalid review timestamp")
    path = Path(folder) / "review.json"
    if path.exists() and json.loads(path.read_text()).get("reviewed_ts", 0) > incoming:
        return False
    write_json(path, review)
    return True


class LiveFeedback:
    def __init__(self, folder, profile):
        self.folder = Path(folder)
        self.profile = profile
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.refresh_event = threading.Event()
        self.socket = None
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.socket:
            self.socket.close()

    def refresh(self):
        self.refresh_event.set()

    def get_takes(self):
        takes = {}
        for path in self.folder.rglob("take.json"):
            try:
                record = json.loads(path.read_text())
                receipt = path.parent / "sync.json"
                if (
                    receipt.exists()
                    and json.loads(receipt.read_text()).get("profile") == self.profile
                ):
                    takes[record["recording_id"]] = path.parent
            except (ValueError, KeyError, OSError):
                continue
        return takes

    def request_reviews(self, socket):
        takes = self.get_takes()
        ids = list(takes)
        for offset in range(0, len(ids), 25):
            socket.send(
                json.dumps(
                    {
                        "action": "get_reviews",
                        "recording_ids": ids[offset : offset + 25],
                    }
                )
            )
        return takes

    def run(self):
        from websockets.sync.client import connect

        delay = 1
        while not self.stop_event.is_set():
            try:
                self.events.put(("status", "Connecting to Wonderful…"))
                with connect(
                    get_socket_url(self.profile),
                    open_timeout=15,
                    close_timeout=3,
                    max_size=65536,
                    proxy=None,
                ) as socket:
                    self.socket = socket
                    socket.send(json.dumps({"action": "hello"}))
                    takes = {}
                    while not self.stop_event.is_set():
                        if self.refresh_event.is_set():
                            self.refresh_event.clear()
                            takes = self.request_reviews(socket)
                        try:
                            message = json.loads(socket.recv(timeout=1))
                        except TimeoutError:
                            # Local shutdown check, no network request.
                            continue
                        if message.get("type") == "ready":
                            delay = 1
                            self.events.put(("status", "Live · Wonderful connected"))
                            self.events.put(("reconcile", None))
                            takes = self.request_reviews(socket)
                        elif message.get("type") == "recordings_changed":
                            takes = self.request_reviews(socket)
                        elif message.get("type") == "reviews":
                            for review in message.get("reviews", []):
                                folder = takes.get(review.get("recording_id"))
                                if folder and save_review(folder, review):
                                    self.events.put(("review", (folder, review)))
                        elif message.get("error"):
                            raise RuntimeError("Live request rejected")
            except Exception:
                if not self.stop_event.is_set():
                    self.events.put(
                        (
                            "status",
                            "Live disconnected · reconnecting; local takes are safe",
                        )
                    )
            finally:
                self.socket = None
            if self.stop_event.wait(delay):
                return
            delay = min(30, delay * 2)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Receive live Wonderful recording reviews"
    )
    parser.add_argument("folder", type=Path)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    if not args.folder.is_dir() or not args.profile or args.profile.startswith("-"):
        parser.error("An existing recordings folder and explicit profile are required")
    client = LiveFeedback(args.folder, args.profile)
    client.start()
    try:
        while True:
            kind, payload = client.events.get()
            if kind == "status":
                print(payload, flush=True)
            elif kind == "review":
                folder, review = payload
                print(
                    f"Review received: {folder.name} · {review['status']}", flush=True
                )
    except KeyboardInterrupt:
        client.stop()
