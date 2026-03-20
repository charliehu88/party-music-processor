import argparse
import subprocess
import re
import json

def sanitize_filename(name):
    """Removes illegal characters from filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def detect_dance_type(title, description=""):
    """Detect dance type from title or description."""
    text = (title + " " + (description or "")).lower()
    
    # Special cases first
    if "viennese" in text and "waltz" in text:
        return "Viennese Waltz"
    elif "waltz" in text:
        return "Waltz"
    
    # General keyword matching
    dance_keywords = {
        "Bachata": ["bachata"],
        "Bolero": ["bolero"],
        "Chacha": ["chacha", "cha cha", "cha-cha"],
        "Country Two Step": ["country two step", "country 2 step"],
        "Foxtrot": ["foxtrot"],
        "Hustle": ["hustle"],
        "Jive": ["jive"],
        "NightClub Two Step": ["nightclub two step", "night club 2 step"],
        "Paso Doble": ["paso doble"],
        "Quickstep": ["quickstep"],
        "Rumba": ["rumba"],
        "Salsa": ["salsa"],
        "Samba": ["samba"],
        "Tango": ["tango"],
        "West Coast Swing": ["west coast swing", "wcs"],
        "Merengue": ["merengue"]
    }
    
    for dance, keywords in dance_keywords.items():
        for kw in keywords:
            if kw in text:
                return dance
    
    # If not found, try to infer from common patterns
    if "swing" in text:
        return "West Coast Swing"
    if "two step" in text:
        return "Country Two Step"
    
    return "Unknown"

def main():
    parser = argparse.ArgumentParser(description="Extract YouTube playlist videos to a downloads.txt-style file.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--playlist", "-p", required=True, help="YouTube playlist URL")
    parser.add_argument("--file", "-f", required=True, help="Output file path")

    args = parser.parse_args()

    # Use yt-dlp to get playlist info as JSON
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        args.playlist
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error fetching playlist: {e}")
        return

    # Parse JSON lines
    entries = []
    for line in result.stdout.strip().split('\n'):
        if line.strip():
            try:
                entry = json.loads(line)
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    if not entries:
        print("No videos found in playlist.")
        return

    # Generate output lines
    lines = []
    for entry in entries:
        vid = entry.get('id')
        title = entry.get('title', 'Unknown Title')
        description = entry.get('description', '')
        if not vid:
            continue
        url = f"https://youtu.be/{vid}"
        dance_type = detect_dance_type(title, description)
        # Sanitize title
        clean_title = sanitize_filename(title)
        line = f"{url} | {dance_type} - {clean_title}"
        lines.append(line)

    # Write to file
    with open(args.file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"Wrote {len(lines)} entries to {args.file}")

if __name__ == "__main__":
    main()