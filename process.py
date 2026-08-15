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

# Fallback for dances whose config entry has no "category" set
UNCATEGORIZED = "uncategorized"

# The dance that opens and closes the party, when one has been selected
BOOKEND_DANCE = "Waltz"

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
    parser.add_argument("--video-pool", "-v", help="Path to dance video clips, named '<Dance Type> - <name>.mp4'. "
                                                   "Clips play behind each track instead of the static cover.")
    parser.add_argument("--intro", type=float, default=6.0,
                        help="Seconds the full text card stays up before dissolving into the dance video (--video-pool only)")

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
    if args.video_pool:
        args.video_pool = os.path.expanduser(args.video_pool)
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
        config = {k.title(): dict(v) for k, v in raw_dances.items()}

        # Normalize categories once, here, so the rest of the script can trust
        # them. Entries without a category still work - they just group together
        # under UNCATEGORIZED instead of alternating against anything.
        missing = []
        for dtype, info in config.items():
            category = str(info.get('category') or '').strip().lower()
            if not category:
                missing.append(dtype)
                category = UNCATEGORIZED
            info['category'] = category

        if missing:
            print(f"⚠️  No 'category' set in config for: {', '.join(sorted(missing))} "
                  f"(treated as '{UNCATEGORIZED}')")
        return config
    except json.JSONDecodeError:
        print(f"Error: '{config_path}' is not valid JSON.")
        sys.exit(1)

def get_category(dtype, dance_config):
    return dance_config.get(dtype, {}).get('category', UNCATEGORIZED)

def get_tempo(dtype, dance_config):
    return 'Slow' if str(dance_config.get(dtype, {}).get('tempo', '')).lower() == 'slow' else 'Quick'

def get_dance_type(filename, all_dances):
    # Sort by length descending so "Viennese Waltz" matches before "Waltz"
    sorted_dances = sorted(all_dances, key=len, reverse=True)
    escaped_dances = [re.escape(d) for d in sorted_dances]
    pattern = re.compile(r'(' + '|'.join(escaped_dances) + ')', re.IGNORECASE)
    
    match = pattern.search(filename)
    if match:
        return match.group(1).title()
    return None

def song_key(filename):
    """
    Identify a song by its name alone, ignoring case, padding and file format.

    Favorites are scanned before the general pool, so a track sitting in both
    places is claimed as a favorite and never picked a second time from the
    pool. Matching loosely matters here: the same song often differs by a
    stray space, a capital letter, or an .m4a next to an .mp3.
    """
    stem = os.path.splitext(filename)[0]
    return " ".join(stem.split()).casefold()

def parse_libraries(source_dir, favorite_path, all_dances):
    library = {}
    claimed = {}  # song_key -> where it was first taken from

    def add_song(filename, dir_path, is_favorite):
        """Returns 'added', 'duplicate' or 'unknown' (no dance type in the name)."""
        dtype = get_dance_type(filename, all_dances)
        if not dtype:
            return 'unknown'

        key = song_key(filename)
        if key in claimed:
            return 'duplicate'

        claimed[key] = 'favorites' if is_favorite else 'pool'
        library.setdefault(dtype, []).append({
            'filename': filename,
            'dir': dir_path,
            'is_favorite': is_favorite
        })
        return 'added'

    def add_songs_from_dir(dir_path, is_favorite):
        if not os.path.exists(dir_path):
            return 0
        count = skipped = 0
        for filename in os.listdir(dir_path):
            if not filename.lower().endswith((".mp3", ".m4a")):
                continue

            result = add_song(filename, dir_path, is_favorite)
            count += (result == 'added')
            skipped += (result == 'duplicate')

        if skipped and not is_favorite:
            print(f"Skipped {skipped} pool song{'s' if skipped != 1 else ''} already taken from favorites.")
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
                    
                result = add_song(filename, dir_path, is_favorite)
                if result == 'unknown':
                    print(f"Warning: Could not determine dance type for favorite song: {filename}")
                count += (result == 'added')
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

# --- SEQUENCING WEIGHTS ---
# Tempo alternation is the first preference; category alternation is honoured
# on a best-effort basis behind it, ahead of the balance nudge. Where the two
# conflict the tempo change wins. When a rule cannot be honoured at all (say
# only one category is left in the pool) the next rule down still decides the
# pick, so the playlist degrades gracefully instead of failing.
SCORE_DIFFERENT_TEMPO = 1000
SCORE_DIFFERENT_CATEGORY = 400
SCORE_ABUNDANCE = 200
PENALTY_RECENT_TYPE = 10000
HISTORY_LIMIT = 3

def arrange_playlist(drafted_songs, dance_config, all_dances, opener=None, closer=None):
    """
    Order the drafted songs so the floor keeps changing character.

    Greedy, one slot at a time, scoring every remaining song against the one
    just placed: a different tempo is worth most, a different category next,
    and repeating a dance type within HISTORY_LIMIT slots is heavily penalised.
    A small abundance term prefers whatever category is most plentiful in the
    remaining pool, which stops one category from piling up at the end - the
    usual failure mode of naive alternation.

    `opener` and `closer` are the songs already reserved for the first and last
    slots (if any). Neither is placed here, but the run-in to each is scored
    against it, so the bookends alternate with their neighbours too.
    """
    print("Arranging playlist (alternating category and tempo)...")
    pool = list(drafted_songs)
    random.shuffle(pool)

    sequence = []
    last_category = None
    last_tempo = None
    history = []

    if opener:
        opener_type = get_dance_type(opener['filename'], all_dances)
        last_category = get_category(opener_type, dance_config)
        last_tempo = get_tempo(opener_type, dance_config)
        history.append(opener_type)

    while pool:
        total_remaining = len(pool)
        category_counts = {}
        for song in pool:
            category = get_category(get_dance_type(song['filename'], all_dances), dance_config)
            category_counts[category] = category_counts.get(category, 0) + 1

        # On the final slot the reserved closer becomes the "next" neighbour
        following = closer if (total_remaining == 1 and closer) else None
        following_type = get_dance_type(following['filename'], all_dances) if following else None

        best_candidate = None
        best_score = None
        for song in pool:
            dtype = get_dance_type(song['filename'], all_dances)
            category = get_category(dtype, dance_config)
            tempo = get_tempo(dtype, dance_config)

            score = 0.0
            if dtype in history:
                score -= PENALTY_RECENT_TYPE
            if last_category is not None and category != last_category:
                score += SCORE_DIFFERENT_CATEGORY
            if last_tempo is not None and tempo != last_tempo:
                score += SCORE_DIFFERENT_TEMPO
            score += (category_counts[category] / total_remaining) * SCORE_ABUNDANCE

            if following_type:
                if category != get_category(following_type, dance_config):
                    score += SCORE_DIFFERENT_CATEGORY
                if tempo != get_tempo(following_type, dance_config):
                    score += SCORE_DIFFERENT_TEMPO
                if dtype == following_type:
                    score -= PENALTY_RECENT_TYPE

            # Break ties randomly so equally good playlists still vary run to run
            score += random.random()

            if best_score is None or score > best_score:
                best_score = score
                best_candidate = song

        sequence.append(best_candidate)
        pool.remove(best_candidate)

        placed_type = get_dance_type(best_candidate['filename'], all_dances)
        last_category = get_category(placed_type, dance_config)
        last_tempo = get_tempo(placed_type, dance_config)

        history.append(placed_type)
        if len(history) > HISTORY_LIMIT:
            history.pop(0)

    return sequence

# Relative cost of each rule being broken between two neighbouring songs.
# Same ranking as the scoring above: repeating a dance type is worst, then
# tempo, then category. One same-tempo pair costs more than two same-category
# pairs, so a trade that fixes tempo at the expense of category is taken.
COST_SAME_TYPE = 100
COST_SAME_TEMPO = 10
COST_SAME_CATEGORY = 4
MAX_POLISH_PASSES = 50

# How much worse the alternation may get before the opening Waltz is given up.
# One tempo break is a fair price for the ceremony of opening on a Waltz;
# beyond that the dancing wins. Set to 0 to make the Waltz yield on any cost
# at all, or raise it to insist on the opening Waltz more stubbornly.
BOOKEND_TOLERANCE = COST_SAME_TEMPO

def polish_sequence(sequence, dance_config, all_dances, pinned=()):
    """
    Clean up what the greedy pass could not see coming.

    Placing songs one at a time is myopic: it can strand a run of same-tempo
    songs at the end because the good partners were already used. This walks
    the finished order looking for changes that lower the total rule-breaking
    cost, and keeps going until nothing improves.

    Two kinds of move are tried. Swapping a pair fixes local mistakes, but on
    its own it gets stuck: once one rule is satisfied everywhere, no single
    swap can improve the other without breaking that boundary first. Reversing
    a stretch of the playlist changes only the two adjacencies at its ends,
    which is exactly the move needed to escape that.

    Positions in `pinned` (the opening and closing dances) never move.
    """
    order = list(sequence)
    pinned = set(pinned)

    # get_dance_type runs a regex over every dance name, far too slow to call
    # from inside a search loop - resolve each song's attributes once up front.
    attributes = {}
    for song in order:
        name = song['filename']
        if name not in attributes:
            dtype = get_dance_type(name, all_dances)
            attributes[name] = (dtype, get_category(dtype, dance_config), get_tempo(dtype, dance_config))

    def pair_cost(first, second):
        cost = 0
        if first[0] == second[0]:
            cost += COST_SAME_TYPE
        if first[1] == second[1]:
            cost += COST_SAME_CATEGORY
        if first[2] == second[2]:
            cost += COST_SAME_TEMPO
        return cost

    def total_cost(candidate):
        return sum(pair_cost(attributes[candidate[i]['filename']],
                             attributes[candidate[i + 1]['filename']])
                   for i in range(len(candidate) - 1))

    cost = total_cost(order)
    movable = [i for i in range(len(order)) if i not in pinned]

    for _ in range(MAX_POLISH_PASSES):
        improved = False

        for a_index, a in enumerate(movable):
            for b in movable[a_index + 1:]:
                order[a], order[b] = order[b], order[a]
                candidate_cost = total_cost(order)
                if candidate_cost < cost:
                    cost = candidate_cost
                    improved = True
                else:
                    order[a], order[b] = order[b], order[a]

        for start in movable:
            for end in movable:
                if end <= start + 1 or any(i in pinned for i in range(start, end + 1)):
                    continue
                order[start:end + 1] = order[start:end + 1][::-1]
                candidate_cost = total_cost(order)
                if candidate_cost < cost:
                    cost = candidate_cost
                    improved = True
                else:
                    order[start:end + 1] = order[start:end + 1][::-1]

        if not improved:
            break

    return order

def alternation_cost(sequence, dance_config, all_dances):
    """Total rule-breaking cost of a finished order. Lower is better."""
    types = [get_dance_type(song['filename'], all_dances) for song in sequence]
    cost = 0
    for previous, current in zip(types, types[1:]):
        if previous == current:
            cost += COST_SAME_TYPE
        if get_tempo(previous, dance_config) == get_tempo(current, dance_config):
            cost += COST_SAME_TEMPO
        if get_category(previous, dance_config) == get_category(current, dance_config):
            cost += COST_SAME_CATEGORY
    return cost

def build_sequence(drafted_songs, dance_config, all_dances, opener=None, closer=None):
    """Arrange, place the reserved bookends, then polish - pinning what is fixed."""
    sequence = arrange_playlist(drafted_songs, dance_config, all_dances,
                                opener=opener, closer=closer)
    if opener:
        sequence.insert(0, opener)
    if closer:
        sequence.append(closer)

    pinned = ([0] if opener else []) + ([len(sequence) - 1] if closer else [])
    return polish_sequence(sequence, dance_config, all_dances, pinned=pinned)

def reserve_bookends(drafted_songs, dance_config, all_dances):
    """
    Pull a Waltz out for the opening slot and another for the closing slot.

    Traditional last dance takes precedence: with only one Waltz drafted it
    closes the party rather than opening it. With none, both slots are left
    empty and the rule simply does not apply.
    """
    if dance_config.get(BOOKEND_DANCE, {}).get('weight', 0) <= 0:
        return None, None

    indices = [i for i, song in enumerate(drafted_songs)
               if (get_dance_type(song['filename'], all_dances) or '').lower() == BOOKEND_DANCE.lower()]
    if not indices:
        print(f"ℹ️  No {BOOKEND_DANCE} selected - skipping the opening/closing {BOOKEND_DANCE} rule.")
        return None, None

    chosen = random.sample(indices, min(2, len(indices)))
    closer = drafted_songs[chosen[0]]
    opener = drafted_songs[chosen[1]] if len(chosen) > 1 else None

    # Remove by index, highest first, so the earlier index stays valid
    for i in sorted(chosen, reverse=True):
        drafted_songs.pop(i)

    # The opening slot is only a candidate at this point - whether it survives
    # depends on what it does to the alternation (see main).
    print(f"💾 Reserved Last Dance: {closer['filename']}")
    return opener, closer

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
    category_counts = {}
    speed_counts = {'Slow': 0, 'Quick': 0}
    favorite_count = 0
    total_seconds = 0

    for song in playlist:
        dtype = get_dance_type(song['filename'], all_dances)
        stats[dtype] = stats.get(dtype, 0) + 1

        category = get_category(dtype, dance_config)
        category_counts[category] = category_counts.get(category, 0) + 1
        if song.get('is_favorite'):
            favorite_count += 1

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
    
    # How well the ordering rules held up - 0 repeats means perfect alternation
    category_repeats = tempo_repeats = 0
    for previous, current in zip(playlist, playlist[1:]):
        prev_type = get_dance_type(previous['filename'], all_dances)
        curr_type = get_dance_type(current['filename'], all_dances)
        if get_category(prev_type, dance_config) == get_category(curr_type, dance_config):
            category_repeats += 1
        if get_tempo(prev_type, dance_config) == get_tempo(curr_type, dance_config):
            tempo_repeats += 1

    output_lines = []
    output_lines.append("\n" + "="*40)
    output_lines.append(f"📊 FINAL STATISTICS ({total} songs)")
    output_lines.append(f"   ⏱️  Max Duration: {time_str}")
    output_lines.append("-" * 36)
    category_summary = " | ".join(f"{name.title()}: {count}"
                                 for name, count in sorted(category_counts.items()))
    output_lines.append(f"   {category_summary}")
    output_lines.append(f"   Slow: {speed_counts['Slow']} | Quick: {speed_counts['Quick']}")
    output_lines.append(f"   Favorites: {favorite_count} of {total}")
    output_lines.append(f"   Back-to-back same category: {category_repeats} | same tempo: {tempo_repeats}")
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

FONT_PATH = "./NotoSansSC-VariableFont_wght.ttf"
COVER_W, COVER_H = 1280, 720

# Where the "coming up next" block sits. The full card and the lower third that
# replaces it both draw from these numbers, so the block stays put when one
# dissolves into the other instead of sliding or doubling up on screen.
NEXT_DIVIDER_Y = 440
NEXT_LABEL_XY = (100, 470)
NEXT_TYPE_XY = (100, 530)
NEXT_NAME_XY = (100, 650)

C_NEXT_LABEL = (255, 105, 180)  # Vibrant Hot Pink
C_NEXT_TYPE = (0, 255, 255)     # Pure Neon Cyan
C_SONG = (255, 255, 255)


def load_fonts():
    """The shared font ladder for both the cover card and the lower third."""
    try:
        sizes = {'xxl': 150, 'xl': 110, 'l': 60, 'm': 45, 's': 40}
        return {name: ImageFont.truetype(FONT_PATH, size) for name, size in sizes.items()}
    except IOError:
        print("⚠️ Font not found! Falling back to default.")
        fallback = ImageFont.load_default()
        return {name: fallback for name in ('xxl', 'xl', 'l', 'm', 's')}


def draw_coming_up_next(draw, next_meta, fonts, stroke_width=0):
    """
    Draw the 'coming up next' block at the shared coordinates.

    stroke_width outlines the text in black, which the lower third needs to
    survive bright dance footage. The card sits on its own dark gradient and
    passes 0.
    """
    stroke = {'stroke_width': stroke_width, 'stroke_fill': (0, 0, 0)} if stroke_width else {}
    draw.text(NEXT_LABEL_XY, "COMING UP NEXT:", font=fonts['m'], fill=C_NEXT_LABEL, **stroke)
    draw.text(NEXT_TYPE_XY, next_meta['type'], font=fonts['xl'], fill=C_NEXT_TYPE, **stroke)
    draw.text(NEXT_NAME_XY, next_meta['name'], font=fonts['s'], fill=C_SONG, **stroke)


def generate_dynamic_cover(current_meta, next_meta, output_img_path):
    W, H = COVER_W, COVER_H
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

    fonts = load_fonts()

    c_label = (180, 180, 180)
    c_dance = (255, 215, 0)

    draw.text((100, 100), "NOW PLAYING:", font=fonts['m'], fill=c_label)
    draw.text((100, 160), current_meta['type'], font=fonts['xxl'], fill=c_dance)
    draw.text((100, 340), current_meta['name'], font=fonts['l'], fill=C_SONG)

    if next_meta:
        draw.line((50, NEXT_DIVIDER_Y, W - 50, NEXT_DIVIDER_Y), fill=(80, 80, 110), width=3)
        draw_coming_up_next(draw, next_meta, fonts)

    img.save(output_img_path)

# Clip pool file types. Anything ffmpeg can decode works; these are the
# containers yt-dlp and video_splitter.py actually produce.
VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".mkv")

# Seconds the text card takes to dissolve into the dance video, and the matching
# fade-in of the lower third that replaces it.
CARD_XFADE_SEC = 1.0

# Clips shorter than this are noise (stray thumbnails, broken downloads) and
# would need absurd repetition to fill a track.
MIN_CLIP_SEC = 3.0

# Stop chaining clips long before a pool of tiny files can spin forever.
MAX_CLIPS_PER_TRACK = 40


def parse_video_pool(pool_dir, all_dances):
    """
    Scan a flat folder of dance clips named '<Dance Type> - <name>.mp4'.

    Same naming rule as the music library, so `video_splitter.py --prefix
    "Waltz"` and `download.py --download-type mp4` both drop files in ready to
    use. Returns {dance_type: [(path, duration_sec), ...]}.
    """
    if not os.path.isdir(pool_dir):
        print(f"⚠️  Video pool '{pool_dir}' not found - falling back to static covers.")
        return {}

    clips = {}
    unknown = short = 0
    filenames = sorted(f for f in os.listdir(pool_dir) if f.lower().endswith(VIDEO_EXTENSIONS))

    print(f"Scanning {len(filenames)} clips in video pool: {pool_dir}")
    for filename in filenames:
        dtype = get_dance_type(filename, all_dances)
        if not dtype:
            unknown += 1
            continue

        path = os.path.join(pool_dir, filename)
        duration = get_video_duration(path)
        if duration < MIN_CLIP_SEC:
            short += 1
            continue

        clips.setdefault(dtype, []).append((path, duration))

    if unknown:
        print(f"  ⚠️  {unknown} clip(s) skipped - no dance type in the filename.")
    if short:
        print(f"  ⚠️  {short} clip(s) skipped - shorter than {MIN_CLIP_SEC:.0f}s or unreadable.")

    if clips:
        summary = ", ".join(f"{dtype}: {len(v)}" for dtype, v in sorted(clips.items()))
        print(f"  🎬 Clips available for {len(clips)} dance type(s) - {summary}")
    else:
        print("  ⚠️  No usable clips found - every track will use the static cover.")
    return clips


class VideoPool:
    """
    Hands out clips for a dance type, chaining as many as a track needs.

    Each type keeps its own shuffled queue that carries across songs, so a
    second Waltz shows different footage from the first and a clip only comes
    back once the rest of that dance's pool has been used.
    """

    def __init__(self, clips_by_type):
        self._clips = clips_by_type
        self._queue = {}

    def has(self, dtype):
        return bool(self._clips.get(dtype))

    def _next_clip(self, dtype):
        queue = self._queue.get(dtype)
        if not queue:
            queue = list(self._clips[dtype])
            random.shuffle(queue)
            self._queue[dtype] = queue
        return queue.pop()

    def take(self, dtype, needed_sec):
        """Return clip paths whose durations cover needed_sec, repeating if the pool is small."""
        if not self.has(dtype):
            return []

        chosen, covered = [], 0.0
        while covered < needed_sec and len(chosen) < MAX_CLIPS_PER_TRACK:
            path, duration = self._next_clip(dtype)
            chosen.append(path)
            covered += duration
        return chosen


def generate_lower_third(next_meta, output_img_path):
    """
    Transparent overlay that keeps 'COMING UP NEXT' on screen once the full
    text card has dissolved away.

    The block is drawn at the same coordinates the card uses, so it does not
    move during the dissolve - the now-playing half fades off and this half
    appears to simply stay. Dance footage is bright and busy, so here the text
    additionally gets a dark scrim behind it and a black outline; either alone
    would lose against a spotlit white dress.
    """
    W, H = COVER_W, COVER_H
    BAND_TOP = NEXT_DIVIDER_Y - 20

    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Scrim: ramps up over the first quarter of the band so there is no hard
    # line cutting across the video, then holds solid under all of the text.
    for y in range(BAND_TOP, H):
        progress = (y - BAND_TOP) / (H - BAND_TOP)
        alpha = int(235 * min(1.0, progress / 0.25))
        draw.line([(0, y), (W, y)], fill=(8, 6, 20, alpha))

    draw.line((50, NEXT_DIVIDER_Y, W - 50, NEXT_DIVIDER_Y), fill=(80, 80, 110), width=3)
    draw_coming_up_next(draw, next_meta, load_fonts(), stroke_width=4)

    img.save(output_img_path)


def build_video_filter(clip_count, intro_sec, has_lower_third):
    """
    Compose the per-track picture: dance clips underneath, the full text card
    on top for the intro, then the lower third for the rest.

    The card does not cut - it fades its alpha out over CARD_XFADE_SEC while
    the lower third fades in, so the video is already running underneath when
    the card clears.
    """
    parts = []

    # Input 0 is the card, input 1 the lower third when there is a next song.
    # Fill the frame rather than letterboxing: a party screen wants full bleed.
    clip_start = 2 if has_lower_third else 1
    for i in range(clip_count):
        parts.append(
            f"[{i + clip_start}:v]scale=1280:720:force_original_aspect_ratio=increase,"
            f"crop=1280:720,fps=30,setsar=1,format=yuv420p[c{i}]"
        )

    if clip_count > 1:
        chain = "".join(f"[c{i}]" for i in range(clip_count))
        parts.append(f"{chain}concat=n={clip_count}:v=1:a=0[bg]")
    else:
        parts.append("[c0]null[bg]")

    fade_out_at = intro_sec
    parts.append(f"[0:v]format=rgba,fade=t=out:st={fade_out_at}:d={CARD_XFADE_SEC}:alpha=1[card]")
    parts.append("[bg][card]overlay=0:0:eof_action=pass[withcard]")

    if has_lower_third:
        parts.append(f"[1:v]format=rgba,fade=t=in:st={fade_out_at}:d={CARD_XFADE_SEC}:alpha=1[low]")
        parts.append("[withcard][low]overlay=0:0:eof_action=pass,format=yuv420p[v]")
    else:
        parts.append("[withcard]format=yuv420p[v]")

    return ";".join(parts)


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

    # Only ask the pool for clips once the real track length is known, and take
    # a couple of seconds more than needed so rounding can never leave a black
    # tail at the end of the song.
    pool = settings.get('video_pool')
    clips = pool.take(settings['dance_type'], duration_sec + 2.0) if pool else []

    if clips:
        lower_img_path = settings.get('lower_img_path')
        # A very short track must still get its card before the dissolve.
        intro_sec = max(0.0, min(settings.get('intro_sec', 6.0), duration_sec - CARD_XFADE_SEC))

        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
               '-loop', '1', '-framerate', '30', '-i', cover_img_path]
        if lower_img_path:
            cmd += ['-loop', '1', '-framerate', '30', '-i', lower_img_path]
        for clip in clips:
            cmd += ['-i', clip]
        cmd += ['-i', temp_wav_path]

        audio_index = len(clips) + (2 if lower_img_path else 1)
        video_filter = build_video_filter(len(clips), intro_sec, bool(lower_img_path))
        filter_complex = f"{video_filter};[{audio_index}:a]apad[A]"

        cmd += ['-filter_complex', filter_complex,
                '-map', '[v]', '-map', '[A]',
                # Real footage, so stillimage tuning no longer applies. veryfast
                # keeps a 20-track party render to minutes rather than hours.
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '256k',
                '-ar', '44100', '-ac', '2',
                '-t', str(duration_sec), output_mp4_path]
    else:
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

    # Dance footage is optional: any type without clips keeps the static cover.
    video_pool = VideoPool(parse_video_pool(args.video_pool, all_dances)) if args.video_pool else None

    # --- 1. CALCULATE TARGETS ---
    print(f"Calculating quotas based on Config Weights...")
    quotas = calculate_global_quotas(args.count, dance_config, library)

    # --- 2. SELECT SONGS ---
    # Favorites are drawn first and exhaustively; the rest of the quota comes
    # from the general pool. Both draws use random.sample, so within each group
    # every song has exactly the same chance of being picked - no ordering,
    # folder or filename bias.
    drafted_songs = []
    fav_pool = {dtype: [s for s in songs if s['is_favorite']] for dtype, songs in library.items()}
    non_fav_pool = {dtype: [s for s in songs if not s['is_favorite']] for dtype, songs in library.items()}

    # Fulfill quotas as best as possible
    for dtype, count in quotas.items():
        if count == 0:
            continue

        favorites = fav_pool.get(dtype, [])
        others = non_fav_pool.get(dtype, [])

        picked_for_type = random.sample(favorites, min(count, len(favorites)))
        fav_used = len(picked_for_type)
        if len(picked_for_type) < count:
            needed = count - len(picked_for_type)
            picked_for_type += random.sample(others, min(needed, len(others)))

        fav_note = f" ({fav_used} favorite{'s' if fav_used != 1 else ''})" if fav_used else ""
        print(f"  - {dtype}: {count}{fav_note}")

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

    # --- 3. RESERVE OPENING AND LAST DANCE ---
    reserved_first, reserved_last = reserve_bookends(drafted_songs, dance_config, all_dances)

    # --- 4. ARRANGE ---
    master_playlist = build_sequence(drafted_songs, dance_config, all_dances,
                                     opener=reserved_first, closer=reserved_last)

    # Opening on a Waltz is a preference, not a requirement. Pinning it to the
    # front takes a song out of circulation at the point where alternation
    # needs it most, so build the playlist both ways and compare. A small
    # penalty is worth paying for the ceremony; a large one is not.
    # The closing Waltz stays put - the last dance is the tradition worth
    # protecting.
    if reserved_first:
        without_opener = build_sequence(drafted_songs + [reserved_first], dance_config,
                                        all_dances, opener=None, closer=reserved_last)
        cost_with = alternation_cost(master_playlist, dance_config, all_dances)
        cost_without = alternation_cost(without_opener, dance_config, all_dances)

        if cost_with - cost_without > BOOKEND_TOLERANCE:
            print(f"ℹ️  Opening on a {BOOKEND_DANCE} would break up the alternation too much - "
                  f"letting it fall where it fits instead.")
            master_playlist = without_opener
        else:
            print(f"💾 Reserved Opening Dance: {reserved_first['filename']}")

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

        # The lower third only earns its place once the card dissolves, so it is
        # built only when this track actually gets dance footage behind it.
        temp_lower_path = None
        if video_pool and video_pool.has(dtype):
            track_settings['video_pool'] = video_pool
            track_settings['dance_type'] = dtype
            track_settings['intro_sec'] = args.intro
            if next_meta:
                temp_lower_path = os.path.join(args.output, f"temp_lower_{seq_index}.png")
                generate_lower_third(next_meta, temp_lower_path)
                track_settings['lower_img_path'] = temp_lower_path

        mp3_out_path = None
        if args.mp3:
            # Use the same robust naming as MP4s, but change the extension
            clean_name = f"{seq_index:02d}_{os.path.splitext(audio_filename)[0].replace(' ','_')}.mp3"
            mp3_out_path = os.path.join(args.output_mp3, clean_name)
            
        create_media(song['dir'], args.output, audio_filename, seq_index, temp_img_path, track_settings, mp3_out_path)
        os.remove(temp_img_path)
        if temp_lower_path:
            os.remove(temp_lower_path)
        
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