import os
import random
import subprocess
import re
import argparse
import sys
import json
import math
import time
from pydub import AudioSegment, effects
from PIL import Image, ImageDraw, ImageFont

# --- DANCE DEFINITIONS ---
SLOW_DANCES = ['Waltz', 'Foxtrot', 'Tango', 'Rumba', 'Bachata', 'Bolero', 'West Coast Swing', 'Country Two Step', 'Paso Doble', 'Night Club Two Step']
QUICK_DANCES = ['Chacha', 'Samba', 'Jive', 'Quickstep', 'Viennese Waltz', 'Salsa', 'Merengue', 'Hustle', 'Swing', 'Lindy Hop', 'Charleston']
STANDARD_DANCES = ['Waltz', 'Foxtrot', 'Tango', 'Viennese Waltz', 'Quickstep']

def parse_args():
    parser = argparse.ArgumentParser(description="Generate a Dance Party Video Playlist")
    parser.add_argument("--source", "-s", default="./input_mp3s", help="Path to source MP3s")
    parser.add_argument("--output", "-o", default="./output_mp4s", help="Path to output folder")
    parser.add_argument("--config", "-cfg", default="dance_config.json", help="Path to weights JSON")
    parser.add_argument("--count", "-c", type=int, default=20, help="Number of songs")
    
    # Export Flags
    parser.add_argument("--mp3", action="store_true", help="If set, also export processed MP3 files")
    parser.add_argument("--output-mp3", default="./output_processed_mp3s", help="Path to output MP3 folder")

    # Audio Params
    parser.add_argument("--length-quick", type=int, default=150, help="Max length Quick (s)")
    parser.add_argument("--length-slow", type=int, default=180, help="Max length Slow (s)")
    parser.add_argument("--fade", type=int, default=3, help="Fade out (s)")
    parser.add_argument("--silence", type=int, default=8, help="Silence (s)")
    return parser.parse_args()

def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"Error: Config file '{config_path}' not found.")
        sys.exit(1)
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
            raw_weights = data.get('weights', {})
            return {k.title(): v for k, v in raw_weights.items()}
    except json.JSONDecodeError:
        print(f"Error: '{config_path}' is not valid JSON.")
        sys.exit(1)

def get_dance_type(filename):
    all_dances = SLOW_DANCES + QUICK_DANCES
    pattern = re.compile(r'(' + '|'.join(all_dances) + ')', re.IGNORECASE)
    match = pattern.search(filename)
    if match: return match.group(1).title() 
    return None

def parse_library(source_dir):
    library = {}
    if not os.path.exists(source_dir): return library

    count = 0
    for filename in os.listdir(source_dir):
        if not filename.lower().endswith(".mp3"): continue
        dtype = get_dance_type(filename)
        if not dtype: continue 

        if dtype not in library: library[dtype] = []
        library[dtype].append(filename)
        count += 1
    print(f"Parsed {count} songs into library.")
    return library

def calculate_global_quotas(target_count, weights, library):
    valid_weights = {k: v for k, v in weights.items() if k in library and library[k]}
    total_weight = sum(valid_weights.values())
    if total_weight == 0: return {}

    quotas = {}
    remainders = {}
    current_sum = 0
    
    for dtype, weight in valid_weights.items():
        share = (weight / total_weight) * target_count
        count = int(math.floor(share))
        quotas[dtype] = count
        remainders[dtype] = share - count
        current_sum += count
        
    remainder_needed = target_count - current_sum
    sorted_rem = sorted(remainders.items(), key=lambda x: x[1], reverse=True)
    
    for i in range(remainder_needed):
        dtype = sorted_rem[i][0]
        quotas[dtype] += 1

    return quotas

def arrange_abundance_aware(drafted_songs):
    print("Arranging playlist (Focus: Even Distribution for ALL types)...")
    final_playlist = []
    pool = list(drafted_songs)
    random.shuffle(pool) 
    
    last_speed = None
    last_type = None
    history_buffer = [] 
    HISTORY_LIMIT = 4

    while pool:
        best_candidate = None
        best_score = -999999
        total_remaining = len(pool)
        
        type_counts = {}
        for s in pool:
            t = get_dance_type(s)
            type_counts[t] = type_counts.get(t, 0) + 1

        for song in pool:
            score = 0
            dtype = get_dance_type(song)
            is_slow = any(d.lower() == dtype.lower() for d in SLOW_DANCES)
            speed = 'Slow' if is_slow else 'Quick'
            
            # 1. HISTORY PENALTY
            if dtype in history_buffer:
                score -= 10000 
            
            # 2. ABUNDANCE BONUS
            abundance_ratio = type_counts[dtype] / total_remaining
            score += (abundance_ratio * 2000)

            # 3. SPEED ALTERNATION
            if last_speed and speed != last_speed:
                score += 300
            elif last_speed and speed == last_speed:
                score -= 50

            if score > best_score:
                best_score = score
                best_candidate = song
        
        final_playlist.append(best_candidate)
        pool.remove(best_candidate)
        
        last_type = get_dance_type(best_candidate)
        is_slow_type = any(d.lower() == last_type.lower() for d in SLOW_DANCES)
        last_speed = 'Slow' if is_slow_type else 'Quick'
        
        history_buffer.append(last_type)
        if len(history_buffer) > HISTORY_LIMIT:
            history_buffer.pop(0)
            
    return final_playlist

def interactive_swap(playlist):
    while True:
        print("\n" + "="*60)
        print("📝 REVIEW PLAYLIST ORDER")
        print("="*60)
        for i, song in enumerate(playlist):
            idx = i + 1
            dtype = get_dance_type(song)
            clean_name = os.path.splitext(song)[0]
            print(f"{idx:02d}. [{dtype}] {clean_name}")
        print("="*60)
        
        print("\nOPTIONS:")
        print(" - Type '23-46' to swap song #23 and #46")
        print(" - Press ENTER to Accept and Start Generation")
        
        choice = input("\n> ").strip()
        
        if not choice:
            return playlist
        
        match = re.match(r"(\d+)[\s\W]+(\d+)", choice)
        if match:
            a = int(match.group(1)) - 1
            b = int(match.group(2)) - 1
            if 0 <= a < len(playlist) and 0 <= b < len(playlist):
                song_a = playlist[a]
                song_b = playlist[b]
                playlist[a] = song_b
                playlist[b] = song_a
                print(f"\n✅ SWAPPED: #{a+1} {get_dance_type(song_a)} <--> #{b+1} {get_dance_type(song_b)}")
            else:
                print("\n❌ Error: Song numbers out of range.")
        else:
             print("\n❌ Invalid command.")

# --- SILENCE STRIPPER ---
def strip_trailing_silence(audio_segment, silence_threshold=-45.0, chunk_size=50):
    """
    Scans audio from end to start. Returns audio trimmed to the last sound event.
    Threshold lowered to -45dB (Safer for dynamic songs).
    Requires audio to be NORMALIZED first.
    """
    reversed_audio = audio_segment.reverse()
    
    trim_ms = 0
    for i in range(0, len(reversed_audio), chunk_size):
        chunk = reversed_audio[i:i+chunk_size]
        if chunk.dBFS > silence_threshold:
            trim_ms = i
            break
            
    if trim_ms > 0:
        # Keep 500ms buffer
        keep_len = len(audio_segment) - trim_ms + 500
        keep_len = min(keep_len, len(audio_segment))
        return audio_segment[:keep_len]
        
    return audio_segment

def main():
    args = parse_args()
    print(f"Loading rules from: {args.config}")
    weights = load_config(args.config)
    
    if not os.path.exists(args.output): os.makedirs(args.output)
    if args.mp3 and not os.path.exists(args.output_mp3): os.makedirs(args.output_mp3)

    print(f"Scanning library at: {args.source}")
    library = parse_library(args.source)
    
    if not library:
        print("No valid songs found.")
        return

    # --- 1. CALCULATE TARGETS ---
    print(f"Calculating quotas based on Config Weights...")
    quotas = calculate_global_quotas(args.count, weights, library)
    
    # --- 2. SELECT SONGS ---
    drafted_songs = []
    used_songs_tracker = {} 

    for dtype, count in quotas.items():
        if count == 0: continue
        print(f"  - {dtype}: {count}")
        candidates = library[dtype]
        if dtype not in used_songs_tracker: used_songs_tracker[dtype] = set()
        
        picked = []
        available = list(candidates)
        random.shuffle(available)
        
        while len(picked) < count:
            if not available:
                available = list(candidates)
                random.shuffle(available)
            selection = available.pop()
            picked.append(selection)
            
        drafted_songs.extend(picked)

    # --- 3. RESERVE LAST DANCE ---
    reserved_last = None
    for i, song in enumerate(drafted_songs):
        if get_dance_type(song).lower() == 'waltz':
            reserved_last = drafted_songs.pop(i)
            print(f"💾 Reserved Last Dance: {reserved_last}")
            break
            
    if not reserved_last and 'Waltz' in library and library['Waltz']:
         reserved_last = random.choice(library['Waltz'])
         if drafted_songs: drafted_songs.pop()
         print(f"💾 Forced Last Dance: {reserved_last}")

    # --- 4. ARRANGE ---
    master_playlist = arrange_abundance_aware(drafted_songs)
    if reserved_last:
        master_playlist.append(reserved_last)

    # --- 5. INTERACTIVE REVIEW ---
    master_playlist = interactive_swap(master_playlist)

    # --- STATISTICS & GENERATION ---
    def print_statistics(playlist):
        stats = {}
        total = len(playlist)
        style_counts = {'Standard': 0, 'Latin': 0}
        speed_counts = {'Slow': 0, 'Quick': 0}
        total_seconds = 0
        
        for song in playlist:
            dtype = get_dance_type(song)
            stats[dtype] = stats.get(dtype, 0) + 1
            
            if any(d.lower() == dtype.lower() for d in STANDARD_DANCES):
                style_counts['Standard'] += 1
            else:
                style_counts['Latin'] += 1
                
            if any(d.lower() == dtype.lower() for d in SLOW_DANCES):
                speed_counts['Slow'] += 1
                total_seconds += (args.length_slow + args.silence)
            else:
                speed_counts['Quick'] += 1
                total_seconds += (args.length_quick + args.silence)
            
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        time_str = f"{hours}h {minutes}m {seconds}s (approx)"
            
        print("\n" + "="*40)
        print(f"📊 FINAL STATISTICS ({total} songs)")
        print(f"   ⏱️  Max Duration: {time_str}")
        print("-" * 36)
        print(f"   Standard: {style_counts['Standard']} | Latin: {style_counts['Latin']}")
        print(f"   Slow: {speed_counts['Slow']} | Quick: {speed_counts['Quick']}")
        print("="*40)
        print(f"{'DANCE TYPE':<20} | {'COUNT':<5} | {'%':<5}")
        print("-" * 36)
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
        for dtype, count in sorted_stats:
            percent = (count / total) * 100
            print(f"{dtype:<20} | {count:<5} | {percent:.1f}%")
        print("="*40 + "\n")

    if master_playlist:
        print_statistics(master_playlist)

    print("Starting batch generation...")
    
    def extract_metadata(filename):
        base = os.path.splitext(filename)[0].replace('_', ' ').strip()
        parts = base.split('-', 1)
        if len(parts) == 2: return {'type': parts[0].strip(), 'name': parts[1].strip()}
        return {'type': 'Dance', 'name': base}

    def generate_dynamic_cover(current_meta, next_meta, output_img_path):
        FONT_PATH_BOLD = "/Library/Fonts/Arial Bold.ttf"
        FONT_PATH_REG = "/Library/Fonts/Arial.ttf"
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

    def create_media(source_dir, output_dir, mp3_filename, index, cover_img_path, settings, export_mp3_path=None):
        input_mp3_path = os.path.join(source_dir, mp3_filename)
        temp_wav_path = os.path.join(output_dir, f"temp_{index}.wav")
        
        # 1. Load Audio
        audio = AudioSegment.from_mp3(input_mp3_path)
        
        # 2. NORMALIZE FIRST (Important Fix)
        # We maximize volume BEFORE checking for silence.
        # This makes the quiet ending of the Paso Doble 'loud enough' to survive the cut.
        audio = effects.normalize(audio)

        # 3. TRIM SILENCE (Safe Threshold)
        audio = strip_trailing_silence(audio)

        # 4. Check Length Cap
        if len(audio) > settings['length_ms']: 
            audio = audio[:settings['length_ms']]
            
        # 5. Fade & Add Silence
        audio = audio.fade_out(settings['fade_ms'])
        silence = AudioSegment.silent(duration=settings['silence_ms'])
        final_audio = audio + silence
        
        # 6. Export
        final_audio.export(temp_wav_path, format="wav")
        if export_mp3_path:
            final_audio.export(export_mp3_path, format="mp3")

        output_mp4_name = f"{index:02d}_{mp3_filename.replace('.mp3', '.mp4').replace(' ','_')}"
        output_mp4_path = os.path.join(output_dir, output_mp4_name)
        
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
               '-loop', '1', '-i', cover_img_path, '-i', temp_wav_path,
               '-c:v', 'libx264', '-tune', 'stillimage', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '256k', '-shortest', output_mp4_path]
        subprocess.run(cmd)
        os.remove(temp_wav_path)

    for i, mp3_filename in enumerate(master_playlist):
        seq_index = i + 1
        dtype = get_dance_type(mp3_filename)
        is_quick = any(d.lower() == dtype.lower() for d in QUICK_DANCES)
        current_length_sec = args.length_quick if is_quick else args.length_slow
        
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
        
        mp3_out_path = None
        if args.mp3:
            clean_name = f"{seq_index:02d}_{mp3_filename.replace(' ','_')}"
            mp3_out_path = os.path.join(args.output_mp3, clean_name)
            
        create_media(args.source, args.output, mp3_filename, seq_index, temp_img_path, track_settings, mp3_out_path)
        os.remove(temp_img_path)

    print(f"\nDone! Videos located in: {args.output}")
    if args.mp3:
        print(f"MP3s located in: {args.output_mp3}")

if __name__ == "__main__":
    main()