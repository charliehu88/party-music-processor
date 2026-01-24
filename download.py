import os
import subprocess
import argparse
import shutil

# File to store URLs of songs we have already downloaded
HISTORY_FILE = "download_history.log"

def parse_args():
    parser = argparse.ArgumentParser(description="Universal Batch Downloader (YouTube, SoundCloud, TikTok, etc.)")
    parser.add_argument("--list", "-l", default="downloads.txt", help="Path to the list file (Format: URL | Name)")
    parser.add_argument("--output", "-o", default="input_mp3s", help="Folder to save downloads")
    parser.add_argument("--browser", "-b", help="Load cookies from browser (e.g. 'chrome', 'safari', 'firefox')")
    parser.add_argument("--force", action="store_true", help="Ignore history and force re-download")
    return parser.parse_args()

def load_history():
    """Loads the set of previously downloaded URLs."""
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f if line.strip())

def update_history(url):
    """Appends a new URL to the history file."""
    with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
        f.write(url + "\n")

def download_track(url, custom_name, output_dir, browser=None):
    """Calls yt-dlp to download and convert to MP3."""
    
    output_template = os.path.join(output_dir, f"{custom_name}.%(ext)s")
    
    print(f"⬇️  Downloading: {custom_name}...")
    
    cmd = [
        "yt-dlp",
        "-x",                       # Extract audio
        "--audio-format", "mp3",    # Convert to MP3
        "--audio-quality", "0",     # Best quality
        "-o", output_template,      # Output template
        "--no-playlist",            # Ensure we only get the single video
        "--ignore-errors",          # Don't crash batch on error
        "--no-warnings",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36", 
    ]

    if browser:
        cmd.extend(["--cookies-from-browser", browser])

    cmd.append(url)

    try:
        # Run process
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"✅ Success: {custom_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed: {custom_name}")
        if e.stderr:
            error_lines = e.stderr.strip().split('\n')
            print(f"   Error: {error_lines[-1]}")
        return False

def main():
    args = parse_args()

    if not shutil.which("ffmpeg"):
        print("❌ Error: 'ffmpeg' is not installed.")
        return

    if not os.path.exists(args.list):
        print(f"Error: List file '{args.list}' not found.")
        return

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    # 1. Load History
    history = load_history()
    if not args.force:
        print(f"📚 Loaded {len(history)} previously downloaded URLs.")
    
    print(f"Reading queue from {args.list}...")
    if args.browser:
        print(f"🔓 Masquerading as {args.browser}...")
    
    with open(args.list, 'r') as f:
        lines = f.readlines()

    # Track URLs seen in THIS run (to catch duplicates inside the text file itself)
    seen_in_batch = set()

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"): 
            continue 

        if "|" in line:
            parts = line.split("|")
            url = parts[0].strip()
            name = parts[1].strip()
            
            # Sanitization
            name = name.replace("/", "-").replace("\\", "-")
            
            # CHECK 1: Duplicates in the current text file
            if url in seen_in_batch:
                print(f"⏭️  Skipping (Duplicate in file): {name}")
                continue
            seen_in_batch.add(url)

            # CHECK 2: History (Already downloaded previously)
            if not args.force and url in history:
                print(f"⏭️  Skipping (Already in history): {name}")
                continue
            
            # Attempt Download
            success = download_track(url, name, args.output, args.browser)
            
            # If successful, save to history immediately
            if success:
                update_history(url)
                history.add(url)
                
        else:
            print(f"⚠️ Skipped invalid line: {line}")
        
    print(f"\nBatch complete.")

if __name__ == "__main__":
    main()