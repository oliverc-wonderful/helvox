import configparser
import json
from pathlib import Path
from typing import Optional, Union

import numpy as np
import sounddevice as sd
import soundfile as sf
from sounddevice import CallbackFlags

from helvox.utils.data import read_dataset
from helvox.utils.quality import judge_recording
from helvox.utils.takes import validate_component
from helvox.utils.trim import trim_silence


class Recorder:
    def __init__(
        self,
        output_folder: Union[str, Path],
        sample_rate: int = 48000,
        channels: int = 1,
    ) -> None:
        self.recording = False
        self.capture_errors = []
        self.quality = None
        self.purpose = "reference"
        self.sync_profile = ""
        self.monitoring = False
        self.output_folder = Path(output_folder)
        self.sample_rate = sample_rate
        self.channels = channels

        self.device_map = {}
        self.current_level = -60.0  # dB
        self.full_audio = None
        self.trimmed_audio = None

        self.monitor_stream = None
        self.stream = None

        self.selected_device = ""
        self.speaker_id = "unknown"
        self.speaker_dialect = "AG"
        self.input_file = ""
        self.output_file = ""
        self.skipped_file = ""

        self.input_data = []
        self.input_index = {}
        self.output_data = []
        self.output_index = {}
        self.skipped_ids = []

        self.open_ids = []
        self.total_duration = 0

    def get_audio_devices(self) -> dict:
        devices = sd.query_devices()
        device_map = {}

        for idx, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) > 0:
                device_map[str(device.get("name", f"device_{idx}"))] = idx

        return device_map

    def refresh_audio_devices(self) -> None:
        self.device_map = self.get_audio_devices()

    def calculate_rms_db(self, audio_data: np.ndarray) -> float:
        if len(audio_data) == 0:
            return -60.0

        # Calculate RMS
        rms = np.sqrt(np.mean(audio_data**2))

        # Convert to dB (with floor to avoid log(0))
        if rms > 0:
            db = 20 * np.log10(rms)
        else:
            db = -60.0

        return max(-60.0, min(0.0, db))

    def start_monitoring(self) -> None:
        if self.monitoring:
            self.stop_monitoring()

        device_idx = self.device_map.get(self.selected_device)
        if device_idx is None:
            return

        self.monitoring = True

        def monitor_callback(indata: np.ndarray, frames, time, status: CallbackFlags):
            if status:
                print(status)

            # Calculate level
            self.current_level = self.calculate_rms_db(indata)

        try:
            self.monitor_stream = sd.InputStream(
                device=device_idx,
                channels=self.channels,
                samplerate=self.sample_rate,
                callback=monitor_callback,
            )
            self.monitor_stream.start()
        except Exception as e:
            print(f"Error starting monitor stream: {e}")
            self.monitoring = False

    def stop_monitoring(self) -> None:
        if self.monitoring and self.monitor_stream:
            try:
                self.monitor_stream.stop()
                self.monitor_stream.close()
            except Exception as e:
                print(f"Error stopping monitor stream: {e}")
            finally:
                self.monitoring = False
                self.monitor_stream = None
                self.current_level = -60.0

    def get_current_level(self) -> float:
        return self.current_level

    def start_recording(self):
        if not self.selected_device:
            return

        device_idx = self.device_map.get(self.selected_device)

        # Stop monitoring while recording
        if self.monitoring:
            self.stop_monitoring()

        self.recording = True
        self.audio_data = []
        self.capture_errors = []
        self.quality = None
        self.full_audio = None
        self.trimmed_audio = None

        def callback(indata: np.ndarray, frames, time, status: CallbackFlags):
            if status:
                print(status)
            if status:
                self.capture_errors.append(str(status))
            self.audio_data.append(indata.copy())

            # Update level during recording
            self.current_level = self.calculate_rms_db(indata)

        self.stream = sd.InputStream(
            device=device_idx,
            channels=self.channels,
            samplerate=self.sample_rate,
            callback=callback,
        )

        self.stream.start()

    def stop_recording(self) -> None:
        if self.recording and self.stream:
            self.stream.stop()
            self.stream.close()
            self.recording = False

            if self.audio_data:
                self.full_audio = np.concatenate(self.audio_data, axis=0)

                self.trimmed_audio = trim_silence(
                    self.full_audio,
                    sample_rate=self.sample_rate,
                    aggressiveness=2,
                    frame_duration_ms=30,
                    padding_duration_s=0.1,
                )

            self.quality = judge_recording(
                self.trimmed_audio,
                self.sample_rate,
                purpose=self.purpose,
                capture_errors=self.capture_errors,
            )

            raw_quality = judge_recording(
                self.full_audio, self.sample_rate, purpose="dataset"
            )
            self.quality["metrics"]["raw"] = raw_quality["metrics"]
            for reason in raw_quality["reasons"]:
                if "Clipping" in reason and reason not in self.quality["reasons"]:
                    self.quality["reasons"].append(reason)
                    self.quality["verdict"] = "BAD"

            # Restart monitoring after recording stops
            self.start_monitoring()

    def save_audio(self, filename: str) -> float:
        validate_component(self.speaker_id)
        validate_component(filename)
        audio_path = self.output_folder / self.speaker_id / "audio" / f"{filename}.flac"

        if not audio_path.parent.exists():
            audio_path.parent.mkdir(parents=True, exist_ok=True)

        sf.write(audio_path, self.trimmed_audio, self.sample_rate, format="FLAC")

        return self.get_duration_trimmed_audio()

    def play_audio_data_full_audio(self):
        self.play_audio_data(self.full_audio)

    def play_audio_data_trimmed_audio(self):
        self.play_audio_data(self.trimmed_audio)

    def play_audio_data(self, audio):
        if audio is not None:
            sd.play(audio, self.sample_rate)

    def check_playback(self) -> bool:
        return sd.get_stream().active

    def get_duration_full_audio(self) -> float:
        return self.get_duration(self.full_audio)

    def get_duration_trimmed_audio(self) -> float:
        return self.get_duration(self.trimmed_audio)

    def get_duration(self, audio) -> float:
        if audio is not None:
            return len(audio) / self.sample_rate
        return 0.0

    def get_waveform_full_audio(self, num_points: int = 100) -> list[float]:
        return self.get_waveform_data(audio=self.full_audio, num_points=num_points)

    def get_waveform_trimmed_audio(self, num_points: int = 100) -> list[float]:
        return self.get_waveform_data(audio=self.trimmed_audio, num_points=num_points)

    def get_waveform_data(self, audio, num_points: int = 100) -> list[float]:
        if audio is None:
            return [0] * num_points

        # Flatten audio data and normalize to [-1, 1]
        data = audio.flatten()
        if not len(data):
            return [0] * num_points
        max_val = np.max(np.abs(data))
        if max_val > 0:
            data = data / max_val

        # Downsample by taking max and min in segments
        samples_per_point = len(data) // (
            num_points // 2
        )  # We'll get 2 points per segment
        if samples_per_point < 1:
            return list(data) + [0] * (num_points - len(data))

        waveform = []
        for i in range(num_points // 2):
            start = i * samples_per_point
            end = start + samples_per_point
            if start < len(data):
                segment = data[start : min(end, len(data))]
                # Get both max and min for symmetric display
                waveform.extend([float(np.max(segment)), float(np.min(segment))])
            else:
                waveform.extend([0.0, 0.0])

        return waveform[:num_points]  # Ensure we return exactly num_points

    def update_output_folder(self, folder: Union[str, Path]) -> None:
        self.output_folder = Path(folder)

    def update_selected_device(self, device_name: str) -> None:
        self.selected_device = device_name

    def restart_monitoring(self) -> None:
        self.stop_monitoring()
        self.start_monitoring()

    def save_settings(self, config_path: Path) -> None:
        if not config_path.parent.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)

        config = configparser.ConfigParser()
        config["Settings"] = {
            "output_folder": str(self.output_folder),
            "selected_device": self.selected_device,
            "speaker_id": self.speaker_id,
            "speaker_dialect": self.speaker_dialect,
            "input_file": self.input_file,
            "purpose": self.purpose,
            "sync_profile": self.sync_profile,
        }

        with open(config_path, "w") as configfile:
            config.write(configfile)

    def load_settings(self, config_path: Path) -> None:
        if not config_path.exists():
            return

        config = configparser.ConfigParser()
        config.read(config_path)

        settings = config["Settings"]
        self.output_folder = Path(
            settings.get("output_folder", str(self.output_folder))
        )
        self.selected_device = settings.get("selected_device", self.selected_device)
        self.speaker_id = settings.get("speaker_id", self.speaker_id)
        self.speaker_dialect = settings.get("speaker_dialect", self.speaker_dialect)
        self.input_file = settings.get("input_file", self.input_file)

        self.purpose = settings.get("purpose", "reference")
        self.sync_profile = settings.get("sync_profile", "")

        self.output_file = self.output_folder / self.speaker_id / "output.json"
        self.skipped_file = self.output_folder / self.speaker_id / "skipped.txt"

        self.load_data()

    def load_data(self) -> None:
        self.load_input_data()
        self.load_output_data()
        self.load_skipped_ids()

        self.open_ids = [
            idx
            for idx in list(self.input_index.keys())
            if (
                idx not in list(self.output_index.keys())
                and (idx not in self.skipped_ids)
            )
        ]

        self.total_duration = self.calc_total_duration()

    def calc_total_duration(self) -> float:
        return sum(
            [
                sample["duration_s"]
                for sample in self.output_data
                if "duration_s" in sample
            ]
        )

    def load_input_data(self) -> None:
        if len(self.input_file) > 0 and Path(self.input_file).exists():
            self.input_data = read_dataset(
                Path(self.input_file), dialect_filter=self.speaker_dialect.lower()
            )
            self.input_index = {str(d["id"]): d for d in self.input_data}
        else:
            self.input_data = []

    def load_output_data(self) -> None:
        if len(str(self.output_file)) > 0 and Path(self.output_file).exists():
            self.output_data = read_dataset(Path(self.output_file))
            self.output_index = {str(d["id"]): d for d in self.output_data}
        else:
            self.output_data = []

    def load_skipped_ids(self) -> None:
        if len(str(self.skipped_file)) > 0 and Path(self.skipped_file).exists():
            with open(self.skipped_file, mode="r", encoding="utf-8") as f:
                self.skipped_ids = [line.strip() for line in f.readlines()]
        else:
            self.skipped_ids = []

    def get_sample_by_id(self, id: Union[int, str]) -> dict:
        id_str = str(id)
        return self.output_index.get(id_str) or self.input_index.get(id_str) or {}

    def add_skip(self, id: Union[int, str]) -> None:
        if id in self.skipped_ids:
            return

        self.skipped_ids.append(str(id))
        if not Path(self.skipped_file).parent.exists():
            Path(self.skipped_file).parent.mkdir(parents=True, exist_ok=True)

        with open(self.skipped_file, mode="a", encoding="utf-8") as f:
            f.write(f"{id}\n")

    def add_sample(
        self,
        id: str,
        text_de: str,
        text_ch: str,
        dialect: str,
        audio_path: str,
        duration_s: float,
        recording_id: str = "",
        quality: Optional[dict] = None,
    ) -> None:
        sample = {
            "id": id,
            "de": text_de,
            "ch": text_ch,
            "dialect": dialect.lower(),
            "audio": audio_path,
            "duration_s": duration_s,
            "recording_id": recording_id,
            "quality": quality,
        }

        self.output_data = [
            item for item in self.output_data if str(item["id"]) != str(id)
        ]
        self.output_data.append(sample)
        self.output_index[str(id)] = sample

        if not Path(self.skipped_file).parent.exists():
            Path(self.skipped_file).parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_file, mode="w", encoding="utf-8") as f:
            json.dump(self.output_data, f, ensure_ascii=False, indent=4)

        self.total_duration = self.calc_total_duration()

    def get_next_id(self) -> Optional[str]:
        if not self.open_ids:
            return None
        return self.open_ids.pop(0)
