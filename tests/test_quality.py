import numpy as np
import pytest

from helvox.utils.quality import judge_recording


@pytest.fixture
def speech(monkeypatch):
    class Vad:
        def __init__(self, *args):
            pass

        def is_speech(self, *args):
            return True

    monkeypatch.setattr("helvox.utils.quality.webrtcvad.Vad", Vad)
    audio = np.zeros((48000 * 8, 1), dtype=np.float32)
    audio[4800:-4800, 0] = 0.15 * np.sin(
        2 * np.pi * 200 * np.arange(len(audio) - 9600) / 48000
    )
    return audio


def test_technical_good_with_pending_linguistic_review(speech):
    report = judge_recording(speech, 48000)
    assert report["verdict"] == "GOOD"
    assert report["linguistic_review"] == "pending"
    assert report["metrics"]["estimated_speech_noise_db"] is None


@pytest.mark.parametrize("purpose", ["reference", "dataset"])
@pytest.mark.parametrize("seconds", [1.0, 4.99, 10.51, 61.0])
def test_duration_does_not_reject_valid_audio(speech, seconds, purpose):
    report = judge_recording(
        np.resize(speech, (round(seconds * 48000), 1)), 48000, purpose=purpose
    )
    assert report["verdict"] == "GOOD"
    assert report["metrics"]["duration_s"] == seconds


def test_dataset_does_not_apply_short_reference_minimum(speech):
    assert (
        judge_recording(speech[:48000], 48000, purpose="dataset")["verdict"] == "GOOD"
    )


@pytest.mark.parametrize(
    "kind", ["empty", "nan", "stereo", "quiet", "clipped", "overflow"]
)
def test_bad_capture(speech, kind):
    audio = speech.copy()
    kwargs = {}
    if kind == "empty":
        audio = audio[:0]
    if kind == "nan":
        audio[0] = np.nan
    if kind == "stereo":
        audio = np.repeat(audio, 2, axis=1)
    if kind == "quiet":
        audio *= 0.00001
    if kind == "clipped":
        audio[5000:5500] = 1
    if kind == "overflow":
        kwargs["capture_errors"] = ["input overflow"]
    assert judge_recording(audio, 48000, **kwargs)["verdict"] == "BAD"


def test_no_sustained_speech_rejects_tone_when_vad_negative(monkeypatch, speech):
    monkeypatch.setattr(
        "helvox.utils.quality.webrtcvad.Vad.is_speech", lambda *args: False
    )
    assert judge_recording(speech, 48000)["verdict"] == "BAD"


def test_edge_sound_is_a_listening_warning_not_false_cutoff_proof(speech):
    speech[:2000] = 0.1
    report = judge_recording(speech, 48000)
    assert report["verdict"] == "GOOD"
    assert any("clip edge" in item for item in report["warnings"])
