import os
import random
import subprocess
import re
import argparse
import sys
import json
import math
import time
import numpy as np
from pydub import AudioSegment, effects
from PIL import Image, ImageDraw, ImageFont

# Used only for the final statistics display
STANDARD_DANCES = ['Waltz', 'Foxtrot', 'Tango', 'Viennese Waltz', 'Quickstep']

def parse_args():
    # Added formatter_class to automatically display default values in -h output
    parser = argparse.ArgumentParser(
        description="Generate a Dance Party Video Playlist",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--source", "-s", default="~/music_dir/general-music-pool/input_mp3s_m4as", help="Path to source audio files (MP3s, M4As)")
    parser.add_argument("--favorite", "-f", help="Path to favorite audio files directory or a file containing a list of favorite song paths (prioritized)")
    parser.add_argument("--output", "-o", default="./output_mp4s", help="Path to output folder")
    parser.add_argument("--config", "-cfg", default="dance_config.json", help="Path to weights JSON")
    parser.add_argument("--count", "-c", type=int, default=20, help="Number of songs")
    
    # Export Flags
    parser.add_argument("--mp3", action="store_true", help="If set, also export processed MP3 files")
    parser.add_argument("--output-mp3", default="./output_processed_mp3s", help="Path to output MP3 folder")
    
    # Audio Params
    parser.add_argument("--length-quick", type=int, default=150, help="Max length Quick (s)")
    parser.add_argument("--length-slow", type=int, default=180, help="Max length Slow (s)")
    parser.add_argument("--fade", type=float, default=5, help="Fade out (s), added on top of the dance length rather than taken out of it")
    parser.add_argument("--fade-curve", type=float, default=FADE_CURVE,
                        help="Fade shape: 1.0 drops fast right away, higher stays near full volume longer before easing down")
    parser.add_argument("--silence", type=int, default=6, help="Silence (s)")

    args = parser.parse_args()
    # argparse leaves "~" as a literal, and the default source lives under $HOME
    args.source = os.path.expanduser(args.source)
    if args.favorite:
        args.favorite = os.path.expanduser(args.favorite)
    return args

def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"Error: Config file '{config_path}' not found.")
        sys.exit(1)
    try:
        with open(config_path, 'r') as f:
            data = json.load(f)
            
        raw_dances = data.get('dances', {})
        # Normalize to Title Case to match filenames consistently
        return {k.title(): v for k, v in raw_dances.items()}
    except json.JSONDecodeError:
        print(f"Error: '{config_path}' is not valid JSON.")
        sys.exit(1)

def get_dance_type(filename, all_dances):
    # Sort by length descending so "Viennese Waltz" matches before "Waltz"
    sorted_dances = sorted(all_dances, key=len, reverse=True)
    escaped_dances = [re.escape(d) for d in sorted_dances]
    pattern = re.compile(r'(' + '|'.join(escaped_dances) + ')', re.IGNORECASE)
    
    match = pattern.search(filename)
    if match:
        return match.group(1).title()
    return None

def parse_libraries(source_dir, favorite_path, all_dances):
    library = {}
    
    def add_songs_from_dir(dir_path, is_favorite):
        if not os.path.exists(dir_path):
            return 0
        count = 0
        for filename in os.listdir(dir_path):
            if not filename.lower().endswith((".mp3", ".m4a")):
                continue
                
            dtype = get_dance_type(filename, all_dances)
            if not dtype:
                continue
                
            if dtype not in library:
                library[dtype] = []
            # Avoid duplicates by filename
            if not any(song['filename'] == filename for song in library[dtype]):
                library[dtype].append({
                    'filename': filename,
                    'dir': dir_path,
                    'is_favorite': is_favorite
                })
                count += 1
        return count
    
    def add_songs_from_file(file_path, is_favorite):
        if not os.path.isfile(file_path):
            return 0
        count = 0
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                song_path = line.strip()
                if not song_path or song_path.startswith('#'):
                    continue
                
                # Handle quotes and user home directory (e.g. ~/music/"file.mp3")
                song_path = os.path.expanduser(song_path.strip().replace('"', ''))

                if not os.path.exists(song_path):
                    print(f"Warning: Favorite song not found: {song_path}")
                    continue

                dir_path, filename = os.path.split(song_path)

                if not filename.lower().endswith((".mp3", ".m4a")):
                    continue
                    
                dtype = get_dance_type(filename, all_dances)
                if not dtype:
                    print(f"Warning: Could not determine dance type for favorite song: {filename}")
                    continue
                    
                if dtype not in library:
                    library[dtype] = []
                # Avoid duplicates by filename
                if not any(song['filename'] == filename for song in library[dtype]):
                    library[dtype].append({
                        'filename': filename,
                        'dir': dir_path,
                        'is_favorite': is_favorite
                    })
                    count += 1
        return count
    
    total_count = 0
    if favorite_path:
        fav_count = 0
        if os.path.isdir(favorite_path):
            fav_count = add_songs_from_dir(favorite_path, True)
        elif os.path.isfile(favorite_path):
            fav_count = add_songs_from_file(favorite_path, True)
        else:
            # Only print warning if path was given but not found
            if not os.path.exists(favorite_path):
                 print(f"Warning: Favorite path '{favorite_path}' not found.")

        if fav_count > 0:
            print(f"Parsed {fav_count} favorite songs.")
            total_count += fav_count

    src_count = add_songs_from_dir(source_dir, False)
    print(f"Parsed {src_count} source songs.")
    total_count += src_count
    print(f"Total: {total_count} songs in library.")
    return library

def calculate_global_quotas(target_count, dance_config, library):
    # Extract only the 'weight' weights for calculation
    weights = {k: v.get('weight', 0) for k, v in dance_config.items()}
    valid_weights = {k: v for k, v in weights.items() if k in library and library[k]}
    
    total_weight = sum(valid_weights.values())
    if total_weight == 0:
        return {}
        
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

def arrange_abundance_aware(drafted_songs, dance_config, all_dances):
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
            t = get_dance_type(s['filename'], all_dances)
            type_counts[t] = type_counts.get(t, 0) + 1
            
        for song in pool:
            score = 0
            dtype = get_dance_type(song['filename'], all_dances)
            
            # Fetch tempo from dynamic config
            is_slow = dance_config.get(dtype, {}).get('tempo', '').lower() == 'slow'
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
        
        last_type = get_dance_type(best_candidate['filename'], all_dances)
        is_slow_type = dance_config.get(last_type, {}).get('tempo', '').lower() == 'slow'
        last_speed = 'Slow' if is_slow_type else 'Quick'
        
        history_buffer.append(last_type)
        if len(history_buffer) > HISTORY_LIMIT:
            history_buffer.pop(0)
            
    return final_playlist

def interactive_swap(playlist, all_dances):
    while True:
        print("\n" + "="*60)
        print("📝 REVIEW PLAYLIST ORDER")
        print("="*60)
        for i, song in enumerate(playlist):
            idx = i + 1
            dtype = get_dance_type(song['filename'], all_dances)
            clean_name = os.path.splitext(song['filename'])[0]
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
                print(f"\n✅ SWAPPED: #{a+1} {get_dance_type(song_a['filename'], all_dances)} <--> #{b+1} {get_dance_type(song_b['filename'], all_dances)}")
            else:
                print("\n❌ Error: Song numbers out of range.")
        else:
            print("\n❌ Invalid command.")

# --- SMOOTH FADE ---
# Level (dB) the fade has reached when the window ends. -60 dB is inaudible,
# so this is effectively where the music disappears.
FADE_FLOOR_DB = -60.0
# Shape of the descent, as an exponent on the dB ramp. 1.0 = constant dB/s,
# which lunges the moment the fade starts. Above 1.0 the slope begins at zero
# and accelerates, so the fade eases in gently and drifts away at the end.
# Higher = more of the window spent near full volume. See --fade-curve.
FADE_CURVE = 2.0

def smooth_fade_out(audio_segment, fade_ms, curve=FADE_CURVE, floor_db=FADE_FLOOR_DB):
    """
    Fade out over the full requested duration, sample by sample.

    pydub's built-in fade_out() ramps amplitude linearly: still only ~6 dB down
    at the halfway point, then a collapse in the last few hundred ms, with the
    same shape no matter how long the fade is - a brief dip followed by a hard
    stop. This ramps in *decibels* (what the ear tracks) and bends that ramp by
    `curve`, so the descent starts at zero slope and steepens. The opening
    second stays close to full volume instead of lunging downward, and the
    track thins out to nothing rather than being cut off.

    A short linear taper on the last few ms lands on true digital silence
    (already inaudible by then) so nothing clicks at the cut.
    """
    fade_ms = int(round(fade_ms))
    if fade_ms <= 0 or len(audio_segment) == 0:
        return audio_segment

    fade_ms = min(fade_ms, len(audio_segment))
    head = audio_segment[:len(audio_segment) - fade_ms]
    tail = audio_segment[len(audio_segment) - fade_ms:]

    samples = tail.get_array_of_samples()
    channels = max(1, tail.channels)
    frames = len(samples) // channels
    if frames < 2:
        return audio_segment

    dtype = np.dtype(samples.typecode)
    data = np.array(samples, dtype=np.float64)

    t = np.linspace(0.0, 1.0, frames, endpoint=True)
    gain_db = floor_db * (t ** max(0.1, curve))
    shaped = 10.0 ** (gain_db / 20.0)

    # Land on absolute silence over the final few ms to avoid a click.
    taper_frames = max(1, min(frames // 4, int(frames * 40.0 / fade_ms)))
    shaped[-taper_frames:] *= np.linspace(1.0, 0.0, taper_frames, endpoint=True)

    curve_samples = np.repeat(shaped, channels) if channels > 1 else shaped

    limits = np.iinfo(dtype)
    faded = np.clip(np.rint(data * curve_samples), limits.min, limits.max).astype(dtype)

    return head + tail._spawn(faded.tobytes())

# --- SILENCE STRIPPER ---
def strip_trailing_silence(audio_segment, silence_threshold=-45.0, chunk_size=50):
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

def print_statistics(playlist, dance_config, args, all_dances):
    stats = {}
    total = len(playlist)
    style_counts = {'Standard': 0, 'Latin': 0}
    speed_counts = {'Slow': 0, 'Quick': 0}
    total_seconds = 0
    
    for song in playlist:
        dtype = get_dance_type(song['filename'], all_dances)
        stats[dtype] = stats.get(dtype, 0) + 1
        
        if any(d.lower() == dtype.lower() for d in STANDARD_DANCES):
            style_counts['Standard'] += 1
        else:
            style_counts['Latin'] += 1
            
        # Fetch dynamic tempo and length
        is_slow = dance_config.get(dtype, {}).get('tempo', '').lower() == 'slow'
        custom_len = dance_config.get(dtype, {}).get('length', 0)
        
        if is_slow:
            speed_counts['Slow'] += 1
            song_len = custom_len if custom_len > 0 else args.length_slow
        else:
            speed_counts['Quick'] += 1
            song_len = custom_len if custom_len > 0 else args.length_quick
            
        # Fade sits on top of the danceable length, so it counts toward the total
        total_seconds += (song_len + args.fade + args.silence)

    total_seconds = int(round(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    time_str = f"{hours}h {minutes}m {seconds}s (approx)"
    
    output_lines = []
    output_lines.append("\n" + "="*40)
    output_lines.append(f"📊 FINAL STATISTICS ({total} songs)")
    output_lines.append(f"   ⏱️  Max Duration: {time_str}")
    output_lines.append("-" * 36)
    output_lines.append(f"   Standard: {style_counts['Standard']} | Latin: {style_counts['Latin']}")
    output_lines.append(f"   Slow: {speed_counts['Slow']} | Quick: {speed_counts['Quick']}")
    output_lines.append("="*40)
    output_lines.append(f"{'DANCE TYPE':<20} | {'COUNT':<5} | {'%':<5}")
    output_lines.append("-" * 36)
    
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    for dtype, count in sorted_stats:
        percent = (count / total) * 100
        output_lines.append(f"{dtype:<20} | {count:<5} | {percent:.1f}%")
    output_lines.append("="*40 + "\n")

    # Generate Playlist Order matching your preferred format
    output_lines.append("===========================================================")
    output_lines.append("📝 PLAYLIST ORDER")
    output_lines.append("===========================================================")
    for i, song in enumerate(playlist):
        dtype = get_dance_type(song['filename'], all_dances)
        clean_name = os.path.splitext(song['filename'])[0].strip()
        output_lines.append(f"{i+1:02d}. [{dtype}] {clean_name}")
    output_lines.append("===========================================================\n")

    output_text = "\n".join(output_lines)
    print(output_text)

    stats_file_path = os.path.join(args.output, "statistics.txt")
    with open(stats_file_path, "w", encoding="utf-8") as f:
        f.write(output_text)

def get_video_duration(file_path):
    """Get duration of video file in seconds using ffprobe"""
    try:
        cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
               '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return float(result.stdout.strip())
        else:
            print(f"Warning: Could not get duration for {file_path}")
            return 0
    except Exception as e:
        print(f"Warning: Error getting duration for {file_path}: {e}")
        return 0

def calculate_playlist_total_duration(output_dir):
    """Calculate total duration of all MP4 files in output directory"""
    if not os.path.exists(output_dir):
        return 0
    
    total_duration = 0
    mp4_files = [f for f in os.listdir(output_dir) if f.lower().endswith('.mp4')]
    mp4_files.sort()  # Sort to ensure consistent order
    
    print(f"\n🔍 Scanning {len(mp4_files)} generated MP4 files...")
    
    for mp4_file in mp4_files:
        file_path = os.path.join(output_dir, mp4_file)
        duration = get_video_duration(file_path)
        total_duration += duration
        print(f"  {mp4_file}: {duration:.1f}s")
    
    return total_duration

def extract_metadata(filename):
    base = os.path.splitext(filename)[0].replace('_', ' ').strip()
    parts = base.split('-', 1)
    if len(parts) == 2:
        return {'type': parts[0].strip(), 'name': parts[1].strip()}
    return {'type': 'Dance', 'name': base}

def generate_dynamic_cover(current_meta, next_meta, output_img_path):
    FONT_PATH = "./NotoSansSC-VariableFont_wght.ttf"
    W, H = 1280, 720
    img = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)
    
    # 1. Create a beautiful dark gradient background (Midnight Blue to Deep Purple)
    for y in range(H):
        r = int(15 + (45 - 15) * (y / H))
        g = int(10 + (20 - 10) * (y / H))
        b = int(35 + (70 - 35) * (y / H))
        draw.line([(0, y), (W, y)], fill=(r, g, b))
        
    # 2. Add subtle abstract decorative circles to give it a "party/dance" vibe
    draw.ellipse((800, -100, 1400, 500), outline=(60, 40, 90), width=10)
    draw.ellipse((900, 100, 1300, 500), outline=(50, 30, 80), width=5)
    draw.ellipse((-200, 400, 300, 900), outline=(30, 40, 80), width=8)

    try:
        font_xxl = ImageFont.truetype(FONT_PATH, 150)
        font_xl = ImageFont.truetype(FONT_PATH, 110)
        font_l = ImageFont.truetype(FONT_PATH, 60)
        font_m = ImageFont.truetype(FONT_PATH, 45)
        font_s = ImageFont.truetype(FONT_PATH, 40)
    except IOError:
        print("⚠️ Font not found! Falling back to default.")
        font_xxl = font_xl = font_l = font_m = font_s = ImageFont.load_default()
        
    c_label = (180, 180, 180)
    c_dance = (255, 215, 0)
    c_song = (255, 255, 255)
    
    draw.text((100, 100), "NOW PLAYING:", font=font_m, fill=c_label)
    draw.text((100, 160), current_meta['type'], font=font_xxl, fill=c_dance)
    draw.text((100, 340), current_meta['name'], font=font_l, fill=c_song)
    
    if next_meta:
        draw.line((50, 440, W-50, 440), fill=(80, 80, 110), width=3)
        c_next_label = (255, 105, 180) # Vibrant Hot Pink
        draw.text((100, 470), "COMING UP NEXT:", font=font_m, fill=c_next_label)
        c_next = (0, 255, 255) # Pure Neon Cyan
        draw.text((100, 530), next_meta['type'], font=font_xl, fill=c_next)
        draw.text((100, 650), next_meta['name'], font=font_s, fill=c_song)
        
    img.save(output_img_path)

def create_media(source_dir, output_dir, audio_filename, index, cover_img_path, settings, export_mp3_path=None):
    input_audio_path = os.path.join(source_dir, audio_filename)
    temp_wav_path = os.path.join(output_dir, f"temp_{index}.wav")
    
    audio = AudioSegment.from_file(input_audio_path)
    audio = effects.normalize(audio)
    audio = strip_trailing_silence(audio)
    
    # The configured length is full-volume dance time; the fade is appended on
    # top of it rather than eaten out of it, so a 120s dance stays 120s danceable.
    fade_ms = int(round(settings['fade_ms']))
    danceable_ms = settings['length_ms'] + fade_ms
    if len(audio) > danceable_ms:
        audio = audio[:danceable_ms]

    audio = smooth_fade_out(audio, fade_ms, settings.get('fade_curve', FADE_CURVE))
    silence = AudioSegment.silent(duration=settings['silence_ms'])
    final_audio = audio + silence
    
    final_audio.export(temp_wav_path, format="wav")
    if export_mp3_path:
        final_audio.export(export_mp3_path, format="mp3")
        
    output_mp4_name = f"{index:02d}_{os.path.splitext(audio_filename)[0].replace(' ','_')}.mp4"
    output_mp4_path = os.path.join(output_dir, output_mp4_name)
    
    # Calculate exact duration to prevent A/V drift during concatenation
    duration_sec = len(final_audio) / 1000.0
    
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', 
           '-loop', '1', '-framerate', '30', '-i', cover_img_path, 
           '-i', temp_wav_path, 
           '-filter_complex', '[1:a]apad[A]',
           '-map', '0:v', '-map', '[A]',
           '-c:v', 'libx264', '-tune', 'stillimage', '-pix_fmt', 'yuv420p', 
           '-c:a', 'aac', '-b:a', '256k', 
           '-ar', '44100', '-ac', '2',
           '-t', str(duration_sec), output_mp4_path]
    subprocess.run(cmd)
    os.remove(temp_wav_path)

def main():
    args = parse_args()
    print(f"Loading rules from: {args.config}")
    
    # Load dynamic config
    dance_config = load_config(args.config)
    all_dances = list(dance_config.keys())
    
    if not os.path.exists(args.output):
        os.makedirs(args.output)
    if args.mp3 and not os.path.exists(args.output_mp3):
        os.makedirs(args.output_mp3)
        
    print(f"Scanning libraries at: {args.source}" + (f" and {args.favorite}" if args.favorite else ""))
    library = parse_libraries(args.source, args.favorite, all_dances)
    if not library:
        print("No valid songs found.")
        return

    # --- 1. CALCULATE TARGETS ---
    print(f"Calculating quotas based on Config Weights...")
    quotas = calculate_global_quotas(args.count, dance_config, library)

    # --- 2. SELECT SONGS ---
    drafted_songs = []
    # Create a mutable pool of available songs, separating favs and non-favs
    fav_pool = {dtype: [s for s in songs if s['is_favorite']] for dtype, songs in library.items()}
    non_fav_pool = {dtype: [s for s in songs if not s['is_favorite']] for dtype, songs in library.items()}
    for p in fav_pool.values(): random.shuffle(p)
    for p in non_fav_pool.values(): random.shuffle(p)
    
    # Fulfill quotas as best as possible
    for dtype, count in quotas.items():
        if count == 0:
            continue
        print(f"  - {dtype}: {count}")
        
        picked_for_type = []
        
        # Pick from favorites first
        while len(picked_for_type) < count and fav_pool.get(dtype):
            picked_for_type.append(fav_pool[dtype].pop(0))
        
        # Then from non-favorites
        while len(picked_for_type) < count and non_fav_pool.get(dtype):
            picked_for_type.append(non_fav_pool[dtype].pop(0))
        
        if len(picked_for_type) < count:
            print(f"Warning: Not enough unique songs for {dtype}. Repeating to meet quota.")
            # All unique songs for this type have been used.
            # The pool of candidates for repetition is the entire library for this type.
            repeatable_candidates = library.get(dtype, [])
            if repeatable_candidates:
                needed = count - len(picked_for_type)
                # random.choices allows for replacement, which is what we want.
                repeated_picks = random.choices(repeatable_candidates, k=needed)
                picked_for_type.extend(repeated_picks)
            else:
                # This case should not be reachable due to how quotas are calculated.
                print(f"Error: No songs found for {dtype} at all, cannot meet quota.")
            
        drafted_songs.extend(picked_for_type)

    # --- 3. RESERVE LAST DANCE ---
    reserved_last = None
    is_waltz_in_config = dance_config.get('Waltz', {}).get('weight', 0) > 0
    
    if is_waltz_in_config:
        # Find a waltz in the drafted songs to reserve for the end
        waltz_indices = [i for i, song in enumerate(drafted_songs) if get_dance_type(song['filename'], all_dances).lower() == 'waltz']
        if waltz_indices:
            # Pick one of the drafted waltzes to be the last dance
            idx_to_pop = random.choice(waltz_indices)
            reserved_last = drafted_songs.pop(idx_to_pop)
            if reserved_last:
                print(f"💾 Reserved Last Dance: {reserved_last['filename']}")

    # --- 4. ARRANGE ---
    master_playlist = arrange_abundance_aware(drafted_songs, dance_config, all_dances)
    if reserved_last:
        master_playlist.append(reserved_last)

    # --- 5. INTERACTIVE REVIEW ---
    master_playlist = interactive_swap(master_playlist, all_dances)

    # --- STATISTICS & GENERATION ---
    if master_playlist:
        print_statistics(master_playlist, dance_config, args, all_dances)
        
    print("Starting batch generation...")
    
    for i, song in enumerate(master_playlist):
        seq_index = i + 1
        audio_filename = song['filename']
        dtype = get_dance_type(audio_filename, all_dances)
        
        # Fetch dynamic settings from JSON
        info = dance_config.get(dtype, {})
        custom_len = info.get('length', 0)
        is_quick = info.get('tempo', '').lower() == 'quick'
        
        if custom_len > 0:
            current_length_sec = custom_len
        else:
            current_length_sec = args.length_quick if is_quick else args.length_slow
            
        track_settings = {
            'length_ms': current_length_sec * 1000,
            'fade_ms': args.fade * 1000,
            'fade_curve': args.fade_curve,
            'silence_ms': args.silence * 1000
        }
        
        current_meta = extract_metadata(audio_filename)
        next_meta = None
        if i + 1 < len(master_playlist):
            next_song = master_playlist[i+1]
            next_filename = next_song['filename']
            next_meta = extract_metadata(next_filename)
            
        temp_img_path = os.path.join(args.output, f"temp_cover_{seq_index}.png")
        generate_dynamic_cover(current_meta, next_meta, temp_img_path)
        
        mp3_out_path = None
        if args.mp3:
            # Use the same robust naming as MP4s, but change the extension
            clean_name = f"{seq_index:02d}_{os.path.splitext(audio_filename)[0].replace(' ','_')}.mp3"
            mp3_out_path = os.path.join(args.output_mp3, clean_name)
            
        create_media(song['dir'], args.output, audio_filename, seq_index, temp_img_path, track_settings, mp3_out_path)
        os.remove(temp_img_path)
        
    print(f"\nDone! Videos located in: {args.output}")
    if args.mp3:
        print(f"MP3s located in: {args.output_mp3}")
    
    # Calculate and display exact total duration
    total_duration = calculate_playlist_total_duration(args.output)
    if total_duration > 0:
        hours = int(total_duration // 3600)
        minutes = int((total_duration % 3600) // 60)
        seconds = int(total_duration % 60)
        exact_msg = f"\n🎵 EXACT PLAYLIST DURATION: {hours}h {minutes}m {seconds}s ({total_duration:.1f} seconds total)"
        print(exact_msg)
        
        stats_file_path = os.path.join(args.output, "statistics.txt")
        with open(stats_file_path, "a", encoding="utf-8") as f:
            f.write(exact_msg + "\n")
    else:
        print("\n⚠️ Could not calculate playlist duration")

if __name__ == "__main__":
    main()