import argparse
import os
import sys
import subprocess
import re
import yt_dlp

def sanitize_filename(name):
    """Removes illegal characters from filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def get_unique_filename(directory, filename):
    """Ensures we don't overwrite existing files."""
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(directory, new_filename)):
        new_filename = f"{base}_{counter}{ext}"
        counter += 1
    return new_filename

def split_video(url, prefix=None, output_folder="split_output", audio_only=False):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    print(f"🔍 Analyzing: {url}")
    
    # 1. Get Video Info & Chapters
    ydl_opts_info = {'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"❌ Error fetching info: {e}")
            return

    chapters = info.get('chapters')
    if not chapters:
        print("❌ Error: No chapters found in this video.")
        return

    print(f"✅ Found {len(chapters)} chapters.")

    # 2. Download the FULL Source File
    print("⬇️  Downloading full source file (will split locally)...")
    
    temp_filename = "temp_full_source"
    
    ydl_opts_download = {
        'outtmpl': temp_filename,
        'quiet': False,
        # Force MP4 for video or MP3/Best for audio
        'format': 'bestaudio/best' if audio_only else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    }
    
    if audio_only:
        ydl_opts_download['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
        ext = ".mp3"
    else:
        ext = ".mp4"

    full_file_path = f"{temp_filename}{ext}"
    
    # If the file ended up being .webm or .mkv, yt-dlp might have appended the extension
    # We let yt-dlp handle the download, then find the file.
    with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
        ydl.download([url])

    # Find the actual downloaded file (handling potential extension mismatches)
    if not os.path.exists(full_file_path):
        # Fallback search
        for f in os.listdir("."):
            if f.startswith(temp_filename):
                full_file_path = f
                break
    
    if not os.path.exists(full_file_path):
        print("❌ Error: Could not find downloaded source file.")
        return

    print(f"✂️  Splitting {full_file_path} into {len(chapters)} clips...")

    # 3. Split using FFmpeg
    for i, chapter in enumerate(chapters):
        start_time = chapter['start_time']
        end_time = chapter['end_time']
        title = chapter.get('title', 'NA')
        
        # Determine Filename
        # If title is bad (NA or empty), use index.
        # If prefix is set, use prefix.
        
        is_title_bad = not title or title.upper() == "NA"
        
        if prefix:
            if is_title_bad:
                # Fallback: "Waltz-01.mp4"
                final_name = f"{prefix}-{i+1:02d}{ext}"
            else:
                # Desired: "Waltz-SongName.mp4"
                clean_title = sanitize_filename(title)
                final_name = f"{prefix}-{clean_title}{ext}"
        else:
            # Default: "01_SongName.mp4"
            clean_title = sanitize_filename(title) if not is_title_bad else f"Track_{i+1:02d}"
            final_name = f"{i+1:02d}_{clean_title}{ext}"

        # Prevent Overwrites
        final_name = get_unique_filename(output_folder, final_name)
        output_path = os.path.join(output_folder, final_name)

        # FFmpeg Split Command
        # -ss (start) -to (end) -c copy (fast, no quality loss)
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", full_file_path,
            "-ss", str(start_time),
            "-to", str(end_time),
            "-c", "copy",
            output_path
        ]
        
        subprocess.run(cmd)
        print(f"   Generated: {final_name}")

    # 4. Cleanup
    os.remove(full_file_path)
    print(f"\n🎉 Done! All files are in '{output_folder}/'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and Split YouTube video by Chapters.")
    parser.add_argument("url", help="YouTube Video URL")
    parser.add_argument("--prefix", "-p", help="Prefix (e.g. 'Waltz'). If chapters have no names, 'Waltz-01' is used.")
    parser.add_argument("--folder", "-f", default="split_output", help="Output folder")
    parser.add_argument("--audio", "-a", action="store_true", help="Download as MP3 audio only")

    args = parser.parse_args()
    
    split_video(args.url, args.prefix, args.folder, args.audio)