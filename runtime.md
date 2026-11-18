# Runtime and portability

The source template is in `assets/template`. It is copied to a separate writable runtime before use. No private video project, user account directory, or particular drive letter is required.

The default runtime directory is `.kinetic-tech-runtime` **next to the repository**. Override it with `KINETIC_RUNTIME_HOME` or `--work`. Keep the runtime outside the repository so dependency caches and generated media cannot accidentally become source files.

## Requirements

- Python 3.12 or newer. The declared NumPy/SciPy versions require Python 3.12; the upstream adapter's broader declaration is not sufficient.
- Node.js 22 or newer.
- FFmpeg and ffprobe. FFmpeg must provide libx264, AAC, colorspace, overlay and alimiter.
- An installed Chrome/Chromium or Edge capable of running headless.
- Local process execution and writable runtime/output directories. Bootstrap may require network access for declared dependencies.

Use an actual Python interpreter. On Windows, the `python` command can be a Microsoft Store alias; if it does not run Python, use the installed interpreter path or the Python launcher.

```text
python scripts/runtime.py doctor
python scripts/runtime.py bootstrap
python scripts/runtime.py doctor
```

`doctor` prints JSON and exits with code 0 only when the selected tools, pinned Python packages, matching template copy and locked Playwright dependency are ready. Before the first bootstrap it normally exits 1. It checks the Chrome executable's presence; browser launch and rendering are exercised by preview/the demo, not inferred from file existence.

Override tools before the subcommand:

```text
python scripts/runtime.py --work /path/to/runtime --python /path/to/python --node /path/to/node --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe --chrome /path/to/chrome bootstrap
```

Corresponding environment variables are `KINETIC_PYTHON`, `KINETIC_NODE`, `KINETIC_FFMPEG`, `KINETIC_FFPROBE`, and `CHROME`. Otherwise discovery uses the existing runtime configuration, the current interpreter, PATH and ordinary browser installation locations. There is no private-project fallback. Windows, macOS and Linux path discovery is provided; only the Windows execution path has been exercised during this release's local validation.

## Dependency setup

`requirements.txt` pins direct Python dependencies; bootstrap reuses an environment that matches exactly, or creates `runtime/python` and installs the requirements there. System Python, Node, FFmpeg and browsers are not downloaded by this helper. Missing system tools produce a concrete error.

Playwright is pinned by `assets/template/package-lock.json`. Bootstrap downloads the exact package URL, verifies its SHA512 integrity, and extracts it without running lifecycle scripts. If a matching installed dependency already exists, explicitly set `KINETIC_PLAYWRIGHT_ROOT` to a directory containing `node_modules/playwright-core`. `bootstrap --offline` permits only already available dependencies. This is an optional optimization, not a dependency on the author's machine.

TEMP/TMP, pip/npm caches and browser temporary files are placed under the selected runtime. `runtime.json` records resolved executable paths for that machine. It is generated locally and must not be committed or copied as a portable configuration.

## Native stages

Prefer the unified workflow entry described in the repository README. These lower-level commands are useful for previews, diagnosis and explicitly resuming a stage:

```text
python scripts/runtime.py template plan --input /path/to/user.json --out /path/to/plan.json
python scripts/runtime.py template prepare --input /path/to/user.json --out /path/to/instance
python scripts/runtime.py template preview --instance /path/to/instance --out /path/to/preview.png --time 3
python scripts/runtime.py template render --instance /path/to/instance --out /path/to/silent.mp4
```

Each command uses the real template adapter. Existing output targets are preserved. `render` produces a silent master, a native audio intermediate and the native effects stems. Complete delivery then runs the final mixer with the selected BGM and cover; the intermediate is not automatically a complete delivery.

Template and prepared-instance digests protect source consistency. If the template working copy is edited, bootstrap/template commands refuse to silently reuse it; use a new runtime or deliberately maintain that fork. A prepared instance from another template revision must be run by the matching revision or prepared again. Changing Python/FFmpeg/browser versions may change encoded bytes even when the visual style is equivalent.

## Bundled template changes

The upstream public package is MotionGit #385712, kinetic-tech 0.2.7-open-beta. Original `.motion` SHA256: `472a95af35f8e0c09c0f7dc2ca0992b7c9a3405c5aa8063730c347fc4e015c21`.

- Three adapter resource paths use `.as_posix()` for Windows browser URLs.
- Renderer progress is reported every 120 frames; scene timing and encoding settings are unchanged.
- Topic-specific personal example patches are not bundled.

Upstream integrity records remain upstream records, not signatures for this local adaptation. Code, fonts and brand assets retain the separate terms in `assets/template/licenses/`.

## Release validation scope

On Windows, release validation created a new Python virtual environment from an interpreter that did not contain the required packages, downloaded and installed all declared Python dependencies, downloaded the locked Playwright tarball and verified its SHA512, then passed doctor, actual audio-library operations and a native browser preview. The test reused installed Node, FFmpeg/ffprobe and Chrome. It therefore verifies clean dependency setup, not installation on an otherwise empty operating system. Network availability and local execution permissions remain prerequisites.
