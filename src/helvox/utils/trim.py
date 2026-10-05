import numpy as np
import webrtcvad


def trim_silence(
    audio,
    sample_rate=48000,
    aggressiveness=3,
    frame_duration_ms=30,
    padding_duration_s=0.1,
):
    """
    Trim silence from start and end of audio using WebRTC VAD.

    Args:
        audio: numpy array of audio samples (float32 or int16)
        sample_rate: sample rate in Hz (must be 8000, 16000, 32000, or 48000)
        aggressiveness: VAD aggressiveness (0-3, higher = more aggressive)
        frame_duration_ms: frame size in ms (10, 20, or 30)
        padding_duration_s: seconds to keep at start/end (default 0.1)

    Returns:
        Trimmed audio as numpy array
    """

    # WebRTC VAD only works with 16-bit PCM
    if audio.dtype == np.float32 or audio.dtype == np.float64:
        # Convert float [-1, 1] to int16
        audio_int16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    else:
        audio_int16 = audio.astype(np.int16)

    # Initialize VAD
    vad = webrtcvad.Vad(aggressiveness)

    # Calculate frame size in samples
    frame_size = int(sample_rate * frame_duration_ms / 1000)

    # Pad audio to make it divisible by frame_size
    num_frames = len(audio_int16) // frame_size
    audio_padded = audio_int16[: num_frames * frame_size]

    # Split into frames and check each frame for voice activity
    frames = []
    voiced_frames = []

    for i in range(0, len(audio_padded), frame_size):
        frame = audio_padded[i : i + frame_size]

        # Convert frame to bytes
        frame_bytes = frame.tobytes()

        # Check if frame contains voice
        is_speech = vad.is_speech(frame_bytes, sample_rate)

        frames.append((i, frame))
        voiced_frames.append(is_speech)

    # Find first and last voiced frames
    if not any(voiced_frames):
        # No voice detected, return original audio
        return audio

    first_voiced = voiced_frames.index(True)
    last_voiced = len(voiced_frames) - 1 - voiced_frames[::-1].index(True)

    # Calculate start and end sample positions
    start_sample = frames[first_voiced][0]
    end_sample = frames[last_voiced][0] + frame_size

    # Add padding
    padding_samples = int(padding_duration_s * sample_rate)
    start_sample = max(0, start_sample - padding_samples)
    end_sample = min(len(audio), end_sample + padding_samples)

    # Return trimmed audio in original format
    return audio[start_sample:end_sample]
