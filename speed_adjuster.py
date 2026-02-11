import argparse
import os
import subprocess
import sys

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

    print(f"🎧 Processing: {filename}")
    print(f"   Target:     {speed_factor:.2f}x speed ({adjustment_percent}%)")
    print(f"   Saving to:  {new_filename}")

    # 4. Run FFmpeg
    # The 'atempo' filter changes tempo without altering pitch.
    cmd = [
        "ffmpeg", "-y",
        "-v", "error",            # Less verbose
        "-i", source_path,
        "-filter:a", f"atempo={speed_factor}",
        "-vn",                    # Audio only (strip images/video if present)
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
    parser = argparse.ArgumentParser(description="Adjust music speed without changing pitch.")
    
    # Required Named Arguments
    parser.add_argument("--source", required=True, help="Path to the mp3 file")
    parser.add_argument("--adjust", required=True, type=float, help="Percentage adjustment (e.g. 10 or -10)")

    args = parser.parse_args()
    
    adjust_speed(args.source, args.adjust)