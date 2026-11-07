# Sortrr

Sortrr is a local desktop app that identifies movies and TV episodes and organizes them for Plex, Jellyfin, and Emby. It can copy files to a library or move them in place. Change history records original paths and lets you restore a file after several moves or renames.

## Run the Windows app

Extract the entire Windows x64 package and open **Sortrr.exe**. Keep the `_internal` folder next to the executable. The package includes Python, Qt, FFmpeg, and ffprobe and opens without a terminal.

The packaged app stores settings, credentials, match history, saved progress, and logs in `%LOCALAPPDATA%\Sortrr`. A source checkout uses its own `data/` folder. These folders are referred to below as the app data directory.

## Develop and build

Sortrr uses Python and Qt Quick via PySide6. The Windows build was tested with Python 3.14 x64. From the repository root in PowerShell, run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\pythonw.exe .\Start-Sortrr.pyw
```

Put FFmpeg and ffprobe on PATH to enable thumbnails, runtime checks, and media-based tests when running from source.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To build the portable release, install PyInstaller and use FFmpeg and ffprobe from the same Windows distribution. Keep that distribution's `LICENSE` and `README.txt` alongside its `bin` folder so the build can include the required notices.

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe packaging/build_windows.py
```

The build writes an unpacked app to `dist/Sortrr/` and an archive to `dist/Sortrr-Windows-x64.zip`. The source lives in the Python modules and `ui/`. The build script and its packaging hooks live in `packaging/`.

## Organize a library

1. In **Source**, choose a media folder and click **Scan files**. Clear database matches are selected automatically.
2. In **Review files**, use **Needs review** to find uncertain matches. Open a row or start **Review unmatched** to search and confirm matches with a video preview. Filters, sorting, runtime checks and selection actions are available here.
3. In **Organize**, choose the destination, naming preset and which ready files to include. Click **Preview** to see each planned path, then confirm the copy or move. **Source cleanup** and **Change history** are also on this screen.

Movies use Movies/Title (Year)/Title (Year).ext. TV uses TV Shows/Title (Year)/Season 01/Title (Year) - S01E01.ext. Point Plex, Jellyfin or Emby at the corresponding Movies and TV Shows folders as separate libraries. Matching external subtitles (including language suffixes and paired SUB/IDX) follow the media.

Identification uses filenames, not video fingerprinting. TV requires S01E01 or 1x01 numbering; date-based and multi-episode names are held for safety. Music, anime absolute numbering, disc folders and automatic watching are outside this version's scope. Multiple versions with identical output names are skipped rather than overwritten.

Movie metadata defaults to **TMDb**. Open **Settings → TMDb connection** and enter an API Read Access Token once. Movies require this connection. TV metadata uses [TVmaze](https://www.tvmaze.com/api), which does not need a token (CC BY-SA, https://creativecommons.org/licenses/by-sa/4.0/). Only metadata requests go online; Sortrr reads and plays media locally. API responses are cached for seven days. Database requests use shared per-provider limits with retries on rate limits. The response cache and file change history stay in the app data directory.

Undo last copy removes only files whose hashes still match that run's journal; originals and modified copies remain. A failed batch can contain completed copies: those are journaled and undoable. If power is lost during a copy, an intent-only partial file may remain; inspect the journal and remove it manually before retrying. Keep journals while you may need undo. Copying requires space for the entire organized library and may take time because both sides are verified.

## Default movie database: TMDb

Sortrr uses https://developer.themoviedb.org/reference/search-movie with the API Read Access Token in an Authorization header. Get the token at https://www.themoviedb.org/settings/api and paste it into the **TMDb connection** window. Use the API Read Access Token. Sortrr stores it as plain text in `tmdb-token.txt` in the app data directory.

Without a working TMDb token, Sortrr still lists movies for manual review and reuses saved matches. Connect TMDb and scan again to look up those movies online. TVmaze lookup continues separately.

This product uses the TMDb API but is not endorsed or certified by TMDb. Artwork shown in the review wizard is cached locally. Movie identification depends on titles, release years and database coverage; uncertain results remain available for review.

## Live results and in-place organization

Scan results appear as each lookup finishes, including uncertain matches and lookup errors. Folder and mode controls are locked during processing.

Choose **Move within the source folder** in **Organize** to organize directly inside your selected media folder. No separate library destination is required. Files and matching subtitles are renamed/moved into Movies and TV Shows subfolders without duplicating their contents. Existing destination files are never overwritten. Already organized files are left alone on later scans. Copy mode remains the default and keeps the originals.

Open **Organize → Change history** to browse recorded operations by date and see the original and destination paths. Check individual changes and choose **Revert selected**, or choose **Revert operation** to restore the entire run. Older Sortrr operation journals also appear here.

Search by any recorded file name or path to find a file across all operations. **Restore original** previews the original and latest recorded paths and reverses the file's recorded moves and renames together. Copies are tracked separately. Sortrr removes a verified copy only when its original is present and unchanged. If a path in the restore sequence is occupied or the file was modified, Sortrr leaves it in place.

Moves, renames, archived files, and removed source folders return to their original paths when possible. Reverting a copy removes the unchanged copy created by Sortrr. Edited files and occupied paths are preserved, and a newer operation affecting the same path must be reverted first. Successful reversals stay marked in the history after Sortrr restarts. Recycled files are listed with instructions to restore them through the Windows Recycle Bin. Empty destination folders may remain.

## Remembered files

Sortrr automatically stores file history in `history.sqlite3` in the app data directory. No setup is needed. Repeat scans display saved decisions immediately with a `(remembered)` status and report the number reused. Confirmed matches, corrected searches and manual skips survive application restarts. You can still review a remembered row to choose a different match.

History checks the resolved file path, byte size and modification time; changed files are identified again. Recognized copy and move destinations are saved too, so in-place sorting does not require another lookup after renaming. Previously copied files are excluded from ready files only while their source/subtitle set and all recorded outputs remain unchanged. Missing outputs, new subtitles, a changed destination or undo make the original eligible again. A manually changed match also gets a new destination preview.

Unmatched or uncertain results are retried after 24 hours, or immediately when switching movie providers. Network errors are not retained as completed identifications. Existing online-response caching remains separate. File history uses timestamps rather than hashing every video on every scan; content changed while deliberately preserving both size and timestamp will not invalidate the entry. Copy/move operations retain their existing integrity checks.

## Correcting or resetting saved matches

Select one or more rows and choose **Re-identify** to discard their saved matches (including related original/organized-path aliases), parse their current filenames again, and request fresh database results. Both the in-memory and disk response caches are bypassed for those lookups. Results update as each file finishes; failed lookups leave no old match selected. Other files keep their saved decisions. For a misleading filename, use **Review** or **View match** to search a corrected title and choose the right result; **Search** also requests fresh results.

**Clear identification cache** asks for confirmation, then clears all saved matches, skips, processed-file history, and cached online responses. Current rows are reset to **Not identified**; use **Scan again** to rebuild results. Media files, folder settings, the TMDB token and undo journals remain intact. Neither action moves or copies media by itself.

## Parallel identification

Scans and selected re-identification use up to 12 concurrent workers, with at most 24 unfinished jobs queued. Files appear as they are found and update as each identification finishes, even when an earlier lookup is slow. Remembered files reuse their existing history.

Identical requests share a single lookup. The response cache uses atomic file replacement; history uses short SQLite transactions with WAL enabled. Fresh-lookups are isolated per worker. TMDb request starts are spaced by 0.04 seconds (up to 25/second), TVmaze by 0.51 seconds, independently of worker count. HTTP 429 responses apply a shared provider cooldown respecting Retry-After, with up to three attempts. TMDb authentication failures stop additional movie requests while scanning continues for manual review. No concurrency setup is needed.

Provider references: https://developer.themoviedb.org/docs/rate-limiting and https://www.tvmaze.com/api#rate-limiting.

## Movie and show sorting

Open **Filters and sort** in **Review files** to choose a media type, runtime filter or sort order. You can sort by source name, title, type, year, season, episode or status. Episode and season sorting are numeric. **Organize** lets you choose all ready files, the ready files in the current review view, or only selected ready files.

**Customize** under folder and file names sets movie and show structures independently and displays examples before applying:

- Movies: Title (Year), Year / Title (Year), A-Z / Title (Year), or Year - Title.
- TV shows: Show / Season / Episode, or Show / Episode without season subfolders.

Standard Title (Year) movie folders and Show / Season TV folders remain the defaults. Media filenames retain canonical titles, years and SxxExx episode numbering in every layout. Alphabetic movie grouping uses A-Z with # for numeric/other initials; movies without a release year use Unknown Year in year grouping. Shows retain individual folders directly under TV Shows. Keep each media server's library paths consistent with your chosen grouping.

Applying a layout only updates previews and readiness; files move/copy when you choose Organize. Folder layout choices, view sorting, direction and media filter are saved in `settings.json` in the app data directory and restored on restart. History tracks completed outputs separately for each layout, so changing layouts does not require another database lookup. Subtitles, collision protection and undo apply to every layout.

Naming references: https://jellyfin.org/docs/general/server/media/movies/ and https://jellyfin.org/docs/general/server/media/shows/.

## Media server presets

Choose a **Media server** preset in **Organize**. Every server preset uses individual movie folders and show/season folders directly beneath separate Movies and TV Shows roots. The universal preset retains the shared layout without identifiers. Custom year/A-Z grouping remains available; changing individual controls marks the configuration Custom.

| Preset | Movie folder and matching file stem | Show folder when a TVDB ID is available |
| --- | --- | --- |
| Universal | Example Movie (2020) | Example Show (2018) |
| Plex | Example Movie (2020) {tmdb-12345} | Example Show (2018) {tvdb-54321} |
| Jellyfin | Example Movie (2020) [tmdbid-12345] | Example Show (2018) [tvdbid-54321] |
| Emby | Example Movie (2020) [tmdbid=12345] | Example Show (2018) [tvdbid=54321] |

Show episodes keep title/year and SxxExx numbering inside zero-padded Season folders, including Season 00 for numbered specials. Provider tags are placed in show folders; movie tags appear in both folder and filename. The identifiers in examples are illustrative.

Movie IDs come from the selected TMDb match. Show IDs come from TVmaze's external TVDB or IMDb fields, never from TVmaze's own numeric ID. Missing or invalid identifiers are omitted. Older cached show matches may lack external IDs; Re-identify selected refreshes their metadata. Choosing a preset previews changes and saves preferences; Organize performs the actual copy/move. No server settings are modified.

Official sources reviewed November 4, 2026 (also linked in the dialog):

- Plex: [movie naming](https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/) and [TV naming](https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/).
- Jellyfin: [movies](https://jellyfin.org/docs/general/server/media/movies/), [shows](https://jellyfin.org/docs/general/server/media/shows/) and [provider identifier syntax](https://jellyfin.org/docs/general/server/metadata/identifiers/).
- Emby: [movie naming](https://emby.media/support/articles/Movie-Naming.html) and [TV naming](https://emby.media/support/articles/TV-Naming.html).

These presets implement naming and folder conventions for the movie and numbered-episode files Sortrr already supports. They do not add disc-folder, extras, multi-episode-file or alternate episode-order processing.

## Rename files without changing folders

Select identified rows and choose **Rename in place**. The preview lists old and new names for the media and same-stem subtitles, NFO metadata, and named artwork (such as filename-poster.jpg). Names use the current server preset and episode numbering. Shared assets such as poster.jpg or tvshow.nfo stay in place. **Rename files** applies the reviewed names within each current folder; it does not copy content or reorganize the folder tree.

Changed sources and existing destination names are skipped. A conflict in a companion filename prevents that media group from being renamed. **Undo last operation** restores original names when files are unchanged and the old paths are available.

## Clean source folders

Choose **Review source cleanup** to inventory the selected media folder and review cleanup candidates. This works without identifying media first. The destination library, organized Movies/TV Shows subfolders during in-place use, application data, links/junctions, and existing .sortrr-trash recovery folders are excluded.

Only system-generated files (Thumbs.db, desktop.ini, .DS_Store) and checksums (.sfv, .md5, .sha1, .sha256) are preselected. Text documents/links, archives, sample videos, metadata and artwork appear for optional selection. Full media files and subtitles are not offered as junk; sample videos are an explicit optional category. Use the checkboxes in the cleanup preview to choose what to archive.

The preview also lists folders that will be empty after the chosen files are removed. Remove empty folders can be disabled. Cleanup never removes the source root and uses nonrecursive removal of empty directories; files that appear or change after preview are preserved/skipped.

**Archive selected items** moves selected files into .sortrr-trash/<run ID>/ beneath the source folder, retaining their relative paths. This removes clutter from the working folders but does not free disk space. Media scanning ignores recovery storage. No files are permanently deleted by cleanup. **Undo last operation** restores unchanged files and removed empty folders; occupied paths and modified recovery files are preserved. Full skip details are recorded in `run-*.jsonl` in the app data directory. Keep recovery storage and journals for as long as undo may be needed. Undo can recover completed moves even if the final journal append was interrupted.

## Automatic actions after successful sorting

The main window has two saved options:

- **Rename media to match** (on by default) gives the sorted media and matching subtitles/metadata/artwork their preset names as part of organizing. Turn it off to preserve original filenames inside the chosen folder layout. The separate Rename selected command still explicitly renames files.
- **Clean source folders after sorting** (off by default) automatically archives recommended junk and removes empty source folders once sorting has succeeded. No extra cleanup dialog is needed after the sort confirmation.

Automatic cleanup uses a snapshot taken before sorting and only removes system junk/checksums from directories whose media completed successfully. Failed or unselected media in the same directory prevents cleanup there. Notes, archives, samples, metadata and artwork remain unless handled through manual cleanup. Unrelated empty directories, destination libraries, application data and recovery storage are protected. Changed files are skipped. Copies retain original media; moving can leave empty source folders that are then removed.

Sorting and its automatic cleanup share one journal: Undo last operation reverses the combined run in reverse order. Cleaned files remain in .sortrr-trash for recovery and still use disk space.

## Resolve unmatched files wizard

After a scan, choose **Review unmatched**. The wizard follows unresolved files in the current movie/show filter and display order. It includes missing matches, ambiguous results, lookup failures and files requiring review.

The panel shows one file at a time with its full path, runtime, size, video resolution, codec and audio track count when available. Select a timeline thumbnail to jump to that point in the player. Review the suggested database entry or choose **Search instead** to find another one. The search also lets you correct the media type, season and episode.

**Assign match** saves the selected entry and advances to the next unmatched file. **Skip** advances and leaves the file for a later review. **Back** and **Next** browse the current queue without saving a decision. Database settings are available inside the wizard.

The completion page reports resolved and remaining files. The wizard does not move or rename media; use Organize when ready. Unsupported episode patterns must be corrected and rescanned before confirming a match. Changed/missing files cannot be assigned a stale match.

## Create a manual entry

Open a file in the review wizard and choose **Create manual entry**. Enter the title and an optional release year. For a TV episode, enter the series title, season, and episode number. Use season 0 for specials. The wizard previews the destination using your current folder layout.

**Save manual entry** remembers the match and makes the file ready to organize. The entry is stored locally without a provider ID. Use **Organize** to preview and confirm the file operation.

## Pause and resume

Choose **Save and close** in the wizard to save your place, search drafts, and deferred files. Use **Save progress** in Review files or Organize to save the current view, selection, and organize settings. The latest saved progress is available through **Resume** in Source after restarting. Resume checks the saved files and leaves out any that changed or went missing. An organize plan still needs to be previewed and confirmed before files move.

The database info panel shows the selected entry’s poster and metadata beside the local video preview.

## Reject files

**Reject** marks the current file and advances to the next unmatched item. Sortrr remembers the decision across scans. To change it, open the **Rejected** tab, select **View reject**, and choose **Unmark reject**.

Under **Organize → Rejected files**, leave rejects in place, move them to a folder, or send them to the Recycle Bin. The plan lists the affected files and their destinations. Use **Rejected files only** to run a plan that handles only rejects. Folder moves keep the relative paths under the source and can be reversed with **Undo last operation**. For recycled files, use Restore in the Windows Recycle Bin. Use a reject folder for files on network shares.

## Local video thumbnails and previews

The Windows executable includes FFmpeg and ffprobe for timeline thumbnails and runtime checks. The source launcher looks for those tools on PATH. Missing tools or unreadable files show a preview-unavailable message.

The scanned-file list includes a **Preview** thumbnail column. Frames load in the background as rows become visible, including unresolved files. Scroll to load further rows. This avoids decoding an entire large library before it can be used. Hover over a thumbnail and move horizontally across it to scrub through a larger popup preview; move away to dismiss it.

The **Review unmatched** wizard plays local video and audio in the same window. Use Play/Pause, the timeline, audio track selector, volume and mute to inspect a file. Use **Output** to choose speakers or headphones directly. Sortrr uses the Windows default unless you select a device, and it remembers your choice. Closing the wizard or advancing to the next file stops playback.

Preview frames and probe information are cached under `previews/` in the app data directory using the source path, size and modification time. Changed files get fresh previews. Each source fingerprint retains at most 80 cached seek frames. There are two background thumbnail workers, a bounded request queue, debounced hover/seek requests and a single latest playback frame in memory. Stale results are ignored when changing files or rescanning. Preview processes close their source handles before rename, sort, cleanup and undo operations; visible thumbnails resume afterward. Existing Clear cache resets identification history and API responses; preview storage is separate.

## Wizard audio and database entry information

Below the preview, the highlighted database result shows its title/original title, release date, runtime, genres, rating/vote count, tagline and synopsis when available. Selecting another result updates this panel without blocking navigation or playback. Full details use the selected TMDb ID, the existing token, shared rate limiting and response cache. Late responses from earlier selections are ignored. Open database entry links to the actual source record.

For shows identified through TVmaze, TMDb details are used only when a known TVDB/IMDb external ID maps to exactly one TMDb series. Otherwise the panel displays TVmaze information with that source named. Missing credentials or network errors leave available search-result information visible with an explanatory message.

API references: https://developer.themoviedb.org/reference/movie-details, https://developer.themoviedb.org/reference/tv-series-details, https://developer.themoviedb.org/reference/find-by-id.


The wizard shows the movie or show poster next to the database details. It uses TMDb artwork when the selected entry has a TMDb record and can show TVmaze artwork for other show matches.

## Check file runtimes

After scanning, select identified files and click **Check runtimes**. With nothing selected, Sortrr checks all identified files in the current view. The length filter shows **Matches**, **Differs**, **Unknown**, or **Unchecked**. Hover over a row's length result for the local and database lengths and the difference.

Sortrr reads the file duration with ffprobe and compares it with the database's movie runtime or exact season and episode runtime. It allows a difference of two minutes or 5%, whichever is larger. Missing runtimes and unreadable files show as **Unknown**. Results are saved with the match when both runtimes are available. A different runtime can flag a partial file, a different cut, or a questionable match; it does not change the chosen match. The wizard also compares the runtime of the highlighted result.
