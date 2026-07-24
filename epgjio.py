import requests
import gzip
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

CHANNEL_API = "https://jiotvapi.cdn.jio.com/apis/v3.1/getMobileChannelList/get/?langId=6&os=android&devicetype=phone&usertype=jio&version=384&langId=6"
EPG_API = "https://jiotvapi.cdn.jio.com/apis/v1.3/getepg/get?offset=0&channel_id={}&langId=6"

HEADERS = {
    "User-Agent": "plaYtv/7.1",
    "Accept": "application/json"
}

LOGO_URL = "https://jiotvimages.cdn.jio.com/dare_images/images/"
SHOW_IMG_URL = "https://jiotvimages.cdn.jio.com/dare_images/shows/" # Added base URL for programs

# Helper to remove illegal XML characters
def clean_text(text):
    if not text:
        return ""
    return re.sub(r'[^\x09\x0A\x0D\x20-\x7E\x85\xA0-\uD7FF\uE000-\uFDCF\uFDE0-\uFFFD]', '', str(text))

def get_channels():
    print("Downloading channel list...")
    r = requests.get(CHANNEL_API, headers=HEADERS, timeout=30)
    data = r.json()
    
    channels = data.get("result", [])
    
    extra_ids = [1641]
    existing = {c["channel_id"] for c in channels}

    for cid in extra_ids:
        if cid not in existing:
            channels.append({
                "channel_id": cid,
                "channel_name": "Zee Keralam HD",
                "logoUrl": "Zee_Keralam_HD.png"
            })

    print("Channels found:", len(channels))
    return channels


def parse_time(ts):
    try:
        ts = int(ts)
        if ts > 9999999999:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts).strftime("%Y%m%d%H%M%S +0530")
    except Exception:
        return None


def fetch_epg(channel):
    cid = channel["channel_id"]
    try:
        url = EPG_API.format(cid)
        r = requests.get(url, headers=HEADERS, timeout=20)

        if "json" not in r.headers.get("Content-Type", "").lower():
            return None

        return {
            "channel": channel,
            "data": r.json()
        }
    except Exception:
        return None


# Init Root with basic XMLTV attributes
root = ET.Element("tv", {"generator-info-name": "JioTV-EPG"})
channels = get_channels()

# Create channel list
for ch in channels:
    cid = str(ch["channel_id"])
    c = ET.SubElement(root, "channel", {"id": cid})
    
    name = ch.get("channel_name") or f"Channel {cid}"
    ET.SubElement(c, "display-name", {"lang": "en"}).text = clean_text(name)

    if ch.get("logoUrl"):
        # Fix logo URL if it doesn't start with http
        logo_path = ch["logoUrl"]
        if not logo_path.startswith("http"):
            logo_path = LOGO_URL + logo_path
        ET.SubElement(c, "icon", {"src": logo_path})

print("Downloading EPG schedules (this may take a moment)...")

total_programs = 0

with ThreadPoolExecutor(max_workers=20) as executor:
    tasks = [executor.submit(fetch_epg, ch) for ch in channels]

    for task in as_completed(tasks):
        result = task.result()
        if not result:
            continue

        ch = result["channel"]
        data = result["data"]
        cid = ch["channel_id"]

        events = data.get("epg") or data.get("result") or []
        
        if isinstance(events, dict):
            events = events.get("events", [])

        for ev in events:
            start = ev.get("startEpoch") or ev.get("startTime") or ev.get("starttime")
            end = ev.get("endEpoch") or ev.get("endTime") or ev.get("endtime")

            if not start or not end:
                continue

            start_str = parse_time(start)
            end_str = parse_time(end)

            if not start_str or not end_str:
                continue

            p = ET.SubElement(root, "programme", {
                "start": start_str,
                "stop": end_str,
                "channel": str(cid)
            })

            title_text = ev.get("showname") or ev.get("title") or "Unknown Program"
            ET.SubElement(p, "title", {"lang": "en"}).text = clean_text(title_text)

            if ev.get("description"):
                ET.SubElement(p, "desc", {"lang": "en"}).text = clean_text(ev["description"])

            # ---- FIX THUMBNAIL URL HERE ----
            thumb = ev.get("episodeThumbnail") or ev.get("episodePoster") or ev.get("thumbnail")
            if thumb:
                thumb = str(thumb)
                # If it's just a filename, add the full Jio CDN link to it
                if not thumb.startswith("http"):
                    # sometimes it comes with a leading slash
                    if thumb.startswith("/"):
                        thumb = "https://jiotvimages.cdn.jio.com" + thumb
                    else:
                        thumb = SHOW_IMG_URL + thumb
                        
                ET.SubElement(p, "icon", {"src": thumb})
                
            total_programs += 1

print(f"Total programs fetched: {total_programs}")
print("Saving epg.xml...")

tree = ET.ElementTree(root)
tree.write("epg.xml", encoding="utf-8", xml_declaration=True)

with open("epg.xml", "rb") as f:
    with gzip.open("epg.xml.gz", "wb") as gz:
        gz.writelines(f)

print("DONE! File epg.xml.gz is ready.")
