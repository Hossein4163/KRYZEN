# Home-based primary release — 2026-10-25

Moved the entire packaging directory and all archives from the removable source disk to `/home/kry/Packages/kryzen/packaging`. Prepared portable, sanitized build sources in `/home/kry/Packages/kryzen`; build.sh now accepts versions.env without requiring the original private .env file.

Built and activated 1.1.0-9. The home current-release pointer selects it for user CLI, native window, tray, desktop launcher and autostart. All three service pre-start sync commands use the home CLI through user service overrides. Missing primary selections fail explicitly instead of falling back to old system code. Existing sync downgrade protection remains active.

Validation: six packaging regressions passed (including every launcher's primary/invalid-selection behavior), scripts parse, package built from its home path, actual engine restart and forced home-CLI sync retain1.1.0-9. A fresh hash snapshot of all 74 current vault/session files stayed unchanged across forced primary sync and restart; configuration still returns11 agents. One session had been modified before migration (10:15), so the earlier10:07 snapshot was not used to assess this migration. Archive integrity and metadata verified. Installed system package5 is superseded by the user primary entry points, without editing root-owned package files.
