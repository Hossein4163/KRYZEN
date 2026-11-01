# Configuration loading after restart — 2026-10-25

The backend still returned11 agents,11 mesh configurations and2 projects after reboot. The apparent configuration loss was a client startup failure: user runtime files had been replaced by installed release1.1.0-5 at09:55, restoring the `meshGeometry()` call before `cfg` was populated. The restyled1.1.0-7 archive existed on the external source disk but had not been activated as the service release.

## Durable repair

Added `packaging/activate-user-release.py`. It extracts a built release into the persistent per-user releases directory, updates only `KRYZEN_LIB` in the existing private service settings, backs up those settings, and runs the existing sync with its session/key/job/vault preservation rules. The current activation is `~/.local/share/kryzen/releases/1.1.0-7`; startup no longer relies on the source disk or temporary runtime patches. No agent definitions, credentials, conversation content or project files were rewritten.

The original source disk was unmounted following reboot; it was mounted normally using UDisks and is currently available at `/run/media/kry/Bull Shit2`. Source and package recovery used that mount; live service files are all under the home directory.

## Verification

- Health check reported zero active runs before engine restarts.
- First actual engine restart: configuration11 agents, rendered mesh11 nodes,2 projects and2 resize handles; no page errors.
- Second actual engine restart intentionally invalidated the version stamp to force the same release-copy path that caused the regression. Startup synced1.1.0-7 and retained exact source bytes for HTML, server, Studio, theme and resize code.
- SHA-256 comparison: all74 pre-existing vault and session files unchanged across activation and both restarts.
- Theme and resize routes returned HTTP200. The page reload repopulates configuration and project selection.

The open native window needs F5 to replace its already-loaded old JavaScript. The repaired release remains selected for subsequent starts. Activate a newer package with the same helper when updating the per-user release.
