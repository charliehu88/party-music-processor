
```markdown
# Dance Party Playlist Generator

A Python automation tool for ballroom dance hosts. This tool transforms a local collection of MP3s into a sequence of YouTube-ready MP4 videos.

It automates the DJ process by:
1. **Sequencing:** Alternating between "Quick" and "Slow" dances based on configurable logic.
2. **Processing:** Trimming songs to a set length, normalizing volume, and adding fades/silence.
3. **Visualizing:** Generating a 720p video file that displays "NOW PLAYING" and "COMING UP NEXT" metadata for your guests.
4. **Uploading:** Publishing the finished videos to YouTube (Manually or Automatically).

## 📂 Directory Structure

```text
party-music-processor/
├── assets/
├── input_mp3s/            # Drop your source music here
├── output_mp4s/           # Generated video files appear here
├── .venv/                 # Python virtual environment
├── NotoSansSC-VariableFont_wght.ttf  # Font for video overlays
├── process.py             # Core processing logic
├── download.py            # Batch downloader tool
├── playlist_2_file.py     # Playlist extractor tool
├── uploader.py            # Automated YouTube uploader
├── speed_adjuster.py      # Utility: Adjusts audio/video speed
├── volume_adjuster.py     # Utility: Adjusts audio volume
├── video_splitter.py      # Utility: Splits video files
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
brew install ffmpeg yt-dlp

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

**Option B: Extract YouTube Playlist to Downloads List**

If you have a YouTube playlist, use `playlist_2_file.py` to automatically generate a `downloads.txt`-style list with auto-detected dance types:

```bash
python playlist_2_file.py --playlist "https://www.youtube.com/playlist?list=OLAK5uy_..." --file my_playlist.txt
```

This tool analyzes each video's title and description to detect dance types (e.g., "Waltz", "ChaCha", "Viennese Waltz"). It outputs lines in the format: `https://youtu.be/<id> | <Dance Type> - <Title>`

*(Run `python playlist_2_file.py -h` for usage details)*

**Option C: Manual Download**

```bash
yt-dlp -x --audio-format mp3 -o "input_mp3s/DanceType - SongName.%(ext)s" "YOUTUBE_URL"

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

The processor prioritizes songs from the `--favorite` directory over the `--source` directory for each dance type. If favorites are available for a type, they are selected first before falling back to source songs.

**Arguments:**

* `--source`: Folder containing your MP3s.
* `--favorite`: Folder containing favorite MP3s (prioritized over source).
* `--output`: Folder where MP4s will be saved.
* `--config`: Path to the JSON weights file (default: `dance_config.json`).
* `--count`: Number of songs to generate (default: `20`).
* `--length-quick`: Max length for Quick dances in seconds (default: `150` = 2m 30s).
* `--length-slow`: Max length for Slow dances in seconds (default: `180` = 3m 00s).
* `--fade`: Fade out duration in seconds (default: `3`).
* `--silence`: Silence padding in seconds (default: `8`).
* `--mp3`: Also export processed MP3 files.
* `--output-mp3`: Folder for processed MP3s (default: `./output_processed_mp3s`).
* `--mp3`: Also export processed MP3 files.
* `--output-mp3`: Folder for processed MP3s (default: `./output_processed_mp3s`).

## ⚙️ Configuration (Weights)

Edit `dance_config.json` to change the probability of specific dance styles appearing. Each dance has a `weight` (relative importance), `tempo` ("slow" or "quick"), and optional `length` (custom max duration in seconds, 0 uses defaults).

```json
{
  "dances": {
    "Waltz": {
      "weight": 10,
      "tempo": "slow",
      "length": 0
    },
    "Foxtrot": {
      "weight": 5,
      "tempo": "slow",
      "length": 0
    },
    "ChaCha": {
      "weight": 10,
      "tempo": "quick",
      "length": 0
    },
    "Viennese Waltz": {
      "weight": 5,
      "tempo": "quick",
      "length": 120
    }
  }
}
```

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

*Note: Make sure you have your YouTube API credentials configured as required by the script. The script will handle authenticating your account and uploading the sequence automatically.*

---

## 🧰 Additional Audio/Video Utilities

This repository includes several standalone helper scripts to fine-tune your dance tracks before or after processing.

To see exactly how to use each tool, append `-h` when running them from the command line (e.g., `python speed_adjuster.py -h`):

* **`speed_adjuster.py`**: Modify the tempo (BPM) of specific dance tracks if they are too fast or too slow for a particular dance style.
* **`volume_adjuster.py`**: Manually normalize or adjust the volume of individual files that fall outside the standard processing ranges.
* **`video_splitter.py` / `split_manual.py`**: Tools for splitting longer continuous mixes or existing video files into individual, cleanly cut dance tracks.
* **`converter.py`**: A general helper utility for handling various media format conversions.

```

```