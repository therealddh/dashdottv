import json
import os
import re
import urllib.request
from urllib.parse import urlparse

def get_channel_data(file_path):
    """Parses local M3U8 file to extract channel logos and license keys by channel ID."""
    channel_data = {}
    current_id = None
    
    if not os.path.exists(file_path):
        print(f"Warning: '{file_path}' not found. Missing logos and DRM keys.")
        return channel_data

    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            
            # 1. Grab the ID and Logo
            if line.startswith("#EXTINF"):
                id_match = re.search(r'tvg-id="([^"]+)"', line)
                logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                
                if id_match:
                    current_id = id_match.group(1)
                    channel_data[current_id] = {}
                    
                    if logo_match:
                        channel_data[current_id]['logo'] = logo_match.group(1)
                        
            # 2. Grab the License Key and attach it to the current ID
            elif line.startswith("#KODIPROP:inputstream.adaptive.license_key=") and current_id:
                # Split the line and take the second part to avoid list assignment errors
                key_parts = line.split("=", 1)
                if len(key_parts) > 1:
                    channel_data[current_id]['license_key'] = key_parts
                
    return channel_data
    
def extract_name_from_url(url):
    """Extracts, cleans, and formats the channel name from the stream URL as a fallback."""
    def clean_name(raw_name):
        name = raw_name.replace("_MOB", "").replace("_", " ")
        if name.endswith(" MOB"):
            name = name[:-4]
        return name.strip()

    try:
        path = urlparse(url).path
        parts = [p for p in path.split('/') if p] 
        
        if 'WDVLive' in parts:
            idx = parts.index('WDVLive')
            if idx > 0:
                return clean_name(parts[idx - 1])
                
        if 'bpk-tv' in parts:
            idx = parts.index('bpk-tv')
            if idx + 1 < len(parts):
                return clean_name(parts[idx + 1])
                
        if len(parts) >= 2:
            return clean_name(parts[-2])
            
    except Exception:
        pass
        
    return "Unknown Channel"

def generate_m3u_from_url(jio_url, meta_file, cplay_file, output_file):
    print(f"Fetching stream data from {jio_url}...")
    try:
        req = urllib.request.Request(jio_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            if response.status != 200:
                print(f"Error fetching URL: HTTP Status {response.status}")
                return
            raw_data = response.read().decode('utf-8')
            jio_data = json.loads(raw_data)
    except Exception as e:
        print(f"Error fetching or parsing the URL data: {e}")
        return

    # Load Metadata from meta.txt
    meta_data = []
    if not os.path.exists(meta_file):
        print(f"Warning: {meta_file} not found. Proceeding without metadata.")
    else:
        with open(meta_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if content:
                try:
                    meta_data = json.loads(content)
                except json.JSONDecodeError:
                    print(f"Error parsing {meta_file}. Ensure it is valid JSON.")
            
    meta_dict = {str(item.get("tvg-id")): item for item in meta_data}
    
    # Load cplaytv data ONCE outside the loop to get logos and keys efficiently
    print(f"Extracting logos and DRM keys from {cplay_file}...")
    cplay_channels = get_channel_data(cplay_file)
    
    with open(output_file, 'w', encoding='utf-8') as out:
        out.write("#EXTM3U\n")
        
        for channel_id, stream_info in jio_data.items():
            url = stream_info.get("url", "")
            if not url:
                continue
                
            meta_info = meta_dict.get(str(channel_id), {})
            cplay_info = cplay_channels.get(str(channel_id), {})
            
            # 1. Determine Name and Group (from meta.txt or URL fallback)
            if not meta_info:
                name = extract_name_from_url(url).replace(" BTS", "")
                group = "Unknown"
            else:
                name = meta_info.get("channel-name", "").replace(" BTS", "")
                if not name:
                    name = extract_name_from_url(url).replace(" BTS", "")
                group = meta_info.get("group-title", "Unknown")

            # 2. Determine Logo (Strictly from cplaytv.m3u8, fallback to empty)
            logo = cplay_info.get("logo", "")
            
            # Form the EXTINF line
            extinf = f'#EXTINF:-1 tvg-id="{channel_id}" tvg-logo="{logo}" group-title="{group}",{name}\n'
            
            # Base DRM properties required for inputstream.adaptive
            base_drm_props = (
                '#KODIPROP:inputstream=inputstream.adaptive\n'
                '#KODIPROP:inputstream.adaptive.manifest_type=mpd\n'
                '#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
            )
            
            # 3. Determine License Key (Strictly from cplaytv.m3u8, fallback to webplay API if missing)
            license_key = cplay_info.get('license_key', f'https://temp.webplay.fun/jtv/key.php?id={channel_id}')
            drm_props = base_drm_props + f'#KODIPROP:inputstream.adaptive.license_key={license_key}\n'
            
            # Write all parts to the final M3U file
            out.write(extinf)
            out.write(drm_props)
            out.write(url + "\n\n")
            
    print(f"Success! M3U playlist generated as '{output_file}'.")

if __name__ == "__main__":
    # Absolute paths ensure this runs perfectly in GitHub Actions environments
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    JIO_URL = "https://jo-json.vodep39240327.workers.dev/"
    META_FILENAME = os.path.join(BASE_DIR, "meta.txt")
    CPLAY_FILENAME = os.path.join(BASE_DIR, "cplaytv.m3u8")
    OUTPUT_FILENAME = os.path.join(BASE_DIR, "jiotvpl.m3u")
    
    generate_m3u_from_url(JIO_URL, META_FILENAME, CPLAY_FILENAME, OUTPUT_FILENAME)
