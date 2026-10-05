import json
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from helvox.app import App
from helvox.utils.recorder import Recorder
from helvox.utils.takes import archive_take


@pytest.fixture
def app(tmp_path, monkeypatch):
    value = App.__new__(App)
    value.recorder = SimpleNamespace(
        recording=False,
        quality={"verdict": "GOOD", "reasons": []},
        save_audio=Mock(return_value=8),
        add_sample=Mock(),
        audio_data=[],
        full_audio=np.zeros(1),
        trimmed_audio=np.zeros(1),
    )
    value.current_id = "R01.05"
    value.de_text_var = SimpleNamespace(get=lambda: "Source")
    value.ch_text_edit_var = SimpleNamespace(get=lambda: "Transcript")
    value.listened_var = SimpleNamespace(get=lambda: True, set=Mock())
    value.current_take = archive_take(
        tmp_path,
        speaker_id="test",
        sample_id="R01.05",
        dialect="ZH",
        text_de="Source",
        text_ch="Transcript",
        audio=np.zeros(10),
        raw_audio=np.zeros(20),
        sample_rate=48000,
        quality={},
        microphone="Fixture",
    )
    value.recorder.speaker_dialect = "ZH"
    value.request_sync = Mock()
    value.clear_take = Mock()
    value.update_duration = Mock()
    value.load_next_sample = Mock()
    monkeypatch.setattr("helvox.app.messagebox.showwarning", Mock())
    return value


@pytest.mark.parametrize(
    "condition", ["bad", "not_listened", "changed_text", "still_recording"]
)
def test_save_gate_preserves_take_until_valid(app, condition):
    if condition == "bad":
        app.recorder.quality = {"verdict": "BAD", "reasons": ["Clipping"]}
    if condition == "not_listened":
        app.listened_var.get = lambda: False
    if condition == "changed_text":
        app.ch_text_edit_var.get = lambda: "Changed"
    if condition == "still_recording":
        app.recorder.recording = True
    app.save()
    app.recorder.save_audio.assert_not_called()
    app.load_next_sample.assert_not_called()
    assert (
        json.loads((app.current_take / "take.json").read_text())["human_review"]
        == "pending"
    )


def test_confirmed_take_saves_exact_recording_id_and_advances(app):
    expected = json.loads((app.current_take / "take.json").read_text())["recording_id"]
    app.save()
    assert app.recorder.add_sample.call_args.kwargs["recording_id"] == expected
    app.request_sync.assert_called_once()
    app.load_next_sample.assert_called_once()


def test_stop_capture_preserves_overflow_in_quality(monkeypatch, tmp_path):
    recorder = Recorder(tmp_path)
    recorder.recording = True
    recorder.stream = SimpleNamespace(stop=lambda: None, close=lambda: None)
    recorder.audio_data = [np.zeros((48000 * 8, 1), dtype=np.float32)]
    recorder.capture_errors = ["input overflow"]
    monkeypatch.setattr(recorder, "start_monitoring", lambda: None)
    recorder.stop_recording()
    assert recorder.quality["verdict"] == "BAD"
    assert recorder.quality["metrics"]["capture_errors"] == ["input overflow"]
    assert len(recorder.full_audio) == 48000 * 8
