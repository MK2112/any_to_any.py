# Privacy Policy

any_to_any.py was built as a local-first media converter.<br>
The following explains what data the project's code processes, stores, and (if at all) transmits.

---

**TL;DR:**
- For CLI and GUI: Your media files are processed on your own machine or
- For web interface: Your media files are processed on the machine running `web_to_any.py` (default: localhost)
- No data is ever sent to the project maintainers, there exist no accounts, no telemetry, no metadata, no analytics, no tracking, no ads
- The only outbound network requests are a version check (only for GUI) and a GitHub button widget (only in web interface), both detailed below

---

## Where Your Files Go

### Command Line Interface / Graphical User Interface

Input files are read from your disk and converted output is written to the directory you choose
(default is the working directory). Nothing leaves your machine.

### Web Interface

Files are uploaded to the machine running `web_to_any.py`.
By default the server binds to `127.0.0.1` (localhost), so, in this setting, uploads never leave your machine.

If you set `Any2Any_HOST` to another address, uploaded files travel over the network to that host.<br>
This is intended for self-hosting only, see [SECURITY.md](SECURITY.md) before exposing the web interface.

### Docker

The container publishes port `5000` on the host and receives uploaded files through it. Web job
directories (`uploads_<job_id>/`, `converted_<job_id>/`) are created inside the container and
disappear when it is removed. The mounted `uploads/`, `converted/` and `out/` volumes are
available for files you produce or keep on the host.

## Data Stored on Disk

### GUI Settings

A config file is created by the GUI executable:
- Windows: `C:\Users\<username>\.any_to_any_gui_settings.json`
- Linux: `~/.any_to_any_gui_settings.json`

The config file stores two values:
- `last_dir`: the last directory you browsed to
- `locale`: your selected interface language

### Metadata

- With `--preserve-meta` or `--add-tag`, extracted metadata (ID3 tags, EXIF data, document properties) is written as JSON to `<output_directory>/.metadata/<name>.metadata.json`
- With `--strip-meta`, metadata is removed from output files for privacy

### Web Server Storage

While a job runs, `uploads_<job_id>/` and `converted_<job_id>/` directories are created next to `web_to_any.py`:
- After the conversion finishes, uploads are deleted immediately
- Converted files are kept until you download them, or are removed after a 15 minute retention period (`JOB_RETENTION_SECONDS`)
- Abandoned job directories left by a server restart are swept automatically with a next cleanup cycle

### Temporary Files

- Archives made available for download are `.zip` files temporarily placed in the system temp directory, which get deleted right after getting sent
- While conversion libraries may create their own temporary files during processing, they are not retained after a job completes

### Web Sessions

The web interface uses a signed session cookie. It contains only:
- a random job-owner id (so you can only ever access your own jobs)
- your chosen interface language
- a CSRF token

The cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` when served over `HTTPS`. The web frontend
additionally uses client-side `sessionStorage` to remember that a language was already selected.
At the host, rate limiting measures keep IP addresses only in RAM, capped at 10,000 entries.

## Network Activity

### GUI Executable Update Check

On startup, the GUI executable sends one `HTTPS` request to the following GitHub Releases API:
`https://api.github.com/repos/MK2112/any_to_any.py/releases/latest`

This request carries no user data beyond what any `HTTP` request includes (IP address and User-Agent).
It only serves to check and inform the user on whether a newer version of the application exists.

### Web UI GitHub Widget

The web interface loads `https://buttons.github.io/buttons.js` (the official GitHub star/fork buttons).
Your browser requests this script directly from GitHub when you open the page, which exposes your IP address to GitHub,
subject to [GitHub's privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement).

### Everything Else

- The CLI and all parts of the core conversion pipelines make no network requests
- `FFmpeg` runs locally (installed for GUI as system binary or the bundled `imageio-ffmpeg` binary for CLI/Web)
- The web server itself makes no outbound requests

## Third-Party Components

any_to_any.py relies on external libraries and tools (FFmpeg, MoviePy, Pillow, PyMuPDF, Flask,
PyQt6, and others). Their behavior is outside the control of this project. Refer to their
respective privacy documentation.

## Data Retention and Deletion

- Output files, `.metadata` directories, and the GUI settings file are under your control and can
  be deleted at any time
- Web uploads and converted files are cleaned up automatically as already described above
- The uninstalling of this application leaves only files you explicitly created (outputs, metadata, settings)

## Security

See [SECURITY.md](SECURITY.md) for the security policy, including guidance on processing
untrusted files and on not exposing the web interface publicly.

## Changes to This Policy

This policy may be updated as the project evolves.<br>
Changes are visible in the repository's commit history.

## Contact

For privacy questions, open an issue at https://github.com/MK2112/any_to_any.py/issues.<br>
For security vulnerabilities, follow the reporting process outlined in [SECURITY.md](SECURITY.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).