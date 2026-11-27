# Sortrr Release Candidate 4 - local test build

Sortrr is still in testing. Try a small set of test files or a backed-up library before moving, renaming, or cleaning up media.

- Opt in to Start with Windows, and launch directly into the system tray. Enabling Windows startup defaults to quiet tray launch; both options remain adjustable.
- Settings now uses two columns: application/startup controls on the left, watch folders and cache storage on the right.
- Watch-folder rows show separate Waiting, Queued, Scanning, and Ready to review counts, updated as individual files finish. The settling message now reads "Waiting for files to settle".
- Add multiple watch folders in Settings. Sortrr checks subfolders for new and changed media every 15 seconds, and waits for files to stay unchanged for 60 seconds before identifying them.
- Keep Sortrr running in the Windows system tray when the window closes. Open it again from the tray or by launching the EXE.
- Get notifications when watched files are scanned and ready for review. Tray controls include pause/resume, check now, review new files, check for updates, and quit.
- Preserve the active review while background scans run. Use Review on a watched folder to load its files with remembered matches.
- Watch settings, processed-file fingerprints, and pending counts persist between sessions. Pause individual folders or all monitoring, or remove folders from the list.
- Scanning is non-destructive. Copying, moving, renaming, cleanup, and rejects still use the existing Organize workflow.

Extract the entire Windows ZIP and launch Sortrr.exe. Keep the adjacent files and folders together. Python and FFmpeg are included.

Validation: 163 automated tests passed, plus isolated watch-folder and tray workflow checks covering two roots, changed files, saved state, review handoff, and relaunching the existing instance.

This test build is local and has not been published to GitHub.
