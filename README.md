<div align="center">
  <a href="https://github.com/noxenum/helvox">
    <img src="images/logo.png" alt="Logo" width="80" height="80">
  </a>

  <h3 align="center">Helvox</h3>

  <p align="center">
    A simple recording tool for Swiss German speech data.
  </p>
</div>

## About

![Helvox Screen Shot][ui-screenshot]

**Helvox** is an open-source GUI application for recording audio data in Swiss German dialects.  
It provides a simple and efficient interface for collecting high-quality speech recordings, making it ideal for linguistic research, dataset creation, and dialect analysis.

## Features

- Record and save high-quality audio clips (lossless)
- Tailored for Swiss German dialect data collection
- Built with Python and modern audio libraries
- Cross-platform (developed primarily for Windows)
- Automatic voice activity detection for consistent padding
- Fully local and offline data collection

## Input Format

Example:
```json
[
    {
        "id": "bb9ebca5-09b3-4cad-bad3-65d7f9969589",
        "de": "Hallo Welt.",
        "ch_ag": "Hallo Wält.",
        "ch_be": "Hallo Wäut."
    },
    {
        "id": "6f971113-eac5-4279-a6bb-da736384e9b0",
        "de": "Ich war heute draussen.",
        "ch_ag": "Ich bi hüt dusse gsi.",
        "ch_be": "I bi hüt dussä gsi"
    }
]
```

## Development Setup

To run Helvox locally in development mode:

```bash
pip install -e .
python -m helvox
```

or just simply run:

```bash
helvox
```

This will start the Helvox GUI application.

## Build Instructions (Windows)

To create a standalone executable for Windows:

```bash
pip install -e ".[build]"
pyinstaller windows.spec
```

After building, your packaged application will be available at:

```
dist/Helvox.exe
```

## Build Instructions (macOS)

To create a macOS app bundle:

```bash
pip install -e ".[build]"
pyinstaller macos.spec
```

After building, the packaged application will be available at:

```
dist/Helvox.app
```

## Contributing

Contributions are welcome.
If you’d like to improve Helvox or add new features:

1. Fork this repository
2. Create a new branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "Add my feature"`
4. Push to your fork: `git push origin feature/my-feature`
5. Open a Pull Request

## License

This project is licensed under the **MIT License**.
See the [LICENSE](LICENSE) file for details.

## Acknowledgements

Helvox was built to support data collection and research in Swiss German linguistics (e.g., speech-to-text, text-to-speech).
Special thanks to all contributors and researchers working on dialect preservation and computational linguistics.

<!-- MARKDOWN LINKS & IMAGES -->
[ui-screenshot]: images/screenshot.png

## Wonderful recording review integration

This working copy adds a local post-recording technical GOOD/BAD judge and optional
sync to the private Helvox Recording Review app. The upstream source is pinned at
`c0f9f21a440a14613d1e103ea59a21abe2a40529`.

In Settings → Quality & Sync, choose `reference` for Swiss TTS reference candidates
(5–10.5 seconds) or `dataset` for individual TTS chunks (0.3–60 seconds). The 8–10
second evaluator range is a starting point, not an acoustic optimum. Choose complete
scripts; never rush or cut words to fit. Read frozen visible SOSG output with native
pronunciation. Never speak a dialect-conditioning prefix or insert forced pauses at
independent TTS-request boundaries when recording a grouped reference.

After stopping, BAD means re-record for a concrete technical defect: invalid mono
audio, unsuitable duration, capture errors, clipping, silence/very low RMS or no
sustained detected speech. Noise estimates, low levels and possible cut edges are
listening warnings. GOOD means these checks passed; it does not certify transcript,
native dialect, one speaker, clean endings, background noise or reference quality.
Preview the raw and trimmed take, then confirm the listening checklist before saving.
Thresholds are versioned (`swiss-reference-v1`) and need calibration against labelled
native recordings. ASR errors are not automatically treated as misread words.

Every attempt is preserved under `<output>/<speaker>/takes/<recording-uuid>/`, including
raw.wav, audio.wav, take.json and an optional sync.json receipt. The original accepted
FLAC dataset remains compatible. Do not edit immutable audio/transcripts after capture.
A revised reading gets a new take. Capture errors cannot be fixed by automatic trim.

Sync is disabled until a Wonderful CLI profile is explicitly configured. For this
project use your authorized `swiss-german` profile. Sync transfers rejected attempts
as well as accepted ones. It uses the authenticated wful CLI; no API key is stored in
Helvox settings. Failed uploads remain local and can be retried after restart:

```sh
pip install -e '.[dev]'
helvox
helvox-sync /path/to/recordings --profile swiss-german
```

The admin app shows date, speaker ID, dialect, script, technical reasons and metrics,
raw/trimmed playback and independent listening approval or retake instructions.
It is restricted; recorders see their own takes and administrators review across
speakers. Sync receipts assume you keep the same Wonderful identity for a profile.
If that profile is repointed or signed in as another person, use a new profile name.

Import datasets from the verified bank with `scripts/create_recording_dataset.py`.
Default exports 400 grouped readouts; `--individual-chunks` exports 800 requests for
dataset collection. These are exact synthesis-returned text, not word-to-acoustic-batch
alignment or a production-call corpus. Native transcript approval remains required.

Checks: `pytest`, focused `ruff check`, and `black --check` on changed files.
There is no claim that this workflow improves live-call latency or clone quality.

The uploader mints a signed-in, expiring app token through the selected wful profile. Tokens are never written to take metadata or receipts. Long WAVs upload in bounded parts without resampling; finalization verifies original hashes. Interrupted uploads remain locally retryable. Private staged parts may remain until storage cleanup.

### Bidirectional live feedback

With a configured profile, Helvox opens an authenticated Wonderful WebSocket.
New takes push invalidations to the review app; saved admin decisions flow back
into a separate `review.json` beside the local take and into the recorder status.
Reconnection rereads current decisions and retries queued uploads. There are no
periodic server queries. Tk's local queue drain and socket shutdown timeout are
local thread coordination, not server polling. Original audio/transcripts stay
immutable. Run `helvox-live /path/to/recordings --profile swiss-german` to keep
feedback connected independently of the recorder. Restart the recorder after
installing this version to activate its built-in live connection.
