import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from helvox.utils.platform import app_font
from helvox.utils.recorder import Recorder
from helvox.utils.takes import validate_component


class SettingsDialog:
    def __init__(self, parent: tk.Tk, recorder: Recorder) -> None:
        self.recorder = recorder
        self.result = None

        # Create modal dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("650x550")
        self.dialog.resizable(False, False)

        # Make it modal
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center the dialog
        self.center_dialog(parent)

        # Set app icon
        icon_path = Path(__file__).parent.parent / "resources" / "icons" / "app.png"
        if icon_path.exists():
            icon = tk.PhotoImage(file=icon_path)
            self.dialog.iconphoto(False, icon)

        # Configure style
        self.setup_styles()
        self.setup_ui()

        # Handle window close button
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_cancel)

        # Bind Enter and Escape keys
        self.dialog.bind("<Return>", lambda e: self.on_ok())
        self.dialog.bind("<Escape>", lambda e: self.on_cancel())

    def center_dialog(self, parent: tk.Tk) -> None:
        """Center dialog on parent window."""
        self.dialog.update_idletasks()
        x = (
            parent.winfo_x()
            + (parent.winfo_width() // 2)
            - (self.dialog.winfo_width() // 2)
        )
        y = (
            parent.winfo_y()
            + (parent.winfo_height() // 2)
            - (self.dialog.winfo_height() // 2)
        )
        self.dialog.geometry(f"+{x}+{y}")

    def setup_styles(self) -> None:
        """Configure custom styles for better appearance."""
        style = ttk.Style()

        # Custom styles
        style.configure("Title.TLabel", font=app_font(8))
        style.configure("Info.TLabel", font=app_font(9), foreground="#666")
        style.configure("TLabelframe.Label", font=app_font(9, bold=True))
        style.configure("TLabelframe", padding=15)

        # Button styles
        style.configure("Accent.TButton", font=app_font(9, bold=True))

    def setup_ui(self) -> None:
        # Main container with padding
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # Configure grid weights for responsiveness
        self.dialog.rowconfigure(0, weight=1)
        self.dialog.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)  # Allow spacing before buttons
        main_frame.columnconfigure(0, weight=1)

        # Tabs
        tab_control = ttk.Notebook(main_frame)
        tab_speaker = ttk.Frame(tab_control)
        tab_data = ttk.Frame(tab_control)
        tab_audio = ttk.Frame(tab_control)
        tab_review = ttk.Frame(tab_control)

        tab_control.add(tab_speaker, text="Speaker")
        tab_control.add(tab_data, text="Data")
        tab_control.add(tab_audio, text="Audio")
        tab_control.add(tab_review, text="Quality & Sync")
        ttk.Label(
            tab_review, text="Purpose (reference clips must be 5–10.5 seconds)"
        ).pack(anchor="w", padx=15, pady=10)
        self.purpose_var = tk.StringVar(value=self.recorder.purpose)
        ttk.Combobox(
            tab_review,
            textvariable=self.purpose_var,
            values=("reference", "dataset"),
            state="readonly",
        ).pack(anchor="w", padx=15)
        ttk.Label(
            tab_review, text="Wonderful CLI profile (blank keeps recordings local)"
        ).pack(anchor="w", padx=15, pady=10)
        self.profile_var = tk.StringVar(value=self.recorder.sync_profile)
        ttk.Entry(tab_review, textvariable=self.profile_var).pack(fill="x", padx=15)
        ttk.Label(
            tab_review,
            text=(
                "Uses your signed-in wful profile. No API key is stored.\nSync sends"
                " raw and trimmed takes, including rejected attempts.\nOnly enable for"
                " a workspace authorized to hold these recordings."
            ),
            wraplength=550,
        ).pack(anchor="w", padx=15, pady=15)

        tab_control.grid(row=0, column=0, sticky="ew")

        # Speaker Settings
        speaker_frame = ttk.LabelFrame(
            tab_speaker, text="Speaker Configuration", padding="15"
        )
        speaker_frame.grid(row=0, column=0, sticky="ew", padx=(10, 10), pady=(10, 0))
        speaker_frame.columnconfigure(1, weight=1)

        # Speaker ID
        ttk.Label(speaker_frame, text="Speaker ID:", style="Title.TLabel").grid(
            column=0, row=0, padx=(0, 10), pady=8, sticky="w"
        )
        self.speaker_var = tk.StringVar(value=self.recorder.speaker_id)
        self.speaker_input = ttk.Entry(
            speaker_frame, textvariable=self.speaker_var, font=app_font(9)
        )
        self.speaker_input.grid(row=1, column=0, padx=(0, 5), pady=8, sticky="ew")

        # Dialect
        ttk.Label(speaker_frame, text="Dialect:", style="Title.TLabel").grid(
            column=1, row=0, padx=(0, 10), pady=8, sticky="w"
        )
        self.dialect_var = tk.StringVar(value=self.recorder.speaker_dialect)
        self.speaker_dialect = ttk.Combobox(
            speaker_frame,
            textvariable=self.dialect_var,
            state="readonly",
            font=app_font(9),
            width=30,
        )
        self.speaker_dialect["values"] = (
            "AG",
            "BE",
            "BS",
            "GR",
            "LU",
            "SG",
            "VS",
            "ZH",
        )
        self.speaker_dialect.grid(row=1, column=1, padx=(0, 5), pady=8, sticky="w")

        # Input File Selection
        file_frame = ttk.LabelFrame(tab_data, text="Input File", padding="15")
        file_frame.grid(row=0, column=0, sticky="ew", padx=(10, 10), pady=(10, 0))
        file_frame.columnconfigure(0, weight=1)

        # Folder path display
        file_display_frame = ttk.Frame(file_frame)
        file_display_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        file_display_frame.columnconfigure(0, weight=1)

        self.file_var = tk.StringVar(value=str(self.recorder.input_file))
        folder_label = ttk.Label(
            file_display_frame,
            textvariable=self.file_var,
            wraplength=500,
            relief="sunken",
            background="white",
            foreground="#333",
            font=app_font(9),
            padding=5,
        )
        folder_label.grid(row=0, column=0, sticky="ew")

        # Browse button
        browse_file_btn = ttk.Button(
            file_frame, text="Browse...", command=self.select_file, width=12
        )
        browse_file_btn.grid(row=0, column=1, pady=(0, 0), sticky="e")

        # Info label
        info_label = ttk.Label(
            file_frame,
            text="Select the file where the text data is stored (JSON)",
            style="Info.TLabel",
        )
        info_label.grid(row=1, column=0, sticky="w", pady=(5, 0))

        # Output Folder Selection
        folder_frame = ttk.LabelFrame(tab_data, text="Output Folder", padding="15")
        folder_frame.grid(row=1, column=0, sticky="ew", padx=(10, 10), pady=(10, 0))
        folder_frame.columnconfigure(0, weight=1)

        # Folder path display
        folder_display_frame = ttk.Frame(folder_frame)
        folder_display_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        folder_display_frame.columnconfigure(0, weight=1)

        self.folder_var = tk.StringVar(value=str(self.recorder.output_folder))
        folder_label = ttk.Label(
            folder_display_frame,
            textvariable=self.folder_var,
            wraplength=500,
            relief="sunken",
            background="white",
            foreground="#333",
            font=app_font(9),
            padding=5,
        )
        folder_label.grid(row=0, column=0, sticky="ew")

        # Browse button
        browse_btn = ttk.Button(
            folder_frame, text="Browse...", command=self.select_folder, width=12
        )
        browse_btn.grid(row=0, column=1, pady=(0, 0), sticky="e")

        # Info label
        info_label = ttk.Label(
            folder_frame,
            text="Select the folder where the audio recordings should be saved",
            style="Info.TLabel",
        )
        info_label.grid(row=1, column=0, sticky="w", pady=(5, 0))

        # Audio Device Selection
        device_frame = ttk.LabelFrame(
            tab_audio, text="Audio Input Device", padding="15"
        )
        device_frame.grid(row=2, column=0, sticky="ew", padx=(10, 10), pady=(10, 0))
        device_frame.columnconfigure(0, weight=1)

        # Device selection row
        device_row = ttk.Frame(device_frame)
        device_row.grid(row=0, column=0, sticky="ew")
        device_row.columnconfigure(0, weight=1)

        self.device_var = tk.StringVar(value=self.recorder.selected_device or "")
        self.device_combo = ttk.Combobox(
            device_row,
            textvariable=self.device_var,
            state="readonly",
            font=app_font(9),
        )
        self.device_combo.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="ew")

        refresh_btn = ttk.Button(
            device_row, text="Refresh", command=self.refresh_devices, width=12
        )
        refresh_btn.grid(row=0, column=1, pady=5)

        # Info label
        info_label = ttk.Label(
            device_frame,
            text="Select the microphone or audio input device to use for recording",
            style="Info.TLabel",
        )
        info_label.grid(row=1, column=0, sticky="w", pady=(5, 0))

        # Populate devices
        self.refresh_devices()

        # Spacer
        ttk.Frame(main_frame).grid(row=3, column=0, sticky="nsew")

        # Button frame with separator
        ttk.Separator(main_frame, orient="horizontal").grid(
            row=4, column=0, sticky="ew", pady=(0, 15)
        )

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, pady=(0, 0))

        # Buttons with improved styling
        cancel_btn = ttk.Button(
            button_frame, text="Cancel", command=self.on_cancel, width=15
        )
        cancel_btn.grid(row=0, column=0, padx=5)

        ok_btn = ttk.Button(
            button_frame,
            text="OK",
            command=self.on_ok,
            style="Accent.TButton",
            width=15,
        )
        ok_btn.grid(row=0, column=1, padx=5)

        # Set focus to OK button
        ok_btn.focus_set()

    def select_folder(self) -> None:
        """Open folder selection dialog."""
        folder = filedialog.askdirectory(
            title="Select Output Folder", initialdir=self.recorder.output_folder
        )
        if folder:
            self.folder_var.set(str(Path(folder)))

    def select_file(self) -> None:
        file = filedialog.askopenfilename(
            title="Select Input File", filetypes=[("JSON files", "*.json")]
        )

        if file:
            self.file_var.set(str(Path(file)))
            self.recorder.input_file = file

    def refresh_devices(self) -> None:
        """Refresh available audio devices."""
        self.recorder.refresh_audio_devices()
        device_names = list(self.recorder.device_map.keys())
        self.device_combo["values"] = device_names

        # Set default device if none selected
        if device_names:
            current = self.device_var.get()
            if not current or current not in device_names:
                self.device_var.set(device_names[0])
        else:
            self.device_var.set("")

    def validate_inputs(self) -> bool:
        """Validate user inputs before saving."""
        speaker_id = self.speaker_var.get().strip()
        if not speaker_id:
            messagebox.showwarning(
                "Invalid Input", "Please enter a Speaker ID.", parent=self.dialog
            )
            self.speaker_input.focus_set()
            return False

        try:
            validate_component(speaker_id)
        except ValueError as error:
            messagebox.showwarning("Invalid Speaker ID", str(error), parent=self.dialog)
            return False

        folder_path = Path(self.folder_var.get())
        if not folder_path.exists():
            messagebox.showwarning(
                "Invalid Folder",
                "The selected output folder does not exist.",
                parent=self.dialog,
            )
            return False

        if not self.device_var.get():
            messagebox.showwarning(
                "No Device Selected",
                "Please select an audio input device.",
                parent=self.dialog,
            )
            self.device_combo.focus_set()
            return False

        return True

    def on_ok(self) -> None:
        """Handle OK button click."""
        if not self.validate_inputs():
            return

        self.result = {
            "speaker_id": self.speaker_var.get().strip(),
            "speaker_dialect": self.dialect_var.get(),
            "output_folder": self.folder_var.get(),
            "device": self.device_var.get(),
            "input_file": self.file_var.get(),
            "purpose": self.purpose_var.get(),
            "sync_profile": self.profile_var.get().strip(),
        }
        self.dialog.destroy()

    def on_cancel(self) -> None:
        """Handle Cancel button click."""
        self.result = None
        self.dialog.destroy()

    def show(self) -> dict | None:
        """Show dialog and return result."""
        self.dialog.wait_window()
        return self.result
