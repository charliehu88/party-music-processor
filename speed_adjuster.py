import argparse
import os
import subprocess
import sys

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}

def probe_streams(source_path):
    """
    Report what the file actually holds: (has_video, has_audio).

    Cover art embedded in an MP3/M4A shows up as a video stream, so a plain
    "does it have video?" check would treat a tagged audio file as a movie.
    Those streams are flagged 'attached_pic', which is what we filter on here.
    Falls back to the file extension if ffprobe is unavailable.
    """
    def stream_dispositions(kind, entries):
        cmd = ["ffprobe", "-v", "error", "-select_streams", kind,
               "-show_entries", entries, "-of", "csv=p=0", source_path]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return [line.strip() for line in result.stdout.splitlines() if line.strip() != ""]

    try:
        video = [d for d in stream_dispositions("v", "stream_disposition=attached_pic") if d == "0"]
        audio = stream_dispositions("a", "stream=index")
        return bool(video), bool(audio)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.path.splitext(source_path)[1].lower() in VIDEO_EXTS, True

def adjust_speed(source_path, adjustment_percent):
    # 1. Validation
    if not os.path.exists(source_path):
        print(f"❌ Error: File not found: {source_path}")
        return

    # 2. Calculate Speed Factor
    # Factor 1.0 = 100% (Normal)
    # Factor 1.1 = +10% Speed
    # Factor 0.9 = -10% Speed
    speed_factor = 1.0 + (adjustment_percent / 100.0)

    # Safety Check: FFmpeg 'atempo' works best between 0.5 (half speed) and 2.0 (double speed)
    if not (0.5 <= speed_factor <= 2.0):
        print(f"❌ Error: Adjustment {adjustment_percent}% is too extreme.")
        print("   Please keep it between -50 (half speed) and 100 (double speed).")
        return

    # 3. Generate Output Filename
    # Example: "mysong.mp3" -> "mysong_+10.mp3" or "mysong_-5.mp3"
    directory, filename = os.path.split(source_path)
    name, ext = os.path.splitext(filename)
    
    sign_symbol = "+" if adjustment_percent >= 0 else "" # Negative numbers already have '-'
    suffix = f"{sign_symbol}{int(adjustment_percent)}"
    
    new_filename = f"{name}_{suffix}{ext}"
    output_path = os.path.join(directory, new_filename)

    has_video, has_audio = probe_streams(source_path)
    if not has_audio and not has_video:
        print(f"❌ Error: No audio or video streams found in: {filename}")
        return

    print(f"{'🎬' if has_video else '🎧'} Processing: {filename}")
    print(f"   Target:     {speed_factor:.2f}x speed ({adjustment_percent}%)")
    print(f"   Saving to:  {new_filename}")

    # 4. Run FFmpeg
    # The 'atempo' filter changes tempo without altering pitch. For video the
    # picture has to be re-timed to match, or the two drift apart: 'setpts'
    # rescales each frame's timestamp by the inverse factor (faster audio =
    # shorter frame spacing), keeping the video in sync for the whole track.
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", source_path]

    if has_video:
        filters, maps = [], []
        if has_audio:
            filters.append(f"[0:a]atempo={speed_factor}[a]")
            maps += ["-map", "[a]"]
        filters.append(f"[0:v]setpts=PTS/{speed_factor}[v]")
        maps += ["-map", "[v]"]

        cmd += [
            "-filter_complex", ";".join(filters),
            *maps,
            # Match the encoding process.py uses for its still-image playlists
            "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
        ]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "256k"]
    else:
        cmd += ["-filter:a", f"atempo={speed_factor}", "-vn"]

    cmd.append(output_path)

    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Success! Created: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg Error: {e}")
    except FileNotFoundError:
        print("❌ Error: FFmpeg is not installed or not in your PATH.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adjust music speed without changing pitch. Audio files keep their format; video files (MP4 etc.) stay in sync with the retimed audio.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Required Named Arguments
    parser.add_argument("--source", required=True, help="Path to the audio file (MP3, M4A...) or video file (MP4...)")
    parser.add_argument("--adjust", required=True, type=float, help="Percentage adjustment (e.g. 10 or -10)")

    args = parser.parse_args()
    
    adjust_speed(args.source, args.adjust)