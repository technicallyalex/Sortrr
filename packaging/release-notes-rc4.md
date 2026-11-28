# Sortrr Release Candidate 4

Sortrr is still in testing. Try a small set of test files or a backed-up library before moving, renaming, or cleaning up media.

- Watch multiple folders for new or changed media. Checks run every 15 seconds, with 30 seconds of observed stability before identification.
- See separate Waiting, Queued, Scanning, and Ready to review counts. Queued work no longer appears stuck settling; files in use or unreadable files show a separate reason.
- Keep Sortrr in the Windows system tray, receive notifications, pause monitoring, and review new files. Relaunching opens the existing instance.
- Opt in to Start with Windows and quiet tray launch. Settings now uses two columns.
- Keep your active review intact while background scans run. Watch settings, processed-file fingerprints, and review counts persist across restarts. Organizing remains manual.

## Windows

Extract the entire ZIP and launch Sortrr.exe. Keep the adjacent files and folders together. Python and FFmpeg are included.

Existing RC3 users can use **Settings → Check for updates**. RC1 and RC2 users need to download the ZIP manually. If testing another portable copy, quit the existing tray instance first.

## Validation

167 automated tests passed, plus watch-folder, tray, startup, and live-counter workflow checks. Read-only checks passed on 48 unprocessed NAS files, and the standalone Windows package passed startup and bundled dependency checks.
