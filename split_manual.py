import argparse
import os
import re
import subprocess
import yt_dlp

def parse_timestamps(text_file):
    """Parses lines like '02:39 02 Midnight in London' into a list."""
    chapters = []
    with open(text_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Regex to find "MM:SS Song Name" or "HH:MM:SS Song Name"
    # Matches: "02:39", "1:05:00", followed by any text
    pattern = re.compile(r'(\d{1,2}:\d{2}(?::\d{2})?)\s+(.*)')

    for line in lines:
        match = pattern.search(line)
        if match:
            time_str = match.group(1)
            title = match.group(2).strip()
            
            # Clean up title (remove "01", "02" numbers if they exist at start)
            # Example: "01 Caccini" -> "Caccini"
            title = re.sub(r'^\d+\s+[-_]?\s*', '', title)
            
            chapters.append({'time': time_str, 'title': title})
            
    return chapters

def download_full_video(url, output_file):
    print(f"⬇️  Downloading source video...")
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_file,
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def get_seconds(time_str):
    """Converts '01:05:20' or '04:30' to seconds."""
    parts = list(map(int, time_str.split(':')))
    if len(parts) == 3:
        return parts[0]*3600 + parts[1]*60 + parts[2]
    return parts[0]*60 + parts[1]

def split_video(url, text_file, prefix=None, output_folder="manual_splits"):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # 1. Parse the Text File
    chapters = parse_timestamps(text_file)
    if not chapters:
        print("❌ Error: Could not find any timestamps in your text file.")
        print("   Make sure lines look like: '00:00 Song Name'")
        return

    print(f"✅ Found {len(chapters)} songs in text file.")

    # 2. Download Source
    source_filename = "temp_source_video.mp4"
    if not os.path.exists(source_filename):
        download_full_video(url, source_filename)
    else:
        print("   (Using existing temp_source_video.mp4)")

    # 3. Split Loop
    for i in range(len(chapters)):
        current = chapters[i]
        start_str = current['time']
        title = current['title']
        
        # Determine End Time
        if i < len(chapters) - 1:
            end_str = chapters[i+1]['time']
            # FFmpeg needs duration or "to" position. "-to" works best.
        else:
            end_str = None # Last song goes to end of video

        # Filename
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
        if prefix:
            outfile = f"{prefix}-{safe_title}.mp4"
        else:
            outfile = f"{i+1:02d}_{safe_title}.mp4"
            
        output_path = os.path.join(output_folder, outfile)
        
        print(f"✂️  Splitting: {start_str} -> {title}")

        cmd = ["ffmpeg", "-y", "-v", "error", "-i", source_filename, "-ss", start_str]
        
        if end_str:
            cmd.extend(["-to", end_str])
        
        cmd.extend(["-c", "copy", output_path])
        
        subprocess.run(cmd)

    # Optional: Remove source
    # os.remove(source_filename) 
    print(f"\n🎉 Done! Check folder: {output_folder}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument("textfile", help="File containing the copy-pasted description")
    parser.add_argument("--prefix", "-p", help="Prefix (e.g. 'Waltz')")
    args = parser.parse_args()
    
    split_video(args.url, args.textfile, args.prefix)