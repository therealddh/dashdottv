import json
import os
import re
import urllib.request
from urllib.parse import urlparse

def load_channels(m3u_file):
    channels = {}

    with open(m3u_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    current_id = None
    current_logo = None

    for line in lines:
        line = line.strip()

        if line.startswith("#EXTINF"):
            id_match = re.search(r'tvg-id="([^"]+)"', line)
            logo_match = re.search(r'tvg-logo="([^"]+)"', line)
            group_match = re.search(r'group-title="([^"]+)"', line)

            current_id = id_match.group(1) if id_match else None
            current_logo = logo_match.group(1) if logo_match else ""
            current_group = group_match.group(1) if group_match else ""

        elif line.startswith("#KODIPROP:inputstream.adaptive.license_key="):
            license_key = line.split("=", 1)[1]

            if current_id:
                channels[current_id] = {
                    "logo": current_logo,
                    "group_title": current_group,
                    "license_key": license_key
                }

    return channels

def get_logo(CHANNELS, tvg_id):
    return CHANNELS.get(tvg_id, {}).get("logo")


def get_license_key(CHANNELS, tvg_id):
    return CHANNELS.get(tvg_id, {}).get("license_key")

def get_group_title(CHANNELS, tvg_id):
    return CHANNELS.get(tvg_id, {}).get("group_title")

def extract_name_from_url(url):
    """Extracts, cleans, and formats the channel name from the stream URL."""
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

    # Load Metadata
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

    # Load cplaytv data ONCE outside the loop
    CHANNELS = load_channels(cplay_file)

    with open(output_file, 'w', encoding='utf-8') as out:
        out.write("#EXTM3U\n")

        for channel_id, stream_info in jio_data.items():
            url = stream_info.get("url", "")
            if not url:
                continue

            meta_info = meta_dict.get(str(channel_id), {})
            #cplay_info = cplay_channels.get(str(channel_id), {})

            if not meta_info:
                name = extract_name_from_url(url).replace(" BTS", "")
                group = "Unknown"
            else:
                name = meta_info.get("channel-name", "").replace(" BTS", "")
                if not name:
                    name = extract_name_from_url(url).replace(" BTS", "")
                group = meta_info.get("group-title", "Unknown")

            # Fallback logic: Try meta.txt first, then cplaytv.m3u8, then empty string
            logo = get_logo(CHANNELS, name)
            group = get_group_title(CHANNELS, name)
            # A. Format the standard EXTINF line
            extinf = f'#EXTINF:-1 tvg-id="{channel_id}" tvg-logo="{logo}" group-title="{group}",{name}\n'

            # B. Add DRM properties
            base_drm_props = (
                '#KODIPROP:inputstream=inputstream.adaptive\n'
                '#KODIPROP:inputstream.adaptive.manifest_type=mpd\n'
                '#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
            )
            license_key = get_license_key(CHANNELS, name)
            drm_props = base_drm_props + f'#KODIPROP:inputstream.adaptive.license_key={license_key}\n'

            # D. Write blocks to file
            out.write(extinf)
            out.write(drm_props)
            out.write(url + "\n\n")

    print(f"Success! M3U playlist generated as '{output_file}'.")

if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    JIO_URL = os.environ["JIO_URL"]
    META_FILENAME = os.path.join(BASE_DIR, "meta.txt")
    CPLAY_FILENAME = os.path.join(BASE_DIR, "cplaytv.m3u")
    OUTPUT_FILENAME = os.path.join(BASE_DIR, "jiotv.m3u")

    generate_m3u_from_url(JIO_URL, META_FILENAME, CPLAY_FILENAME, OUTPUT_FILENAME)
