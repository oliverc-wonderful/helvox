import json
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import messagebox, ttk

from platformdirs import user_config_path

from helvox.ui.auto_resize_text import AutoResizingText
from helvox.ui.button import RoundedButton
from helvox.ui.rounded_canvas import RoundedCanvas
from helvox.ui.settings import SettingsDialog
from helvox.utils.platform import app_font, default_recordings_dir
from helvox.utils.recorder import Recorder
from helvox.utils.sync import sync_take
from helvox.utils.takes import archive_take, write_json


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root

        self.recorder = Recorder(
            output_folder=default_recordings_dir(), sample_rate=48000, channels=1
        )

        self.settings_path = (
            user_config_path(appname="helvox", appauthor="noxenum") / "config.ini"
        )

        self.current_take = None
        self.sync_executor = ThreadPoolExecutor(max_workers=1)
        self.sync_future = None
        self.sync_requested = False
        self.setup_window()
        self.setup_ui()

        # Show settings dialog on startup
        self.show_settings()

    def setup_window(self) -> None:
        self.root.title("Helvox")
        self.root.geometry("800x600")

        # Set minimum window size
        self.root.minsize(900, 700)

        # Set app icon
        icon_path = Path(__file__).parent / "resources" / "icons" / "app.png"
        if icon_path.exists():
            icon = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(False, icon)

        # Bind configure event
        self.root.bind("<Configure>", self.configure_handler)

    def setup_ui(self) -> None:
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nswe")

        # Configure grid weights for responsiveness
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)  # Allow spacing before buttons
        main_frame.columnconfigure(0, weight=1)

        # Settings button at the top
        settings_frame = ttk.Frame(main_frame)
        settings_frame.grid(row=0, column=0, sticky="we", pady=(0, 10))
        settings_frame.columnconfigure(0, weight=1)

        settings_btn = RoundedButton(
            settings_frame,
            text="Settings",
            command=self.show_settings,
            bg_color="#E6E6E6",
            fg_color="#363636",
            width=120,
            height=40,
            corner_radius=20,
            dot=False,
        )
        settings_btn.grid(row=0, column=0, padx=5, sticky="e")

        # Text frame
        text_frame = ttk.LabelFrame(main_frame, text="Text", padding="5")
        text_frame.grid(row=1, column=0, sticky="we", pady=5, padx=5)
        text_frame.columnconfigure(0, weight=1)

        de_text_frame = ttk.Frame(text_frame)
        de_text_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        de_text_frame.columnconfigure(0, weight=1)

        ttk.Label(de_text_frame, text="DE:").grid(row=0, column=0, sticky=tk.W, padx=0)

        self.de_text_var = tk.StringVar(value="")
        de_text_label = ttk.Label(
            de_text_frame,
            textvariable=self.de_text_var,
            relief="sunken",
            background="white",
            foreground="#8A8A8A",
            font=app_font(12),
            padding=5,
            anchor="w",
        )
        de_text_label.grid(row=1, column=0, sticky="ew")

        # update wraplength dynamically
        de_text_label.bind(
            "<Configure>",
            lambda e: e.widget.configure(wraplength=max(1, e.width - 10)),
        )

        # CH
        ch_text_frame = ttk.Frame(text_frame)
        ch_text_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ch_text_frame.columnconfigure(0, weight=1)

        ttk.Label(ch_text_frame, text="CH (Suggestion):").grid(
            row=0, column=0, sticky=tk.W, padx=0
        )

        self.ch_text_var = tk.StringVar(value="")
        ch_text_label = ttk.Label(
            ch_text_frame,
            textvariable=self.ch_text_var,
            relief="sunken",
            background="white",
            foreground="#8A8A8A",
            font=app_font(12),
            padding=5,
            anchor="w",
        )
        ch_text_label.grid(row=1, column=0, sticky="ew")

        # update wraplength dynamically
        ch_text_label.bind(
            "<Configure>",
            lambda e: e.widget.configure(wraplength=max(1, e.width - 10)),
        )

        # CH (Editable)
        ch_text_edit_frame = ttk.Frame(text_frame)
        ch_text_edit_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ch_text_edit_frame.columnconfigure(0, weight=1)

        ttk.Label(ch_text_edit_frame, text="CH (Edit):").grid(
            row=0, column=0, sticky=tk.W, padx=0
        )

        self.ch_text_edit_var = tk.StringVar(value="")
        self.speaker_input = AutoResizingText(
            ch_text_edit_frame,
            textvariable=self.ch_text_edit_var,
            font=app_font(12),
            background="white",
            foreground="#000000",
            wrap="word",
            padx=5,
            pady=5,
            min_height=2,
            max_height=8,
        )
        self.speaker_input.grid(row=1, column=0, padx=(0, 0), pady=8, sticky="ew")

        # Recording frame
        recording_frame = ttk.LabelFrame(main_frame, text="Recording", padding="5")
        recording_frame.grid(row=2, column=0, sticky="we", pady=5, padx=5)

        # Configure recording frame columns - column 2 expands
        recording_frame.columnconfigure(2, weight=1)

        self.level_canvas = tk.Canvas(recording_frame, width=40, height=160, bg="black")
        self.level_canvas.grid(row=0, rowspan=4, column=0, sticky="ns", padx=5, pady=5)

        self.level_text = tk.StringVar(value="Level: 0 dB")
        ttk.Label(recording_frame, textvariable=self.level_text).grid(
            row=4, column=0, sticky=tk.W, padx=5
        )

        self.waveform_canvas_full = RoundedCanvas(
            recording_frame, height=50, bg="black", corner_radius=20
        )
        self.waveform_canvas_full.grid(row=0, column=2, sticky="we", padx=5, pady=5)

        self.play_btn_full = RoundedButton(
            recording_frame,
            text="Preview",
            command=self.recorder.play_audio_data_full_audio,
            bg_color="#10A560",
            fg_color="#FFFFFF",
            width=120,
            height=50,
            corner_radius=20,
        )
        self.play_btn_full.grid(row=0, column=3, padx=5)

        self.duration_text_full = tk.StringVar(value="Full | Duration: 0.0 seconds")
        ttk.Label(recording_frame, textvariable=self.duration_text_full).grid(
            row=1, column=2, sticky=tk.W, padx=5
        )

        self.waveform_canvas_trimmed = RoundedCanvas(
            recording_frame, height=50, bg="black", corner_radius=20
        )
        self.waveform_canvas_trimmed.grid(row=2, column=2, sticky="we", padx=5, pady=5)

        self.play_btn_trimmed = RoundedButton(
            recording_frame,
            text="Preview",
            command=self.recorder.play_audio_data_trimmed_audio,
            bg_color="#10A560",
            fg_color="#FFFFFF",
            width=120,
            height=50,
            corner_radius=20,
        )
        self.play_btn_trimmed.grid(row=2, column=3, padx=5)

        self.duration_text_trimmed = tk.StringVar(
            value="Trimmed | Duration: 0.0 seconds"
        )
        ttk.Label(recording_frame, textvariable=self.duration_text_trimmed).grid(
            row=3, column=2, sticky=tk.W, padx=5
        )

        # Record Button
        self.record_btn = RoundedButton(
            recording_frame,
            text="REC",
            command=self.toggle_recording,
            bg_color="#000000",
            fg_color="#FFFFFF",
            width=120,
            height=40,
            corner_radius=20,
            dot=True,
        )
        self.record_btn.grid(row=4, column=3, padx=5)

        self.quality_text = tk.StringVar(
            value="Record a take to run the technical judge."
        )
        ttk.Label(recording_frame, textvariable=self.quality_text, wraplength=650).grid(
            row=5, column=1, columnspan=3, sticky="w", pady=8
        )
        self.listened_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            recording_frame,
            text=(
                "I listened: exact words, intended dialect, one voice, clean complete"
                " sounds."
            ),
            variable=self.listened_var,
        ).grid(row=6, column=1, columnspan=3, sticky="w")
        self.sync_text = tk.StringVar(
            value="Sync disabled until a Wonderful profile is configured."
        )
        ttk.Label(settings_frame, textvariable=self.sync_text).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(settings_frame, text="Retry sync", command=self.request_sync).grid(
            row=0, column=1, padx=5
        )

        # Spacer
        ttk.Frame(main_frame).grid(row=3, column=0, sticky="nsew")

        # Button frame with separator
        ttk.Separator(main_frame, orient="horizontal").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(0, 15)
        )

        # Controls
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=4, column=0, sticky="we", pady=(0, 0))
        control_frame.columnconfigure(0, weight=1)

        # Total duration
        self.duration_text = tk.StringVar(value="Total Duration: 0s")
        ttk.Label(control_frame, textvariable=self.duration_text).grid(
            row=0, column=0, sticky=tk.W, padx=5
        )

        # Skip button at the bottom
        settings_btn = RoundedButton(
            control_frame,
            text="Skip",
            command=self.skip,
            bg_color="#E6E6E6",
            fg_color="#363636",
            width=120,
            height=40,
            corner_radius=20,
            dot=False,
        )
        settings_btn.grid(row=0, column=1, padx=5, sticky="e")

        # Next button at the bottom
        settings_btn = RoundedButton(
            control_frame,
            text="Save & Next",
            command=self.save,
            bg_color="#3B32B3",
            fg_color="#F5F5F5",
            width=120,
            height=40,
            corner_radius=20,
            dot=False,
        )
        settings_btn.grid(row=0, column=2, padx=5, sticky="e")

    def show_settings(self) -> None:
        self.recorder.load_settings(self.settings_path)
        dialog = SettingsDialog(self.root, self.recorder)
        result = dialog.show()

        if result:
            # Apply settings
            self.recorder.update_output_folder(result["output_folder"])
            self.recorder.update_selected_device(result["device"])
            self.recorder.speaker_id = result["speaker_id"]
            self.recorder.speaker_dialect = result["speaker_dialect"]
            self.recorder.input_file = result["input_file"]
            self.recorder.purpose = result["purpose"]
            self.recorder.sync_profile = result["sync_profile"]
            self.recorder.output_file = (
                Path(result["output_folder"]) / result["speaker_id"] / "output.json"
            )
            self.recorder.skipped_file = (
                Path(result["output_folder"]) / result["speaker_id"] / "skipped.txt"
            )

            self.recorder.save_settings(self.settings_path)
            self.recorder.load_data()

        self.clear_take()
        self.start_monitoring()
        self.load_next_sample()

        self.update_duration()

    def update_duration(self) -> None:
        total_seconds = self.recorder.total_duration
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds - int(total_seconds)) * 100)

        self.duration_text.set(
            "Total Duration:"
            f" {hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:02d}"
        )

    def update_level_meter(self) -> None:
        level = self.recorder.get_current_level()

        # Update level text
        self.level_text.set(f"Level: {level:.1f} dB")

        # Get canvas dimensions
        width = self.level_canvas.winfo_width()
        height = self.level_canvas.winfo_height()

        if height > 1:  # Only draw if canvas is visible
            # Clear canvas
            self.level_canvas.delete("all")

            # Convert dB to normalized value (0-1)
            db_min = -60
            db_max = 0
            normalized = max(0, min(1, (level - db_min) / (db_max - db_min)))

            # Number of segments
            num_segments = 20
            segment_height = height / num_segments
            segment_spacing = 2  # Pixels between segments

            # Draw segments from bottom to top
            for i in range(num_segments):
                segment_normalized = i / num_segments
                segment_y = height - (i + 1) * segment_height

                # Determine if segment should be lit
                is_lit = normalized >= segment_normalized

                # Determine color based on position
                if i >= int(num_segments * 0.9):  # Top 10% red
                    color = "red" if is_lit else "darkred"
                elif i >= int(num_segments * 0.7):  # Next 20% yellow
                    color = "yellow" if is_lit else "darkgoldenrod4"
                else:  # Bottom 70% green
                    color = "green2" if is_lit else "darkgreen"

                # Draw segment
                self.level_canvas.create_rectangle(
                    2,  # Left margin
                    segment_y + segment_spacing / 2,
                    width - 2,  # Right margin
                    segment_y + segment_height - segment_spacing / 2,
                    fill=color,
                    outline="",
                )

            # Draw tick marks and dB labels every 10 dB
            for i in range(0, 7):
                db_value = db_min + (i * 10)
                y_pos = height * (1 - (db_value - db_min) / (db_max - db_min))
                # Tick mark
                self.level_canvas.create_line(0, y_pos, 5, y_pos, fill="gray", width=1)
                # dB label
                self.level_canvas.create_text(
                    width + 15,
                    y_pos,
                    text=f"{db_value}",
                    fill="white",
                    anchor="w",
                    font=("Arial", 7),
                )

        # Schedule next update
        self.root.after(50, self.update_level_meter)

    def start_monitoring(self) -> None:
        if self.recorder.selected_device:
            self.recorder.start_monitoring()
            self.update_level_meter()

    def toggle_recording(self) -> None:
        if not self.recorder.recording:
            if self.current_id is None:
                return
            self.clear_take()
            try:
                self.recorder.start_recording()
            except Exception:
                self.recorder.recording = False
                messagebox.showerror(
                    "Microphone",
                    "Could not start recording. Check the selected microphone.",
                )
                return
            self.clear_waveform_canvas()
            self.record_btn.config(
                text="Stop Recording", bg_color="#8B0000", dot=False
            )  # Dark red
        else:
            self.recorder.stop_recording()
            self.record_btn.config(text="REC", bg_color="#000000", dot=True)  # Black
            self.update_waveform()
            report = self.recorder.quality
            self.quality_text.set(
                report["verdict"]
                + " — "
                + (
                    " ".join(report["reasons"] + report["warnings"])
                    or "Technical checks passed. Listen before accepting."
                )
            )
            if (
                self.recorder.full_audio is not None
                and self.recorder.trimmed_audio is not None
            ):
                try:
                    self.current_take = archive_take(
                        self.recorder.output_folder,
                        speaker_id=self.recorder.speaker_id,
                        sample_id=self.current_id,
                        dialect=self.recorder.speaker_dialect,
                        text_de=self.de_text_var.get(),
                        text_ch=self.ch_text_edit_var.get(),
                        audio=self.recorder.trimmed_audio,
                        raw_audio=self.recorder.full_audio,
                        sample_rate=self.recorder.sample_rate,
                        quality=report,
                        microphone=self.recorder.selected_device,
                    )
                except (OSError, ValueError) as error:
                    messagebox.showerror("Take not saved", str(error))
                else:
                    self.request_sync()

    def clear_take(self):
        self.current_take = None
        self.recorder.full_audio = None
        self.recorder.trimmed_audio = None
        self.recorder.quality = None
        self.listened_var.set(False)
        self.quality_text.set("Record a new take to run the technical judge.")
        self.clear_waveform_canvas()

    def request_sync(self):
        profile = self.recorder.sync_profile
        if not profile:
            self.sync_text.set(
                "Local only. Configure a Wonderful profile to enable sync."
            )
            return
        if self.sync_future is not None:
            self.sync_requested = True
            return
        folder = self.recorder.output_folder

        def upload_pending():
            successes, failures = 0, 0
            for file in folder.rglob("take.json"):
                try:
                    sync_take(file.parent, profile)
                    successes += 1
                except Exception:
                    failures += 1
            return successes, failures

        self.sync_text.set("Syncing recordings… local copies remain safe.")
        self.sync_future = self.sync_executor.submit(upload_pending)
        self.root.after(100, self.poll_sync)

    def poll_sync(self):
        if not self.sync_future.done():
            self.root.after(100, self.poll_sync)
            return
        try:
            successes, failures = self.sync_future.result()
            self.sync_text.set(f"{successes} synced; {failures} pending retry.")
        except Exception:
            self.sync_text.set("Sync failed; local takes remain queued.")
        self.sync_future = None
        if self.sync_requested:
            self.sync_requested = False
            self.request_sync()

    def clear_waveform_canvas(self) -> None:
        self.waveform_canvas_full.delete("all")
        self.waveform_canvas_trimmed.delete("all")

        self.waveform_canvas_full.draw_canvas()
        self.waveform_canvas_trimmed.draw_canvas()

    def load_next_sample(self) -> None:
        self.current_id = self.recorder.get_next_id()
        if self.current_id is None:
            self.de_text_var.set("All samples completed.")
            self.ch_text_var.set("")
            self.ch_text_edit_var.set("")
            return

        sample = self.recorder.get_sample_by_id(self.current_id)
        text_de = sample["de"]

        if "ch" in sample:
            text_ch = sample["ch"]
        else:
            text_ch = sample[f"ch_{self.recorder.speaker_dialect.lower()}"]

        self.de_text_var.set(text_de)
        self.ch_text_var.set(text_ch)
        self.ch_text_edit_var.set(text_ch)

    def update_waveform(self) -> None:
        if self.recorder.full_audio is None or self.recorder.trimmed_audio is None:
            return

        # Update duration text
        duration_full = self.recorder.get_duration_full_audio()
        self.duration_text_full.set(f"Full | Duration: {duration_full:.1f} seconds")

        duration_trimmed = self.recorder.get_duration_trimmed_audio()
        self.duration_text_trimmed.set(
            f"Trimmed | Duration: {duration_trimmed:.1f} seconds"
        )

        # Get waveform data
        waveform_full = self.recorder.get_waveform_full_audio()
        waveform_trimmed = self.recorder.get_waveform_trimmed_audio()

        # Get canvas dimensions
        width = self.waveform_canvas_full.winfo_width()
        height = self.waveform_canvas_full.winfo_height()
        center_y = height // 2

        # Clear canvas
        self.clear_waveform_canvas()

        # Draw vertical bars (full)
        bar_width = max(1, width // len(waveform_full) // 2)
        for i, value in enumerate(waveform_full):
            x = int((i / len(waveform_full)) * width)
            # Scale the value to half the height (since we're drawing from center)
            bar_height = int(value * (height / 2))
            # Draw vertical bar centered at center_y
            if bar_height != 0:  # Only draw if there's a visible amplitude
                self.waveform_canvas_full.create_line(
                    x,
                    center_y - bar_height,
                    x,
                    center_y + bar_height,
                    fill="orange red",
                    width=bar_width,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                )

        # Draw vertical bars (trimmed)
        bar_width = max(1, width // len(waveform_trimmed) // 2)
        for i, value in enumerate(waveform_trimmed):
            x = int((i / len(waveform_trimmed)) * width)
            # Scale the value to half the height (since we're drawing from center)
            bar_height = int(value * (height / 2))
            # Draw vertical bar centered at center_y
            if bar_height != 0:  # Only draw if there's a visible amplitude
                self.waveform_canvas_trimmed.create_line(
                    x,
                    center_y - bar_height,
                    x,
                    center_y + bar_height,
                    fill="orange red",
                    width=bar_width,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                )

    def configure_handler(self, event):
        self.update_waveform()

    def save(self) -> None:
        if self.recorder.recording or self.current_take is None:
            return
        if self.recorder.quality["verdict"] == "BAD":
            messagebox.showwarning(
                "Re-record needed", " ".join(self.recorder.quality["reasons"])
            )
            return
        if not self.listened_var.get():
            messagebox.showwarning(
                "Listen first",
                "Preview the take and confirm exact words, dialect and clean complete"
                " speech.",
            )
            return
        record = json.loads(
            (self.current_take / "take.json").read_text(encoding="utf-8")
        )
        if record["text_ch"] != self.ch_text_edit_var.get():
            messagebox.showwarning(
                "Transcript changed",
                "The transcript changed after recording. Record the revised text"
                " again.",
            )
            return
        record["human_review"] = "accepted_by_speaker"
        write_json(self.current_take / "take.json", record)

        duration_s = self.recorder.save_audio(self.current_id)
        self.recorder.add_sample(
            id=self.current_id,
            text_de=self.de_text_var.get(),
            text_ch=self.ch_text_edit_var.get(),
            dialect=self.recorder.speaker_dialect,
            audio_path=f"{self.current_id}.flac",
            duration_s=duration_s,
            recording_id=record["recording_id"],
            quality=self.recorder.quality,
        )

        self.recorder.audio_data = []
        self.recorder.full_audio = None
        self.recorder.trimmed_audio = None

        self.request_sync()
        self.clear_take()

        self.update_duration()
        self.load_next_sample()

    def skip(self):
        if self.recorder.recording or self.current_id is None:
            return
        self.clear_take()
        self.recorder.add_skip(self.current_id)
        self.load_next_sample()

    def on_closing(self) -> None:
        self.recorder.stop_monitoring()
        if self.recorder.recording:
            self.recorder.stop_recording()
            self.recorder.stop_monitoring()
        self.sync_executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()
