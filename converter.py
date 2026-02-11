import argparse
import os
import subprocess
import sys

# === CONFIGURATION ===
# Primary Font (Chinese support)
PRIMARY_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf", # Best (.ttf is safer than .ttc)
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc"
]

# Fallback Font (Safe, English only)
FALLBACK_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
if not os.path.exists(FALLBACK_FONT):
    FALLBACK_FONT = "/Library/Fonts/Arial.ttf"

def get_best_font():
    """Finds the best available font for Chinese support."""
    for font in PRIMARY_FONT_CANDIDATES:
        if os.path.exists(font):
            return font
    return FALLBACK_FONT

def escape_ffmpeg_text(text):
    """Escapes special characters for FFmpeg drawtext."""
    # 1. Escape backslashes first
    text = text.replace("\\", "\\\\")
    # 2. Escape colons (filter delimiter)
    text = text.replace(":", "\\:")
    # 3. Escape single quotes (string delimiter)
    text = text.replace("'", "'\\\\''") 
    # 4. Escape percent signs (sometimes expanded by ffmpeg)
    text = text.replace("%", "\\%")
    return text

def run_ffmpeg_command(cmd, filename):
    """Runs FFmpeg and captures stderr for debugging."""
    try:
        # We capture stderr so we can print it if something goes wrong
        result = subprocess.run(cmd, check=True, stderr=subprocess.PIPE, text=True)
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def convert_media(source_dir, target_dir, mode):
    # 1. Setup Directories
    if not os.path.exists(source_dir):
        print(f"❌ Error: Source directory '{source_dir}' not found.")
        return

    if not target_dir:
        target_dir = source_dir
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"📂 Created target directory: {target_dir}")

    # 2. Setup Fonts
    primary_font = get_best_font()
    print(f"🔤 Primary Font: {os.path.basename(primary_font)}")
    print(f"🔤 Fallback Font: {os.path.basename(FALLBACK_FONT)}")

    # 3. Determine Mode
    if mode == "mp4_to_mp3":
        src_ext = ".mp4"
        tgt_ext = ".mp3"
    elif mode == "mp3_to_mp4":
        src_ext = ".mp3"
        tgt_ext = ".mp4"
    else:
        print("❌ Error: Invalid mode.")
        return

    # 4. Find Files
    files = [f for f in os.listdir(source_dir) if f.lower().endswith(src_ext)]
    if not files:
        print(f"⚠️  No {src_ext} files found in '{source_dir}'.")
        return

    print(f"   Found {len(files)} files to convert.")
    
    # 5. Process Loop
    success_count = 0
    
    for filename in files:
        src_path = os.path.join(source_dir, filename)
        name_part = os.path.splitext(filename)[0]
        tgt_filename = f"{name_part}{tgt_ext}"
        tgt_path = os.path.join(target_dir, tgt_filename)

        print(f"⏳ Converting: {filename} ...", end="\r")

        # --- COMMAND GENERATION ---
        # We define a helper to build the command so we can easily swap fonts
        def build_command(font_path_to_use):
            if mode == "mp4_to_mp3":
                return [
                    "ffmpeg", "-y", "-v", "error",
                    "-i", src_path, "-vn",
                    "-acodec", "libmp3lame", "-q:a", "2",
                    tgt_path
                ]
            elif mode == "mp3_to_mp4":
                clean_name = escape_ffmpeg_text(name_part)
                # Note: We put the path in single quotes inside the string
                filter_str = (
                    f"drawtext=fontfile='{font_path_to_use}':"
                    f"text='{clean_name}':"
                    "fontcolor=white:fontsize=60:"
                    "x=(w-text_w)/2:y=(h-text_h)/2"
                )
                return [
                    "ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=1",
                    "-i", src_path,
                    "-filter_complex", f"[0:v]{filter_str}[v]",
                    "-map", "[v]", "-map", "1:a",
                    "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-shortest",
                    tgt_path
                ]

        # --- ATTEMPT 1: Primary Font ---
        cmd = build_command(primary_font)
        success, error_msg = run_ffmpeg_command(cmd, filename)

        if not success and mode == "mp3_to_mp4":
            # --- ATTEMPT 2: Fallback Font ---
            # If the fancy font failed, try the boring one.
            # This fixes issues where .ttc files or chinese characters break FFmpeg.
            cmd_fallback = build_command(FALLBACK_FONT)
            success, error_msg_fallback = run_ffmpeg_command(cmd_fallback, filename)
            
            if success:
                print(f"⚠️  Used fallback font for: {filename}      ")
            else:
                print(f"\n❌ Failed to convert {filename}")
                print(f"   Error: {error_msg_fallback}") # Print the ACTUAL error
        elif not success:
             print(f"\n❌ Failed to convert {filename}")
             print(f"   Error: {error_msg}")

        if success:
            success_count += 1
            
    print(f"\n✅ Done! {success_count}/{len(files)} converted.")
    print(f"📂 Output: {target_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch convert MP3 <-> MP4")
    parser.add_argument("--source", "-s", required=True, help="Source Directory")
    parser.add_argument("--target", "-t", help="Target Directory")
    parser.add_argument("--mode", "-m", required=True, choices=['mp4_to_mp3', 'mp3_to_mp4'], help="Mode")
    args = parser.parse_args()
    
    convert_media(args.source, args.target, args.mode)