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

def parse_timestamps_from_text(text, duration):
    """Parses timestamps from description or text file."""
    chapters = []
    if not text:
        return chapters
        
    # Pattern 1: Timestamp at the beginning (e.g., "01:23 Song Name" or "1. [01:23] - Song Name")
    pat_start = re.compile(r'^\s*(?:\d+[\.)\]]?\s*)?\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+[-:]?\s*(.+)$')
    # Pattern 2: Timestamp at the end (e.g., "Song Name - 01:23" or "Song Name [01:23]")
    pat_end = re.compile(r'^(.+?)\s+[-:]?\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*$')
    
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        
        time_str, title = None, None
        match1 = pat_start.search(line)
        if match1:
            time_str, title = match1.group(1), match1.group(2).strip()
        else:
            match2 = pat_end.search(line)
            if match2:
                title, time_str = match2.group(1).strip(), match2.group(2)
                
        if time_str and title:
            # Clean up residual leading track numbers (e.g. "01 ")
            title = re.sub(r'^\d+\.?\s+[-_]?\s*', '', title)
            
            parts = list(map(int, time_str.split(':')))
            start_time = parts[0]*3600 + parts[1]*60 + parts[2] if len(parts) == 3 else parts[0]*60 + parts[1]
            chapters.append({'start_time': start_time, 'title': title})
            
    # Sort by time to be safe
    chapters.sort(key=lambda x: x['start_time'])
    
    # Deduplicate and calculate end times
    valid_chapters = []
    for chap in chapters:
        if not valid_chapters or chap['start_time'] > valid_chapters[-1]['start_time']:
            if valid_chapters: valid_chapters[-1]['end_time'] = chap['start_time']
            valid_chapters.append(chap)
            
    if valid_chapters:
        valid_chapters[-1]['end_time'] = duration if duration else valid_chapters[-1]['start_time'] + 300
    return valid_chapters

def split_video(url, prefix=None, output_folder="split_output", audio_only=False, textfile=None, auto_silence=False, min_silence=2000, silence_thresh=-40):
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

    duration = info.get('duration', 0)
    chapters = info.get('chapters')
    
    if textfile and os.path.exists(textfile):
        print(f"📄 Reading timestamps from {textfile}...")
        with open(textfile, 'r', encoding='utf-8') as f:
            chapters = parse_timestamps_from_text(f.read(), duration)
    elif not chapters:
        print("⚠️ No YouTube chapters found. Attempting to parse description...")
        description = info.get('description', '')
        chapters = parse_timestamps_from_text(description, duration)

    if not chapters and not auto_silence:
        print("❌ Error: No chapters found in this video or description. Use --auto-silence to split by audio gaps.")
        return

    if chapters and not auto_silence:
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

    if not chapters or auto_silence:
        print(f"🎧 Analyzing audio for silence (min {min_silence}ms at {silence_thresh}dBFS) to detect song boundaries...")
        from pydub import AudioSegment
        from pydub.silence import detect_silence
        
        audio = AudioSegment.from_file(full_file_path)
        silences = detect_silence(audio, min_silence_len=min_silence, silence_thresh=silence_thresh)
        
        chapters = []
        start_t = 0
        duration_sec = len(audio) / 1000.0
        
        for sil_start, sil_end in silences:
            end_t = sil_start / 1000.0
            if end_t - start_t > 15:  # Minimum song length of 15s to avoid glitches
                chapters.append({'start_time': start_t, 'end_time': end_t, 'title': f"AutoTrack_{len(chapters)+1:02d}"})
            start_t = sil_end / 1000.0
            
        if duration_sec - start_t > 15:
            chapters.append({'start_time': start_t, 'end_time': duration_sec, 'title': f"AutoTrack_{len(chapters)+1:02d}"})
            
        if not chapters:
             print("❌ Error: Could not detect any clear songs via silence.")
             os.remove(full_file_path)
             return
        print(f"✅ Auto-detected {len(chapters)} tracks from audio silence.")

    print(f"✂️  Splitting {full_file_path} into {len(chapters)} clips...")

    # 3. Split using FFmpeg
    for i, chapter in enumerate(chapters):
        start_time = chapter['start_time']
        end_time = chapter['end_time']
        title = chapter.get('title', 'NA')
        
        # Determine Filename
        # If title is bad (NA or empty), use index.
        # If prefix is set, use prefix.
        
        is_title_bad = not title or title.upper() == "NA" or title.startswith("AutoTrack")
        
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
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", full_file_path,
            "-ss", str(start_time),
            "-to", str(end_time)
        ]
        
        if ext == ".mp3":
            # Re-encode MP3 to avoid corrupted frame headers which cause Shazamio to segfault
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "192k"])
        else:
            cmd.extend(["-c", "copy"])
            
        cmd.append(output_path)
        
        subprocess.run(cmd)
        print(f"   Generated: {final_name}")

    # 4. Cleanup
    os.remove(full_file_path)
    print(f"\n🎉 Done! All files are in '{output_folder}/'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and Split YouTube video by Chapters.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("url", help="YouTube Video URL")
    parser.add_argument("--prefix", "-p", help="Prefix (e.g. 'Waltz'). If chapters have no names, 'Waltz-01' is used.")
    parser.add_argument("--folder", "-f", default="split_output", help="Output folder")
    parser.add_argument("--audio", "-a", action="store_true", help="Download as MP3 audio only")
    parser.add_argument("--textfile", "-t", help="Optional text file with timestamps to use instead of video description")
    parser.add_argument("--auto-silence", "-s", action="store_true", help="Auto-detect song boundaries using silence if no chapters are found")
    parser.add_argument("--min-silence", type=int, default=2000, help="Minimum silence length in ms for auto-split (default: 2000)")
    parser.add_argument("--silence-thresh", type=int, default=-40, help="Silence threshold in dBFS for auto-split (default: -40)")

    args = parser.parse_args()
    
    split_video(args.url, args.prefix, args.folder, args.audio, args.textfile, args.auto_silence, args.min_silence, args.silence_thresh)