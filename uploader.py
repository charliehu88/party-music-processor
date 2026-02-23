import os
import datetime
import argparse
import subprocess
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

# --- CONSTANTS ---
CLIENT_SECRETS_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/youtube.upload"]
FFMPEG_LIST_FILE = "ffmpeg_list.txt"

def parse_args():
    today = datetime.date.today().strftime('%Y-%m-%d')
    
    parser = argparse.ArgumentParser(description="Merge MP4s, Upload to YouTube, and add to Playlist.")
    
    parser.add_argument("--folder", "-i", default="./output_mp4s", 
                        help="Input folder containing the song MP4s (default: ./output_mp4s)")

    parser.add_argument("--file", "-f", default="Full_Party_Mix.mp4", 
                        help="Filename for the merged output video (default: Full_Party_Mix.mp4)")
    
    parser.add_argument("--title", "-t", default=f"Dance Party Mix {today}", 
                        help="Title of the uploaded video")
    
    parser.add_argument("--playlist", "-p", default=f"Dance Parties {today}", 
                        help="Name of the playlist (creates if not exists)")
    
    parser.add_argument("--privacy", choices=['private', 'unlisted', 'public'], default='unlisted',
                        help="Privacy level (default: unlisted)")

    return parser.parse_args()

def get_video_duration(file_path):
    """Returns duration in seconds using ffprobe."""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
           "-of", "default=noprint_wrappers=1:nokey=1", file_path]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return float(result.stdout)
    except:
        return 0.0

def generate_merge_assets(input_folder):
    """
    1. Scans folder for MP4s.
    2. Creates ffmpeg_list.txt for merging.
    3. Generates Chapter Timestamps for description.
    """
    if not os.path.exists(input_folder):
        print(f"❌ Error: Input folder '{input_folder}' not found.")
        return None, None

    files = sorted([f for f in os.listdir(input_folder) if f.endswith(".mp4")])
    if not files:
        print(f"❌ Error: No MP4 files found in '{input_folder}'.")
        return None, None
    
    # Sort by number prefix (01_, 02_)
    files.sort(key=lambda x: int(x.split('_')[0]) if '_' in x else x)
    
    print(f"   Found {len(files)} clips to merge.")

    chapter_desc = "Auto-generated Dance Playlist.\n\n⏱️ CHAPTERS:\n"
    current_seconds = 0.0
    
    with open(FFMPEG_LIST_FILE, "w") as f:
        for filename in files:
            file_path = os.path.join(input_folder, filename)
            
            # 1. Write to FFmpeg list (Escape single quotes)
            safe_path = file_path.replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
            
            # 2. Format Timestamp
            m, s = divmod(int(current_seconds), 60)
            h, m = divmod(m, 60)
            time_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
            
            # 3. Clean Name
            name_part = os.path.splitext(filename)[0]
            if '_' in name_part:
                parts = name_part.split('_', 1)
                clean_name = parts[1].replace('_', ' ') if len(parts) > 1 else name_part
            else:
                clean_name = name_part
                
            chapter_desc += f"{time_str} {clean_name}\n"
            
            # 4. Add duration
            current_seconds += get_video_duration(file_path)

    return FFMPEG_LIST_FILE, chapter_desc

def merge_videos(list_file, output_filename):
    print(f"⏳ Merging videos into '{output_filename}'...")
    if os.path.exists(output_filename):
        os.remove(output_filename)

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_filename
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(output_filename):
        print(f"   ✅ Merge Success!")
        return True
    else:
        print("   ❌ Merge Failed.")
        return False

def get_authenticated_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)

def get_or_create_playlist(youtube, title, privacy_status):
    print(f"🔍 Checking Playlist: '{title}'...")
    
    request = youtube.playlists().list(
        part="snippet,id",
        mine=True,
        maxResults=50
    )
    response = request.execute()
    
    for item in response.get("items", []):
        if item["snippet"]["title"].lower() == title.lower():
            print(f"   ✅ Found existing (ID: {item['id']})")
            return item["id"]
            
    print(f"   ✨ Creating new playlist...")
    body = {
        "snippet": {"title": title, "description": "Created by Auto-Uploader"},
        "status": {"privacyStatus": privacy_status}
    }
    response = youtube.playlists().insert(part="snippet,status", body=body).execute()
    print(f"   ✅ Created (ID: {response['id']})")
    return response["id"]

def upload_video(youtube, file_path, title, description, privacy_status):
    print(f"🚀 Uploading '{title}' (Privacy: {privacy_status})...")
    
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["Dance", "Ballroom", "Party"],
            "categoryId": "10" 
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(file_path, chunksize=1024*1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    last_progress = 0
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            if progress > last_progress:
                print(f"   Uploading... {progress}%")
                last_progress = progress
                
    print(f"   🎉 Upload Complete! Video ID: {response['id']}")
    return response['id']

def add_video_to_playlist(youtube, video_id, playlist_id):
    print(f"🔗 Adding to playlist...")
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id}
        }
    }
    try:
        youtube.playlistItems().insert(part="snippet", body=body).execute()
        print(f"   ✅ Done!")
    except Exception as e:
        print(f"   ⚠️ Failed to add to playlist: {e}")

def main():
    args = parse_args()

    # 1. Prepare Content (Merge)
    print("📦 Preparing Content...")
    list_file, chapters_desc = generate_merge_assets(args.folder)
    if not list_file: return

    success = merge_videos(list_file, args.file)
    if not success: return

    # 2. Authenticate
    try:
        youtube = get_authenticated_service()
    except Exception as e:
        print(f"❌ Auth Error: {e}")
        return

    # 3. Upload
    video_id = upload_video(youtube, args.file, args.title, chapters_desc, args.privacy)

    # 4. Playlist
    playlist_id = get_or_create_playlist(youtube, args.playlist, args.privacy)
    add_video_to_playlist(youtube, video_id, playlist_id)

    # 5. Cleanup
    if os.path.exists(list_file): os.remove(list_file)
    print("\n" + "="*50)
    print(f"✨ SUCCESS! Link: https://youtu.be/{video_id}")
    print("="*50)

if __name__ == "__main__":
    main()