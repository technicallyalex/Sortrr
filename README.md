# ![Sortrr](branding/sortrr-lockup.svg)

Sortrr identifies movies and TV episodes and organizes them for Plex, Jellyfin, and Emby. It runs locally on Windows.

> **Release Candidate 3.** Sortrr is still in testing. Use a small set of test files or a backed-up library before moving, renaming, or cleaning up media.

[Download the Windows release](https://github.com/technicallyalex/Sortrr/releases/tag/v1.0.0-rc.3)

## Features

- Identify files using TMDb and TVmaze. Review uncertain matches with video previews or enter a match manually.
- Copy or move files using media server presets. Rename media and carry matching subtitles along.
- Preserve bonus videos in extras folders and review their movie or show associations.
- Track scanning with overall progress and per-file queued and identifying indicators.
- Follow Windows appearance or choose light or dark mode, with a browser-style title strip and dedicated window controls.
- Check for updates in Settings and install verified updates automatically. See cache size and choose its storage folder.
- Review source cleanup, handle rejected files, and save your place between sessions.
- Search change history by file name or path and restore a file to its original name and folder.

## Requirements

- 64-bit Windows. The portable build includes Python, Qt, and FFmpeg.
- Internet access for database lookups. For movies, add a [TMDb API Read Access Token](https://www.themoviedb.org/settings/api) in **Settings → TMDb connection**. TV lookups use TVmaze.

## Quick start

1. Extract the Windows ZIP and open **Sortrr.exe**. Keep the `_internal` folder beside it.
2. In **Source**, choose a media folder and click **Scan files**.
3. In **Review files**, check matches and resolve uncertain results.
4. In **Organize**, choose copy or move and a media server preset. Preview the plan before applying it.
5. Point your media server at the resulting **Movies** and **TV Shows** folders as separate libraries.

## Screenshots

![Review files in dark mode, showing identified movies and TV episodes with thumbnails and match status](docs/screenshots/review-files.png)

<details>
<summary>Organize and Change history</summary>

![Organize in light mode, showing the destination, folder naming preset, and file selection](docs/screenshots/organize.png)

![Change history search showing a file's original path, latest path, and Restore original button](docs/screenshots/change-history.png)

</details>

This product uses the TMDb API but is not endorsed or certified by TMDb. TV data comes from [TVmaze](https://www.tvmaze.com/api) under [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/).
