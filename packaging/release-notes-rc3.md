# Sortrr Release Candidate 3

Sortrr is still in testing. Try a small set of test files or a backed-up library before moving, renaming, or cleaning up media.

- Combined the app header and title bar, with themed window controls and no empty strip above the app.
- Added a Check for updates button in Settings and automatic installation of verified updates, with rollback if the new app cannot start.
- Added cache size reporting and a native folder picker to move the cache. Settings, saved matches, review progress, and change history stay in the app data folder.
- Included cached previews when clearing the cache.

## Windows

Extract the entire ZIP and launch Sortrr.exe. Keep the adjacent files and folders together. Python and FFmpeg are included.

RC2 users need to download this release manually once. Later updates can be installed through Settings.

Settings and change history are kept in %LOCALAPPDATA%\Sortrr.

## Validation

146 automated tests passed, plus UI checks for the unified header, Settings, updates, cache relocation, scan progress, and related media. The portable package was also checked for startup and bundled dependencies.

This candidate is prepared locally for review and has not been published.
