import requests
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

CHANNEL_API = "https://jiotvapi.cdn.jio.com/apis/v3.1/getMobileChannelList/get/?langId=6&os=android&devicetype=phone&usertype=jio&version=384&langId=6"
EPG_API = "https://jiotvapi.cdn.jio.com/apis/v1.3/getepg/get?offset=0&channel_id={}&langId=6"

add = "https://ixvSri64WjPk9eDmw9RCkQNX:MxMGfG91568hizw2ZJSMChGK@in169.proxy.nordvpn.com:89"
proxy = {'https': add}
HEADERS = {
    "User-Agent": "plaYtv/7.1",
    "Accept": "application/json"
}

LOGO_URL = "https://jiotvimages.cdn.jio.com/dare_images/images/"


def get_channels():
    print("Downloading channel list...")
    r = requests.get(CHANNEL_API, headers=HEADERS, proxies=proxy, timeout=30)
    data = r.json()

    channels = data.get("result", [])

    # Add extra channel ID only
    extra_ids = [1641]
    existing = {c["channel_id"] for c in channels}

    for cid in extra_ids:
        if cid not in existing:
            channels.append({
                "channel_id": cid,
                "channel_name": "Zee Keralam HD",
                "logoUrl": "Zee_Keralam_HD.png"
            })

    print("Channels:", len(channels))
    return channels


def parse_time(ts):
    try:
        ts = int(ts)
        # If timestamp length indicates milliseconds (> year 2286), convert to seconds
        if ts > 9999999999:
            ts = ts / 1000.0

        return datetime.fromtimestamp(ts).strftime("%Y%m%d%H%M%S +0530")
    except Exception:
        return None


def fetch_epg(channel):
    cid = channel["channel_id"]
    try:
        url = EPG_API.format(cid)
        r = requests.get(url, headers=HEADERS, proxies=proxy, timeout=20)

        # Debug failed responses
        if "json" not in r.headers.get("Content-Type", "").lower():
            return None

        data = r.json()
        return {
            "channel": channel,
            "data": data
        }
    except Exception as e:
        print("EPG error", cid, e)
        return None


# Init Root with basic XMLTV attributes
root = ET.Element("tv", {"generator-info-name": "JioTV-EPG"})
channels = get_channels()

# Create channel list
for ch in channels:
    cid = str(ch["channel_id"])
    c = ET.SubElement(root, "channel", {"id": cid})

    name = ch.get("channel_name") or f"Channel {cid}"
    ET.SubElement(c, "display-name").text = name

    if ch.get("logoUrl"):
        ET.SubElement(c, "icon", {"src": LOGO_URL + ch["logoUrl"]})


print("Downloading EPG...")

with ThreadPoolExecutor(max_workers=20) as executor:
    tasks = [executor.submit(fetch_epg, ch) for ch in channels]

    for task in as_completed(tasks):
        result = task.result()
        if not result:
            continue

        ch = result["channel"]
        data = result["data"]
        cid = ch["channel_id"]

        if not ch.get("channel_name"):
            ch["channel_name"] = data.get("channel_name") or f"Channel {cid}"

        # FIX: The JioTV EPG endpoint uses the "epg" key, not "result"
        events = data.get("epg") or data.get("result") or []

        if isinstance(events, dict):
            events = events.get("events", [])

        for ev in events:
            # FIX: Fallback to Epoch keys which are standard for JioTV v1.3 EPG
            start = ev.get("startEpoch") or ev.get("startTime") or ev.get("starttime")
            end = ev.get("endEpoch") or ev.get("endTime") or ev.get("endtime")

            if not start or not end:
                continue

            # Parse times safely before appending to ElementTree
            start_str = parse_time(start)
            end_str = parse_time(end)

            # Skip if times couldn't be parsed
            if not start_str or not end_str:
                continue

            p = ET.SubElement(root, "programme", {
                "start": start_str,
                "stop": end_str,
                "channel": str(cid)
            })

            ET.SubElement(p, "title").text = ev.get("showname") or ev.get("title") or "Unknown Program"

            if ev.get("description"):
                ET.SubElement(p, "desc").text = ev["description"]

            thumb = ev.get("episodeThumbnail") or ev.get("episodePoster") or ev.get("thumbnail")
            if thumb:
                ET.SubElement(p, "icon", {"src": thumb})

print("Saving epg.xml")

tree = ET.ElementTree(root)
tree.write("epg.xml", encoding="utf-8", xml_declaration=True)

with open("jioepg.xml", "rb") as f:
    with gzip.open("epg.xml.gz", "wb") as gz:
        gz.writelines(f)

print("DONE")
