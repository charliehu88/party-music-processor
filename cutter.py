import argparse
import os
import subprocess
import sys

from pydub import AudioSegment

from process import smooth_fade_out, FADE_CURVE, FADE_FLOOR_DB
from speed_adjuster import probe_streams

# pydub needs the container name and codec, which don't always match the extension
EXPORT_FORMATS = {
    ".mp3": ("mp3", None),
    ".m4a": ("ipod", "aac"),
    ".aac": ("adts", "aac"),
    ".wav": ("wav", None),
    ".flac": ("flac", None),
    ".ogg": ("ogg", "libvorbis"),
}

def probe_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "csv=p=0", path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return 0.0

def cut_audio(source_path, output_path, ext, length_s, fade_s):
    audio = AudioSegment.from_file(source_path)
    total_ms = int(round((length_s + fade_s) * 1000))
    if len(audio) > total_ms:
        audio = audio[:total_ms]

    audio = smooth_fade_out(audio, fade_s * 1000)

    fmt, codec = EXPORT_FORMATS.get(ext, ("mp3", None))
    audio.export(output_path, format=fmt, **({"codec": codec} if codec else {}))

def cut_video(source_path, output_path, length_s, fade_s, fade_start, has_audio):
    # Cutting from the start means the video stream can be copied untouched -
    # no re-encode, no quality loss. Only the audio needs rebuilding, since the
    # fade has to be written into the samples.
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", source_path,
           "-t", f"{length_s + fade_s}", "-c:v", "copy"]

    if has_audio:
        if fade_s > 0:
            # Same curve as process.py: a dB ramp bent by FADE_CURVE, so the
            # volume holds near full, then eases down instead of lunging.
            expr = (f"if(lt(t,{fade_start}),1,"
                    f"pow(10,({FADE_FLOOR_DB}*pow((t-{fade_start})/{fade_s},{FADE_CURVE}))/20))")
            cmd += ["-af", f"volume=volume='{expr}':eval=frame"]
        cmd += ["-c:a", "aac", "-b:a", "256k"]

    cmd.append(output_path)
    subprocess.run(cmd, check=True)

def cut(source_path, length_s, fade_s):
    # 1. Validation
    source_path = os.path.expanduser(source_path)
    if not os.path.exists(source_path):
        print(f"❌ Error: File not found: {source_path}")
        return
    if length_s <= 0:
        print(f"❌ Error: --length must be greater than 0 (got {length_s}).")
        return
    if fade_s < 0:
        print(f"❌ Error: --fade cannot be negative (got {fade_s}).")
        return

    has_video, has_audio = probe_streams(source_path)
    if not has_audio and not has_video:
        print(f"❌ Error: No audio or video streams found in: {source_path}")
        return

    # 2. Work out where the fade sits
    # --length is full-volume material; the fade is added after it, matching how
    # process.py treats dance length, so the cut keeps the length you asked for.
    directory, filename = os.path.split(source_path)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    duration = probe_duration(source_path)
    total_s = length_s + fade_s
    fade_start = length_s

    if duration and duration < total_s:
        print(f"⚠️  Source is only {duration:.1f}s, shorter than {total_s:.1f}s "
              f"({length_s:g}s + {fade_s:g}s fade) - fading out the end of what's there.")
        total_s = duration
        fade_start = max(0.0, duration - fade_s)

    output_path = os.path.join(directory, f"{name}_cut{length_s:g}s{ext}")

    print(f"{'🎬' if has_video else '🎧'} Cutting:  {filename}")
    print(f"   Keeping:   {min(length_s, max(0.0, total_s - fade_s)):g}s at full volume, "
          f"then a {fade_s:g}s fade")
    print(f"   Total:     {total_s:.1f}s")
    print(f"   Saving to: {os.path.basename(output_path)}")

    # 3. Cut it
    try:
        if has_video:
            cut_video(source_path, output_path, length_s, fade_s, fade_start, has_audio)
        else:
            cut_audio(source_path, output_path, ext, length_s, fade_s)
        print(f"✅ Success! Created: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg Error: {e}")
    except FileNotFoundError:
        print("❌ Error: FFmpeg is not installed or not in your PATH.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cut an audio or video file down to a set length, ending with a smooth fade out. "
                    "The fade is added after --length, so you keep the full length you asked for.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--source", required=True, help="Path to the audio file (MP3, M4A...) or video file (MP4...)")
    parser.add_argument("--length", required=True, type=float, help="Length to keep at full volume, in seconds")
    parser.add_argument("--fade", type=float, default=3, help="Fade out (s), added on top of --length")

    args = parser.parse_args()

    cut(args.source, args.length, args.fade)
