import argparse
import os
import subprocess
import sys

def adjust_volume(source_path, db_adjustment):
    # 1. Validation
    if not os.path.exists(source_path):
        print(f"❌ Error: File not found: {source_path}")
        return

    # 2. Generate Output Filename
    # Example: "song.mp3" -> "song_+5dB.mp3" or "song_-3dB.mp3"
    directory, filename = os.path.split(source_path)
    name, ext = os.path.splitext(filename)
    
    # Format the suffix nicely (e.g., "+5dB", "-3dB")
    sign_symbol = "+" if db_adjustment >= 0 else "" 
    suffix = f"{sign_symbol}{db_adjustment}dB"
    
    new_filename = f"{name}_{suffix}{ext}"
    output_path = os.path.join(directory, new_filename)

    print(f"🔊 Processing: {filename}")
    print(f"   Adjustment: {suffix}")
    print(f"   Saving to:  {new_filename}")

    # 3. Run FFmpeg Command
    # The 'volume' filter uses dB. "volume=5dB" increases, "volume=-5dB" decreases.
    cmd = [
        "ffmpeg", "-y",
        "-v", "error",            # Less verbose
        "-i", source_path,
        "-filter:a", f"volume={db_adjustment}dB",
        "-vn",                    # Audio only
        output_path
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"✅ Success! Created: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg Error: {e}")
    except FileNotFoundError:
        print("❌ Error: FFmpeg is not installed or not in your PATH.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Adjust music volume (loudness) in decibels (dB).")
    
    # Arguments
    parser.add_argument("--source", required=True, help="Path to the mp3 file")
    parser.add_argument("--adjust", required=True, type=float, help="Volume change in dB (e.g. 5 for louder, -3 for quieter)")

    args = parser.parse_args()
    
    adjust_volume(args.source, args.adjust)