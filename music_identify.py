import argparse
import os
import subprocess
import re
import concurrent.futures

def recognize_single(file_path, cargo_path):
    """Helper function to run songrec on a single file."""
    try:
        try:
            cmd = ["songrec", "recognize", file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except FileNotFoundError:
            cmd = [cargo_path, "recognize", file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            
        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            if "could not recognize" in output.lower():
                return file_path, None
            else:
                return file_path, output
        else:
            return file_path, None
    except FileNotFoundError:
        return file_path, "MISSING_SONGREC"
    except subprocess.TimeoutExpired:
        return file_path, None
    except Exception:
        return file_path, None

def recognize_batch(files):
    """Uses the 'songrec' CLI tool to identify audio concurrently."""
    results = {}
    
    cargo_path = os.path.expanduser("~/.cargo/bin/songrec")
    
    total = len(files)
    
    # Use up to 8 simultaneous threads to process network requests in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_file = {executor.submit(recognize_single, fp, cargo_path): fp for fp in files}
        
        for future in concurrent.futures.as_completed(future_to_file):
            file_path, output = future.result()
            if output == "MISSING_SONGREC":
                return "MISSING_SONGREC"
            results[file_path] = output
            print(f"   ⏳ Analyzing... [{len(results)}/{total}]", end="\r", flush=True)
            
    print() # Add a newline when complete so the following prints start fresh
    return results

def sanitize_filename(name):
    """Removes illegal characters from filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def get_unique_filename(directory, filename):
    """Ensures we don't overwrite existing files."""
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(directory, new_filename)):
        new_filename = f"{base}_{counter}{ext}"
        counter += 1
    return new_filename

def identify_music(folder, prefix=None):
    if not os.path.exists(folder):
        print(f"❌ Error: Folder '{folder}' not found.")
        return

    supported_exts = ('.mp3', '.m4a', '.wav', '.mp4')
    files_to_process = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(supported_exts)])

    if not files_to_process:
        print(f"⚠️ No supported audio/video files found in '{folder}'.")
        return

    print(f"🔍 Identifying {len(files_to_process)} songs in '{folder}'...")
    results = recognize_batch(files_to_process)
    
    if results == "MISSING_SONGREC":
        print("   ⚠️ 'songrec' CLI not found. (Install via: brew install rust && cargo install songrec)")
        return
        
    for file_path in files_to_process:
        song_info = results.get(file_path)
        directory, filename = os.path.split(file_path)
        ext = os.path.splitext(filename)[1]
        
        if song_info:
            clean_song_info = sanitize_filename(song_info).replace(' ', '_')
            
            # Preserve starting numbers like "01_" if no prefix is given
            match = re.match(r'^(\d+)[_\-]', filename)
            idx_str = match.group(1) + "_" if match else ""
            
            new_final_name = f"{prefix}-{clean_song_info}{ext}" if prefix else f"{idx_str}{clean_song_info}{ext}"
            new_final_name = get_unique_filename(directory, new_final_name)
            new_output_path = os.path.join(directory, new_final_name)
            
            os.rename(file_path, new_output_path)
            print(f"   🎶 {filename} identified as: '{song_info}' -> {new_final_name}")
        else:
            if prefix and not filename.startswith(prefix):
                new_final_name = get_unique_filename(directory, f"{prefix}-{filename}")
                new_output_path = os.path.join(directory, new_final_name)
                os.rename(file_path, new_output_path)
                print(f"   ❓ Could not identify {filename} -> Renamed to {new_final_name}")
            else:
                print(f"   ❓ Could not identify {filename}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Identify music files and rename them using Shazam (songrec).", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--folder", "-f", required=True, help="Folder containing music files to identify")
    parser.add_argument("--prefix", "-p", help="Optional prefix for renamed files (e.g. 'Waltz')")
    args = parser.parse_args()
    
    identify_music(args.folder, args.prefix)