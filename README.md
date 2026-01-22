No problem. Renaming the script to `process.py` makes a lot of sense, as it clearly separates the "processor" logic from the "downloader" logic.

Here is the fully updated `README.md` with `main.py` replaced by `process.py`. You can copy and paste the entire block below.

```markdown
# Dance Party Playlist Generator

A Python automation tool for ballroom dance hosts. This tool transforms a local collection of MP3s into a sequence of YouTube-ready MP4 videos.

It automates the DJ process by:
1.  **Sequencing:** Alternating between "Quick" and "Slow" dances based on configurable logic.
2.  **Processing:** Trimming songs to a set length, normalizing volume, and adding fades/silence.
3.  **Visualizing:** Generating a 720p video file that displays "NOW PLAYING" and "COMING UP NEXT" metadata for your guests.

## 📂 Directory Structure

```text
party-music-processor/
├── assets/
│   └── cover.jpg          # (Required) Background image for video generation
├── input_mp3s/            # Drop your source music here
├── output_mp4s/           # Generated video files appear here
├── .venv/                 # Python virtual environment
├── process.py             # Core processing logic
├── download.py            # Batch downloader tool
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

---

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



**Option B: Manual Download**

```bash
yt-dlp -x --audio-format mp3 -o "input_mp3s/DanceType - SongName.%(ext)s" "YOUTUBE_URL"

```

---

## 🎵 File Naming Convention

**Crucial:** For the processor to correctly categorize speed (Quick/Slow) and display titles, files must follow this format:

`[Dance Type] - [Song Name].mp3`

**Examples:**

* ✅ `Waltz - Moon River.mp3`
* ✅ `ChaCha - Sway.mp3`
* ✅ `West Coast Swing - The Way You Make Me Feel.mp3`

*Note: The script is case-insensitive. It relies on the "Dance Type" keyword (e.g., "Waltz", "Jive") being present in the filename.*

---

## 🚀 Step 2: Generate Playlist

### Option A: VS Code (Recommended)

1. Open this folder in VS Code.
2. Ensure your `.venv` is selected as the Python Interpreter.
3. Open `process.py`.
4. Press **F5** to run.
* *Configuration can be changed in `.vscode/launch.json*`



### Option B: Command Line

```bash
python process.py --source ./input_mp3s --output ./output_mp4s --count 20

```

**Arguments:**

* `--source`: Folder containing your MP3s.
* `--output`: Folder where MP4s will be saved.
* `--config`: Path to the JSON weights file (default: `dance_config.json`).
* `--count`: Number of songs to generate (default: 20).
* `--length-quick`: Max length for Quick dances in seconds (default: 150 = 2m 30s).
* `--length-slow`: Max length for Slow dances in seconds (default: 180 = 3m 00s).
* `--fade`: Fade out duration in seconds (default: 3).
* `--silence`: Silence padding in seconds (default: 8).

---

## ⚙️ Configuration (Weights)

Edit `dance_config.json` to change the probability of specific dance styles appearing (e.g., 0.15 = 15%).

```json
{
    "weights": {
        "Waltz": 0.15,
        "ChaCha": 0.10,
        "Viennese Waltz": 0.00
    }
}

```

## 📤 Step 3: Upload to YouTube

1. Go to YouTube Studio > Create > Upload Videos.
2. Drag all files from `output_mp4s/` into the upload window.
3. YouTube will process them in alphanumeric order (01, 02, 03...).
4. Add them to a new Playlist.

```

### Don't forget `.vscode/launch.json`
Since you renamed the file, you also need to update your VS Code configuration so the **F5** key still works.

Update `.vscode/launch.json`:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Run Processor",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/process.py",
            "console": "integratedTerminal",
            "args": [
                "--source", "${workspaceFolder}/input_mp3s",
                "--output", "${workspaceFolder}/output_mp4s",
                "--config", "${workspaceFolder}/dance_config.json",
                "--count", "10"
            ]
        },
        {
            "name": "Run Downloader",
            "type": "debugpy",
            "request": "launch",
            "program": "${workspaceFolder}/download.py",
            "console": "integratedTerminal",
            "args": [
                "--list", "${workspaceFolder}/downloads.txt",
                "--output", "${workspaceFolder}/input_mp3s"
            ]
        }
    ]
}

```

*(I added a second launch configuration so you can now debug/run the Downloader from VS Code as well!)*