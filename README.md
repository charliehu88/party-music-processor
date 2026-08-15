
```markdown
# Dance Party Playlist Generator

A Python automation tool for ballroom dance hosts. This tool transforms a local collection of audio files (MP3s, M4As) into a sequence of YouTube-ready MP4 videos.

It automates the DJ process by:
1. **Sequencing:** Alternating tempo and dance category so the floor keeps changing character, and opening and closing the party on a Waltz.
2. **Processing:** Trimming songs to a set length, normalizing volume, and adding fades/silence.
3. **Visualizing:** Generating a 720p video file that displays "NOW PLAYING" and "COMING UP NEXT" metadata for your guests.
4. **Uploading:** Publishing the finished videos to YouTube (Manually or Automatically).

## 📂 Directory Structure

```text
party-music-processor/
├── assets/                # (Not used by default)
├── input_mp3s_m4as/       # Drop your source audio files here
├── dance_videos/          # Optional: dance clips for video backgrounds
├── output_mp4s/           # Generated video files appear here
├── .venv/                 # Python virtual environment
├── NotoSansSC-VariableFont_wght.ttf  # Font for video overlays
├── process.py             # Core processing logic
├── download.py            # Batch downloader tool
├── collect_dance_videos.py # Searches YouTube for dance clips by dance type
├── playlist_2_file.py     # Playlist extractor tool
├── uploader.py            # Automated YouTube uploader
├── speed_adjuster.py      # Utility: Adjusts audio/video speed
├── cutter.py              # Utility: Cuts audio/video to length with a fade out
├── volume_adjuster.py     # Utility: Adjusts audio volume
├── video_splitter.py      # Utility: Splits video files
├── music_identify.py      # Utility: Identifies and renames music files via Shazam
├── split_manual.py        # Utility: Manual splitting utility
├── converter.py           # Utility: Format conversion tool
├── dance_config.json      # Dance styles and weights
├── downloads.txt          # List of links to download
└── requirements.txt       # Python dependencies

```

## 🛠️ Prerequisites

### 1. System Tools (macOS)

You must have `ffmpeg` (for video) and `yt-dlp` (for downloading music) installed.

```bash
brew install ffmpeg yt-dlp rust libsoup
cargo install songrec --no-default-features

```

### 2. Python Environment

Initialize the project dependencies:

```bash
# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Install libraries
pip install -r requirements.txt

```

> **💡 Tip for all tools:** You can view the available arguments and detailed usage for any script in this project by running it with the `-h` or `--help` flag. For example: `python process.py -h`.

## ⬇️ Step 1: Download Music

You can download music individually or in batches.

**Option A: Batch Download (Recommended)**

1. Create a file `downloads.txt` (URL | Name):

```text
[https://youtu.be/xyz123](https://youtu.be/xyz123) | Waltz - Moon River
[https://youtu.be/abc456](https://youtu.be/abc456) | ChaCha - Sway

```

2. Run the downloader:

```bash
python download.py

```

*(Run `python download.py -h` for usage details)*

By default `download.py` extracts audio to MP3. Pass `--download-type mp4` (`-t mp4`) to keep the picture instead, which is how you grab a specific dance video by URL for a `--video-pool`:

```bash
python download.py -l dance_clips.txt -o ./dance_videos -t mp4
```

Audio and video of the same URL are tracked separately in `download_history.log`, so downloading a link as MP3 does not stop you fetching the MP4 later.

**Option B: Extract YouTube Playlist to Downloads List**

If you have a YouTube playlist, use `playlist_2_file.py` to automatically generate a `downloads.txt`-style list with auto-detected dance types:

```bash
python playlist_2_file.py --playlist "https://www.youtube.com/playlist?list=OLAK5uy_..." --file my_playlist.txt
```

This tool analyzes each video's title and description to detect dance types (e.g., "Waltz", "ChaCha", "Viennese Waltz"). It outputs lines in the format: `https://youtu.be/<id> | <Dance Type> - <Title>`

*(Run `python playlist_2_file.py -h` for usage details)*

**Option C: Manual Download**

```bash
yt-dlp -x --audio-format best -o "input_mp3s_m4as/DanceType - SongName.%(ext)s" "YOUTUBE_URL"

```

## 🎵 File Naming Convention

**Crucial:** For the processor to correctly categorize speed (Quick/Slow) and display titles, files must follow this format:
`[Dance Type] - [Song Name].mp3`

**Examples:**

* ✅ `Waltz - Moon River.mp3`
* ✅ `ChaCha - Sway.mp3`
* ✅ `West Coast Swing - The Way You Make Me Feel.mp3`

*Note: The script is case-insensitive. It relies on the "Dance Type" keyword (e.g., "Waltz", "Jive") being present in the filename.*

## 🚀 Step 2: Generate Playlist

Run the processor via command line:

```bash
python process.py --source ./input_mp3s --favorite ./favorites --output ./output_mp4s --count 20

```

*(Run `python process.py -h` to see all available arguments like fade duration, song lengths, etc.)*

The processor prioritizes songs from the `--favorite` directory over the `--source` directory for each dance type. If favorites are available for a type, they are selected first before falling back to source songs. Beyond that, every song in a pool has exactly the same chance of being drawn.

A song often lives in both places. Favorites are scanned first and claim the song, so it keeps its favorite priority and the copy in the general pool is skipped — the same track can never appear twice in one playlist. Matching is by filename only, ignoring the folder, capitalization, extra spaces and file format, so `~/favorites/ABC.mp3` and `input_mp3s_m4as/abc.m4a` count as one song. (A renamed copy such as `ABC copy.mp3` still reads as a different song.)

### Flexible Favorites

The `--favorite` argument is highly flexible. You can provide either:
1.  A path to a directory containing your favorite audio files.
2.  A path to a text file (`.txt`) that lists the full paths to your favorite songs, one per line.

**Example `favorites.txt` file:**
```
# This is a comment and will be ignored
~/music/favorite_songs/"Waltz - A Daisy in December.mp3"
"/Users/charlie/Music/ChaCha - Pata Pata.mp3"
```

**Arguments:**

*   `--source, -s`: Folder containing your MP3s.
*   `--favorite, -f`: Path to a directory of favorite songs OR a text file containing a list of song paths. Favorite songs are prioritized during selection.
*   `--output, -o`: Folder where MP4s will be saved.
*   `--config, -cfg`: Path to the JSON weights file (default: `dance_config.json`).
*   `--count, -c`: Number of songs to generate (default: `20`).
*   `--length-quick`: Max length of full-volume dance music for Quick dances in seconds (default: `150` = 2m 30s).
*   `--length-slow`: Max length of full-volume dance music for Slow dances in seconds (default: `180` = 3m 00s).
*   `--fade`: Fade out duration in seconds (default: `5`). The fade is added *after* the dance length, not taken out of it, so a dance configured for 120s gives dancers a full 120s before the music starts to fade.
*   `--fade-curve`: Shape of the fade (default: `2.0`). Higher values hold near full volume longer and then ease down; `1.0` starts dropping immediately.
*   `--silence`: Silence padding in seconds (default: `6`).
*   `--mp3`: If set, also export processed MP3 files.
*   `--output-mp3`: Folder for processed MP3s (default: `./output_processed_mp3s`).
*   `--video-pool, -v`: Folder of dance clips to play behind each track instead of the static cover. See below.
*   `--intro`: Seconds the full text card stays up before dissolving into the dance video (default: `6.0`, `--video-pool` only).

### 🎬 Dance Video Backgrounds

By default every track is a still cover card. Point `--video-pool` at a folder of dance clips and each track instead:

1.  Opens on the usual **full text card** for `--intro` seconds (default 6).
2.  **Dissolves** over one second into real dance footage for that dance type.
3.  Keeps **"COMING UP NEXT"** on screen in a lower third for the rest of the track.

The next-up block sits at the same place on the card and in the lower third, so it does not move during the dissolve — the "now playing" half fades away and the next-up half simply stays. Over footage it gains a dark scrim and a black outline so it stays readable against bright dresses and spotlights.

```bash
python process.py -s ./input_mp3s -o ./output_mp4s -v ./dance_videos --intro 6
```

Clips use the **same naming convention as the music**, in one flat folder — no subfolders:

```
dance_videos/
├── Waltz - Vienna Opera Ball.mp4
├── Waltz - Blackpool Final.mp4
├── Rumba - World Championship.mp4
└── ChaCha - Showdance.mp4
```

Details worth knowing:

*   **Clips are chained, not looped.** A 95s track backed by 30s clips plays three *different* Waltz clips back to back. Each dance keeps its own shuffled queue that carries across the playlist, so a clip only repeats once the rest of that dance's clips have been used.
*   **Any dance without clips keeps the static cover**, so you can start with footage for just a few dance types and grow the folder over time. A missing folder falls back the same way with a warning.
*   Clips are **cropped to fill** 1280x720 rather than letterboxed, and their own audio is discarded.
*   Clips shorter than 3s, or files with no dance type in the name, are skipped and reported.
*   Rendering real footage is slower than a still image — expect minutes rather than seconds for a full party.

#### Collecting the clips

`collect_dance_videos.py` searches YouTube per dance type and fills the pool with correctly named files. List the dance types you want, one per line:

```text
# Dance Type | Count | Extra search terms (both optional)
Waltz | 6
Rumba | 4
Viennese Waltz | 3 | competition final
ChaCha
```

```bash
python collect_dance_videos.py -l dance_videos.txt -o ./dance_videos --dry-run   # preview
python collect_dance_videos.py -l dance_videos.txt -o ./dance_videos             # download
```

Each clip is saved as `<Dance Type> - <video title>.mp4`, ready for `--video-pool` with no renaming.

*   `--per-dance, -n`: Clips per dance when the list gives no count (default: `5`).
*   `--query, -q`: Search template (default: `{dance} ballroom dance performance`). `{dance}` is replaced with the dance type.
*   `--min-duration` / `--max-duration`: Duration filter in seconds (default: `30`–`900`), which keeps out thumbnails and two-hour competition livestreams.
*   `--max-height`: Resolution cap (default: `1080`).
*   `--archive`: yt-dlp archive of everything already collected (default: `dance_video_archive.txt`). Search results overlap heavily between runs, so this is what stops a second run re-fetching the same clips. `--force` ignores it.
*   `--dry-run`: Print the titles and durations the search would fetch, without downloading.

> **⚠️ Review what you get.** The dance-type prefix comes from *your list file*, not from the video — a "Waltz" search will happily return a Viennese Waltz and it will be filed under Waltz. Skim the folder after collecting and delete or rename anything that does not match.

## ⚙️ Configuration (Weights)

Edit `dance_config.json` to change the probability of specific dance styles appearing. Each dance has a `weight` (relative importance), `tempo` ("slow" or "quick"), a `category` ("ballroom", "latin" or "social") used to space similar dances apart, and an optional `length` (custom max duration in seconds, 0 uses defaults).

```json
{
  "dances": {
    "Waltz": {
      "weight": 10,
      "tempo": "slow",
      "length": 0,
      "category": "ballroom"
    },
    "Foxtrot": {
      "weight": 5,
      "tempo": "slow",
      "length": 0,
      "category": "ballroom"
    },
    "ChaCha": {
      "weight": 10,
      "tempo": "quick",
      "length": 0,
      "category": "latin"
    },
    "Viennese Waltz": {
      "weight": 5,
      "tempo": "quick",
      "length": 120,
      "category": "ballroom"
    }
  }
}
```

A dance with no `category` still works — it is reported at startup and grouped as "uncategorized", which simply means it has nothing to alternate against. Categories are your own labels: add a new one (say `"country"`) and the sequencer will space those dances apart like any other.

### 🔀 How the running order is decided

Weights decide *how many* songs of each dance you get; these rules decide the *order*:

1.  **Alternate tempo** — first preference. A Quick dance follows a Slow one wherever possible.
2.  **Alternate category** — best effort, applied behind tempo. Where the two conflict, the tempo change wins.
3.  **No repeated dance type** back to back, and none repeated within 3 slots where the pool allows.
4.  **Waltz opens and closes the party.** The last dance always holds. The opening Waltz gives way if pinning it there would break up the alternation too much; with only one Waltz drafted it closes rather than opens, and with none the rule is skipped.

All of these are preferences, not requirements — the playlist is always generated in full, even from a pool where alternation is impossible (an all-Latin config, say). After each run the statistics report how well it did:

```
   Ballroom: 4 | Latin: 3 | Social: 1
   Slow: 5 | Quick: 3
   Favorites: 0 of 8
   Back-to-back same category: 0 | same tempo: 1
```

Some repeats are unavoidable and simply reflect the weights. If a playlist has, say, 11 Quick dances and 9 Slow ones, no ordering can alternate tempo the whole way through — the fix is to rebalance the weights, not the order.

## 📤 Step 3: Upload to YouTube

You have two options for uploading your generated videos to YouTube.

**Option A: Manual Upload**

1. Go to YouTube Studio > Create > Upload Videos.
2. Drag all files from `output_mp4s/` into the upload window.
3. YouTube will process them in alphanumeric order (01, 02, 03...).
4. Add them to a new Playlist.

**Option B: Automated Upload**
Instead of manually dragging and dropping files, you can use the automated uploader to push your generated MP4s directly to your YouTube channel.

1. Ensure your generated videos are in the `output_mp4s/` directory.
2. Run the uploader script:

```bash
python uploader.py

```

*(Run `python uploader.py -h` for usage options and authentication details)*

**Feature:** The uploader also automatically finds the `statistics.txt` file generated by `process.py`, reformats it into a clean, readable format, and appends it to the YouTube video description. This includes a breakdown of dance types, song counts, and total duration for a professional-looking result.

*Note: Make sure you have your YouTube API credentials (`client_secrets.json`) configured as required by the script. The script will handle authenticating your account and uploading the sequence automatically.*

---

## 🧰 Additional Audio/Video Utilities

This repository includes several standalone helper scripts to fine-tune your dance tracks before or after processing.

To see exactly how to use each tool, append `-h` when running them from the command line (e.g., `python speed_adjuster.py -h`):

* **`speed_adjuster.py`**: Modify the tempo (BPM) of specific dance tracks if they are too fast or too slow for a particular dance style. Works on audio files (MP3, M4A) and on video files (MP4) — for video the picture is retimed along with the audio, so a generated playlist MP4 stays in sync.
* **`cutter.py`**: Trim a single audio or video file down to a set length, ending with the same smooth fade out that `process.py` applies to playlist tracks. The fade is added *after* `--length` (so `--length 120 --fade 3` keeps a full 120s of music and runs 123s in total), and video files keep their picture — the video stream is copied untouched, so there is no quality loss.

  ```bash
  # Cut a song to 2 minutes, with the default 3 second fade
  python cutter.py --source "Waltz - A Daisy in December.mp3" --length 120

  # Cut a generated playlist MP4 to 2m 30s, with a 5 second fade
  python cutter.py --source "output_mp4s/01_Rumba_-_Pata_Pata.mp4" --length 150 --fade 5
  ```

* **`volume_adjuster.py`**: Manually normalize or adjust the volume of individual files that fall outside the standard processing ranges.
* **`converter.py`**: A general helper utility for handling various media format conversions.

### Advanced Video Splitting

The repository includes powerful tools for sourcing new music by splitting long video mixes into individual tracks. Both tools are idempotent, meaning they track their history and won't re-process a video you've already split.

*   **`video_splitter.py` (Recommended)**: A versatile, multi-function splitter. It can automatically find song boundaries using several methods, in order of priority:
    1.  A user-provided text file (`--textfile`).
    2.  Official YouTube chapters embedded in the video.
    3.  Timestamps found in the video's description.
    4.  **Automatic silence detection** (`--auto-silence`) for mixes with no metadata.

    **Example:**
    ```bash
    # Split a video by detecting silence between songs, prefixing each with "Waltz"
    python video_splitter.py "https://youtu.be/xyz123" --prefix "Waltz" --audio --auto-silence
    ```

*   **`split_manual.py`**: A simpler tool that splits a video based on a required text file of timestamps. It's a straightforward alternative if you already have a clean list of times.

```

```