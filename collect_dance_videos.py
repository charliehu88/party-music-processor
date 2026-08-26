import os
import re
import subprocess
import argparse
import shutil

# yt-dlp's own archive format: one line per video it has already fetched.
# Search results overlap heavily between runs, so without this a second run
# re-downloads most of the same clips under slightly different titles.
ARCHIVE_FILE = "dance_video_archive.txt"

# What a clip needs to be useful as a background: long enough to cover a chunk
# of a track, short enough not to be a two-hour competition livestream.
DEFAULT_MIN_DURATION = 30
DEFAULT_MAX_DURATION = 900

# Appended to each dance type to form the search. Overridable with --query.
DEFAULT_QUERY = "{dance} ballroom dance performance"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Search YouTube and collect dance clips for process.py --video-pool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--list", "-l", default="dance_videos.txt",
                        help="File of dance types (Format: Dance Type | Count | Extra search terms)")
    parser.add_argument("--output", "-o", default="./dance_videos", help="Folder to save clips")
    parser.add_argument("--per-dance", "-n", type=int, default=5,
                        help="Clips per dance type, when the list file does not give a count")
    parser.add_argument("--query", "-q", default=DEFAULT_QUERY,
                        help="Search template. '{dance}' is replaced with the dance type")
    parser.add_argument("--min-duration", type=int, default=DEFAULT_MIN_DURATION, help="Skip clips shorter than this (s)")
    parser.add_argument("--max-duration", type=int, default=DEFAULT_MAX_DURATION, help="Skip clips longer than this (s)")
    parser.add_argument("--max-height", type=int, default=1080, help="Cap the download resolution")
    parser.add_argument("--browser", "-b", help="Load cookies from browser (e.g. 'chrome', 'safari', 'firefox')")
    parser.add_argument("--archive", default=ARCHIVE_FILE, help="Archive file of already-collected videos")
    parser.add_argument("--force", action="store_true", help="Ignore the archive and re-download")
    parser.add_argument("--dry-run", action="store_true", help="List what would be downloaded without downloading")

    args = parser.parse_args()
    args.output = os.path.expanduser(args.output)
    return args


def parse_list(list_path, default_count):
    """
    Read the dance list.

    Same pipe-separated style as downloads.txt. Count and extra search terms
    are both optional, so the simplest useful file is one dance per line:

        Waltz
        Rumba | 8
        Viennese Waltz | 3 | competition final
    """
    requests = []
    with open(list_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = [p.strip() for p in line.split("|")]
            dance = parts[0]
            if not dance:
                continue

            count = default_count
            if len(parts) > 1 and parts[1]:
                if parts[1].isdigit():
                    count = int(parts[1])
                else:
                    print(f"⚠️  Ignoring non-numeric count '{parts[1]}' for {dance}.")

            extra = parts[2] if len(parts) > 2 else ""
            requests.append((dance, count, extra))
    return requests


def collect_dance(dance, count, extra, args):
    """Search YouTube for one dance type and download the top matching clips."""
    query = args.query.format(dance=dance)
    if extra:
        query = f"{query} {extra}"

    # Filenames must match what process.py --video-pool expects:
    # "<Dance Type> - <name>.mp4". yt-dlp sanitises the title for us, but a
    # title containing " - " would confuse nothing here - only the leading
    # dance type is ever parsed.
    output_template = os.path.join(args.output, f"{dance} - %(title).80B.%(ext)s")

    duration_filter = f"duration > {args.min_duration} & duration < {args.max_duration}"

    cmd = [
        "yt-dlp",
        f"ytsearch{count}:{query}",
        "-f", f"bestvideo[height<={args.max_height}][ext=mp4]+bestaudio[ext=m4a]/"
              f"best[height<={args.max_height}][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--match-filter", duration_filter,
        "--ignore-errors",
        "--no-warnings",
        # Search pages carry no useful metadata and slow every run down.
        "--no-write-info-json",
    ]

    if not args.force:
        cmd += ["--download-archive", args.archive]

    if args.browser:
        cmd += ["--cookies-from-browser", args.browser]

    if args.dry_run:
        # Resolve the search without fetching any media.
        cmd += ["--skip-download", "--print", "%(duration>%H:%M:%S)s  %(title)s"]

    # flush: yt-dlp writes straight to the terminal, so an unflushed heading
    # would appear after the results it is meant to introduce.
    print(f"\n🔎 {dance}: searching for {count} clip(s) - \"{query}\"", flush=True)

    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        # --ignore-errors means a non-zero exit usually signals that some
        # results failed, not that the whole search did.
        print(f"⚠️  {dance}: yt-dlp exited with {e.returncode} - some clips may be missing.")
        return False


def report_pool(output_dir):
    """Summarise what the pool holds now, grouped by the leading dance type."""
    if not os.path.isdir(output_dir):
        return

    counts = {}
    for filename in os.listdir(output_dir):
        if not filename.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".mkv")):
            continue
        match = re.match(r"\s*(.+?)\s+-\s+", filename)
        dance = match.group(1) if match else "(unrecognised)"
        counts[dance] = counts.get(dance, 0) + 1

    if not counts:
        print("\n⚠️  No clips in the pool yet.")
        return

    print("\n" + "=" * 40)
    print(f"🎬 VIDEO POOL: {output_dir}")
    print("=" * 40)
    for dance, count in sorted(counts.items()):
        print(f"  {dance:<25} | {count}")
    print("=" * 40)
    print(f"Use it with:  python process.py -v {output_dir}")


def main():
    args = parse_args()

    if not shutil.which("yt-dlp"):
        print("❌ Error: 'yt-dlp' is not installed.")
        return
    if not shutil.which("ffmpeg"):
        print("❌ Error: 'ffmpeg' is not installed (needed to merge video and audio).")
        return

    if not os.path.exists(args.list):
        print(f"Error: List file '{args.list}' not found.")
        print("Create one with a dance type per line, e.g.:\n  Waltz | 6\n  Rumba | 4 | showdance")
        return

    requests = parse_list(args.list, args.per_dance)
    if not requests:
        print(f"No dance types found in '{args.list}'.")
        return

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    total = sum(count for _, count, _ in requests)
    mode = "Previewing" if args.dry_run else "Collecting"
    print(f"{mode} up to {total} clip(s) across {len(requests)} dance type(s) into {args.output}")
    print(f"Duration filter: {args.min_duration}s - {args.max_duration}s", flush=True)

    for dance, count, extra in requests:
        collect_dance(dance, count, extra, args)

    if args.dry_run:
        print("\nDry run complete - nothing was downloaded.")
    else:
        report_pool(args.output)


if __name__ == "__main__":
    main()
