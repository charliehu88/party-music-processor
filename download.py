import os
import subprocess
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description="Batch download MP3s from YouTube with custom names.")
    parser.add_argument("--list", "-l", default="downloads.txt", help="Path to the list file (Format: URL | Name)")
    parser.add_argument("--output", "-o", default="input_mp3s", help="Folder to save downloads")
    return parser.parse_args()

def download_track(url, custom_name, output_dir):
    """Calls yt-dlp to download and convert to MP3."""
    
    # ensure output filename has no extension logic yet, yt-dlp handles it
    output_template = os.path.join(output_dir, f"{custom_name}.%(ext)s")
    
    print(f"⬇️ Downloading: {custom_name}...")
    
    cmd = [
        "yt-dlp",
        "-x",                       # Extract audio
        "--audio-format", "mp3",    # Convert to MP3
        "--audio-quality", "0",     # Best quality
        "-o", output_template,      # Output template
        "--no-playlist",            # Ensure we only get the single video if URL is a mix
        url
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"✅ Success: {custom_name}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed: {custom_name}")
        # Print the error from yt-dlp (which is in stderr)
        if e.stderr:
            print(f"   Error details: {e.stderr.decode().strip()}")

def main():
    args = parse_args()

    if not os.path.exists(args.list):
        print(f"Error: List file '{args.list}' not found.")
        return

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    print(f"Reading queue from {args.list}...")
    
    with open(args.list, 'r') as f:
        lines = f.readlines()

    success_count = 0
    total_count = 0

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"): 
            continue # Skip empty lines or comments

        # Parse "URL | Name"
        if "|" in line:
            parts = line.split("|")
            url = parts[0].strip()
            name = parts[1].strip()
            
            # Simple cleanup to prevent filename errors
            name = name.replace("/", "-").replace("\\", "-")
            
            download_track(url, name, args.output)
            success_count += 1
        else:
            print(f"⚠️ Skipped invalid line (missing '|'): {line}")
        
        total_count += 1

    print(f"\nBatch complete. Downloaded {success_count} tracks to '{args.output}'.")

if __name__ == "__main__":
    main()