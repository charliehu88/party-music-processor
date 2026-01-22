import os
import random
import subprocess
import re
import argparse
import sys
import json
from pydub import AudioSegment, effects
from PIL import Image, ImageDraw, ImageFont

# --- STATIC CONFIG ---
# Font Config (Mac Defaults)
FONT_PATH_BOLD = "/Library/Fonts/Arial Bold.ttf"
FONT_PATH_REG = "/Library/Fonts/Arial.ttf"

# Dance Classification
SLOW_DANCES = ['Waltz', 'Foxtrot', 'Rumba', 'Bachata', 'Bolero', 'West Coast Swing', 'Country Two Step', 'Paso Doble']
QUICK_DANCES = ['Chacha', 'Samba', 'Jive', 'Quickstep', 'Viennese Waltz', 'Salsa', 'Merengue', 'Hustle', 'Swing']

def parse_args():
    parser = argparse.ArgumentParser(description="Generate a Dance Party Video Playlist from MP3s")
    
    # Core Parameters
    parser.add_argument("--source", "-s", required=True, help="Path to folder containing source MP3s")
    parser.add_argument("--output", "-o", default="./output_mp4s", help="Path to output folder")
    parser.add_argument("--config", "-cfg", default="dance_config.json", help="Path to weights JSON file")
    parser.add_argument("--count", "-c", type=int, default=20, help="Number of songs to generate")

    # Audio Parameters (Seconds)
    # UPDATED: Separate lengths for Quick vs Slow
    parser.add_argument("--length-quick", type=int, default=150, help="Max length for Quick dances (Default: 150s = 2:30)")
    parser.add_argument("--length-slow", type=int, default=180, help="Max length for Slow dances (Default: 180s = 3:00)")
    
    parser.add_argument("--fade", type=int, default=3, help="Fade out duration in seconds (Default: 3)")
    parser.add_argument("--silence", type=int, default=8, help="Silence padding in seconds (Default: 8)")
    
    return parser.parse_args()

def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"Error: Config file '{config_path}' not found.")
        sys.exit(1)
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
            return data.get('weights', {})
    except json.JSONDecodeError:
        print(f"Error: '{config_path}' is not valid JSON.")
        sys.exit(1)

def parse_library(source_dir):
    library = {'Slow': [], 'Quick': []}
    dance_pattern = re.compile(r'(' + '|'.join(SLOW_DANCES + QUICK_DANCES) + ')', re.IGNORECASE)

    if not os.path.exists(source_dir):
        print(f"Error: Source directory '{source_dir}' not found.")
        sys.exit(1)

    for filename in os.listdir(source_dir):
        if not filename.lower().endswith(".mp3"): continue
        
        match = dance_pattern.search(filename)
        if match:
            dance_type = match.group(1)
            is_slow = any(d.lower() == dance_type.lower() for d in SLOW_DANCES)
            speed = 'Slow' if is_slow else 'Quick'
            library[speed].append(filename)
            
    return library

def extract_metadata(filename):
    base = os.path.splitext(filename)[0].replace('_', ' ').strip()
    parts = base.split('-', 1)
    if len(parts) == 2:
        return {'type': parts[0].strip(), 'name': parts[1].strip()}
    return {'type': 'Dance', 'name': base}

def select_song_weighted(pool, weights_config):
    if not pool: return None
    pool_dances = set()
    dance_pattern = re.compile(r'(' + '|'.join(weights_config.keys()) + ')', re.IGNORECASE)
    
    for song in pool:
        match = dance_pattern.search(song)
        if match: pool_dances.add(match.group(1).lower())
            
    if not pool_dances: return random.choice(pool)

    relevant_weights = {k: v for k, v in weights_config.items() if k.lower() in pool_dances}
    total = sum(relevant_weights.values())
    if total == 0: return random.choice(pool)
    
    keys = list(relevant_weights.keys())
    probs = [w/total for w in relevant_weights.values()]
    selected_type = random.choices(keys, weights=probs, k=1)[0]
    
    candidates = [s for s in pool if selected_type.lower() in s.lower()]
    return random.choice(candidates)

def generate_dynamic_cover(current_meta, next_meta, output_img_path):
    W, H = 1280, 720
    img = Image.new('RGB', (W, H), color=(20, 20, 30))
    draw = ImageDraw.Draw(img)

    try:
        font_xl = ImageFont.truetype(FONT_PATH_BOLD, 80)
        font_l = ImageFont.truetype(FONT_PATH_BOLD, 60)
        font_m = ImageFont.truetype(FONT_PATH_REG, 40)
        font_s = ImageFont.truetype(FONT_PATH_REG, 30)
    except IOError:
        font_xl = font_l = font_m = font_s = ImageFont.load_default()

    c_label = (180, 180, 180)
    c_dance = (255, 215, 0)
    c_song = (255, 255, 255)

    draw.text((100, 150), "NOW PLAYING:", font=font_m, fill=c_label)
    draw.text((100, 200), current_meta['type'], font=font_xl, fill=c_dance)
    draw.text((100, 300), current_meta['name'], font=font_l, fill=c_song)

    if next_meta:
        draw.line((50, 450, W-50, 450), fill=(50, 50, 70), width=3)
        draw.text((100, 480), "COMING UP NEXT:", font=font_s, fill=c_label)
        next_text = f"{next_meta['type']} - {next_meta['name']}"
        draw.text((100, 530), next_text, font=font_m, fill=(200, 200, 200))

    img.save(output_img_path)

def create_mp4(source_dir, output_dir, mp3_filename, index, cover_img_path, settings):
    input_mp3_path = os.path.join(source_dir, mp3_filename)
    temp_wav_path = os.path.join(output_dir, f"temp_{index}.wav")
    
    print(f"[{index}] Processing audio: {mp3_filename}...")
    audio = AudioSegment.from_mp3(input_mp3_path)
    audio = effects.normalize(audio)
    
    # Trim to specific length (Quick or Slow)
    if len(audio) > settings['length_ms']:
        audio = audio[:settings['length_ms']]
    
    audio = audio.fade_out(settings['fade_ms'])
    silence = AudioSegment.silent(duration=settings['silence_ms'])
    final_audio = audio + silence
    
    final_audio.export(temp_wav_path, format="wav")
    
    output_mp4_name = f"{index:02d}_{mp3_filename.replace('.mp3', '.mp4').replace(' ','_')}"
    output_mp4_path = os.path.join(output_dir, output_mp4_name)
    
    cmd = [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-loop', '1', '-i', cover_img_path,
        '-i', temp_wav_path,
        '-c:v', 'libx264', '-tune', 'stillimage', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '256k',
        '-shortest',
        output_mp4_path
    ]
    subprocess.run(cmd)
    os.remove(temp_wav_path)

def main():
    args = parse_args()
    
    print(f"Loading rules from: {args.config}")
    print(f"Settings: Quick={args.length_quick}s, Slow={args.length_slow}s")
    
    weights = load_config(args.config)
    if not os.path.exists(args.output):
        os.makedirs(args.output)

    print(f"Scanning library at: {args.source}")
    library = parse_library(args.source)
    print(f"Found {len(library['Quick'])} Quick and {len(library['Slow'])} Slow songs.")
    
    if not library['Quick'] and not library['Slow']:
        print("No valid songs found.")
        return

    # Sequence Generation
    print(f"Sequencing {args.count} songs...")
    master_playlist = []
    used_songs = set()
    next_is_quick = random.choice([True, False])

    for _ in range(args.count):
        pool_key = 'Quick' if next_is_quick else 'Slow'
        pool = [s for s in library[pool_key] if s not in used_songs]
        if not pool:
             pool = library[pool_key]
             if not pool: break 

        selected = select_song_weighted(pool, weights)
        master_playlist.append(selected)
        used_songs.add(selected)
        next_is_quick = not next_is_quick

    # Processing Loop
    print("Starting batch generation...")
    for i, mp3_filename in enumerate(master_playlist):
        seq_index = i + 1
        
        # Determine if this specific song is Quick or Slow
        # (We check the library again to be sure)
        is_quick = mp3_filename in library['Quick']
        current_length_sec = args.length_quick if is_quick else args.length_slow
        
        # Build settings for this track
        track_settings = {
            'length_ms': current_length_sec * 1000,
            'fade_ms': args.fade * 1000,
            'silence_ms': args.silence * 1000
        }

        current_meta = extract_metadata(mp3_filename)
        next_meta = None
        if i + 1 < len(master_playlist):
            next_filename = master_playlist[i+1]
            next_meta = extract_metadata(next_filename)

        temp_img_path = os.path.join(args.output, f"temp_cover_{seq_index}.png")
        generate_dynamic_cover(current_meta, next_meta, temp_img_path)
        
        create_mp4(args.source, args.output, mp3_filename, seq_index, temp_img_path, track_settings)
        os.remove(temp_img_path)

    print(f"\nDone! Videos located in: {args.output}")

if __name__ == "__main__":
    main()