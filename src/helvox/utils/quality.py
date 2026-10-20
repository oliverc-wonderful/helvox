"""Versioned, local technical checks. GOOD is not a dialect/clone-quality verdict."""

import math

import numpy as np
import webrtcvad

POLICY_VERSION = "swiss-reference-v2"


def judge_recording(audio, sample_rate, *, purpose="reference", capture_errors=()):
    reasons, warnings = [], []
    metrics = {}

    def result():
        return {
            "version": POLICY_VERSION,
            "purpose": purpose,
            "verdict": "BAD" if reasons else "GOOD",
            "reasons": reasons,
            "warnings": warnings,
            "metrics": metrics,
            "linguistic_review": "pending",
        }

    if purpose not in ("reference", "dataset"):
        raise ValueError("Unknown recording purpose")
    if audio is None or np.size(audio) == 0:
        reasons.append("No audio captured. Check the microphone and record again.")
        return result()
    x = np.asarray(audio)
    if sample_rate not in (8000, 16000, 32000, 48000):
        reasons.append("Unsupported sample rate for speech detection.")
        return result()
    if x.ndim == 2 and x.shape[1] == 1:
        x = x[:, 0]
    if x.ndim != 1 or not np.isfinite(x).all():
        reasons.append("Audio must be finite mono samples.")
        return result()
    if np.issubdtype(x.dtype, np.integer):
        x = x.astype(np.float64) / max(abs(np.iinfo(x.dtype).min), 1)
    else:
        x = x.astype(np.float64)
    duration = len(x) / sample_rate
    rms = float(np.sqrt(np.mean(x * x)))

    def db(value):
        return round(20 * math.log10(max(value, 1e-12)), 2)

    metrics.update(
        duration_s=round(duration, 4),
        rms_dbfs=db(rms),
        peak_dbfs=db(float(np.max(np.abs(x)))),
        dc_offset=float(np.mean(x)),
    )
    if capture_errors:
        reasons.append("Microphone capture reported lost/invalid frames. Record again.")
    metrics["capture_errors"] = list(capture_errors)
    clipped = np.abs(x) >= 0.999
    metrics["clipped_fraction"] = float(np.mean(clipped))
    run = longest = 0
    for value in clipped:
        run = run + 1 if value else 0
        longest = max(longest, run)
    metrics["longest_clipped_run"] = longest
    if metrics["clipped_fraction"] >= 0.001 or longest >= 5:
        reasons.append("Clipping detected. Lower microphone gain and record again.")
    if rms < 0.01:
        reasons.append(
            "Recording is too quiet or silent (below −40 dBFS RMS). Check microphone"
            " distance/gain."
        )
    elif rms < 0.025:
        warnings.append("Low level: listen for noise before accepting.")
    if abs(metrics["dc_offset"]) > 0.02:
        warnings.append("Large DC offset: check microphone/interface.")
    frame_size = sample_rate * 30 // 1000
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    vad = webrtcvad.Vad(2)
    voiced, powers = [], []
    for start in range(0, len(x) - frame_size + 1, frame_size):
        voiced.append(
            vad.is_speech(pcm[start : start + frame_size].tobytes(), sample_rate)
        )
        powers.append(float(np.mean(x[start : start + frame_size] ** 2)))
    metrics["speech_fraction"] = float(np.mean(voiced)) if voiced else 0
    if sum(voiced) * 0.03 < 0.3:
        reasons.append(
            "No sustained speech detected. Check the microphone and record again."
        )
    elif metrics["speech_fraction"] < 0.35:
        warnings.append(
            "Long pauses or little detected speech: listen before accepting."
        )
    # Approximation only: unvoiced sounds may be consonants, not room noise.
    noise = [p for p, v in zip(powers, voiced) if not v]
    speech = [p for p, v in zip(powers, voiced) if v]
    if len(noise) >= 10 and speech:
        noise_power = float(np.percentile(noise, 20))
        estimate = 10 * math.log10(
            max(float(np.median(speech)), 1e-12) / max(noise_power, 1e-12)
        )
        metrics["estimated_speech_noise_db"] = round(estimate, 2)
        if estimate < 20:
            warnings.append(
                "Possible background noise. This estimate is not a calibrated SNR;"
                " listen and re-record if audible."
            )
    else:
        metrics["estimated_speech_noise_db"] = None
    edge = min(len(x), sample_rate // 50)
    if (
        float(np.sqrt(np.mean(x[:edge] ** 2))) > 0.02
        or float(np.sqrt(np.mean(x[-edge:] ** 2))) > 0.02
    ):
        warnings.append(
            "Sound touches a clip edge. Listen for a cut onset/final sound; keep the"
            " raw take."
        )
    return result()
