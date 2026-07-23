
import requests
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
Address = 'https://ixvSri64WjPk9eDmw9RCkQNX:MxMGfG91568hizw2ZJSMChGK@in169.proxy.nordvpn.com:89'
setz = {'https': Address}
CHANNEL_API = "https://jiotvapi.cdn.jio.com/apis/v3.1/getMobileChannelList/get/?langId=6&os=android&devicetype=phone&usertype=jio&version=384&langId=6"

EPG_API = "https://jiotvapi.cdn.jio.com/apis/v1.3/getepg/get?offset=0&channel_id={}&langId=6"

HEADERS = {
    "User-Agent": "plaYtv/7.1",
    "Accept": "application/json",
}

LOGO_URL = "https://jiotvimages.cdn.jio.com/dare_images/images/"


def get_channels():

    print("Downloading channel list...")

    r = requests.get(
        CHANNEL_API,
        headers=HEADERS,
        proxies=setz,
        timeout=30
    )

    data = r.json()

    channels = data.get("result", [])

    # Add extra channel ID only
    extra_ids = [1641]

    existing = {
        c["channel_id"]
        for c in channels
    }


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

        return datetime.fromtimestamp(
            int(ts)
        ).strftime("%Y%m%d%H%M%S +0530")

    except:

        return None



def fetch_epg(channel):

    cid = channel["channel_id"]

    try:

        url = EPG_API.format(cid)

        r = requests.get(
            url,
            headers=HEADERS,
            proxies=setz,
            timeout=20
        )


        # Debug failed responses
        if "json" not in r.headers.get(
            "Content-Type",
            ""
        ).lower():

            print(
                "Invalid EPG:",
                cid,
                r.text[:50]
            )

            return None


        data = r.json()


        return {
            "channel": channel,
            "data": data
        }


    except Exception as e:

        print(
            "EPG error",
            cid,
            e
        )

        return None



root = ET.Element(
    "tv"
)


channels = get_channels()



# Create channel list

for ch in channels:


    cid = str(
        ch["channel_id"]
    )


    c = ET.SubElement(
        root,
        "channel",
        {
            "id": cid
        }
    )


    name = (
        ch.get("channel_name")
        or
        f"Channel {cid}"
    )


    ET.SubElement(
        c,
        "display-name"
    ).text = name


    if ch.get("logoUrl"):

        ET.SubElement(
            c,
            "icon",
            {
                "src":
                LOGO_URL + ch["logoUrl"]
            }
        )




print("Downloading EPG...")



with ThreadPoolExecutor(
    max_workers=20
) as executor:


    tasks = [
        executor.submit(
            fetch_epg,
            ch
        )
        for ch in channels
    ]


    for task in as_completed(tasks):

        result = task.result()


        if not result:
            continue


        ch = result["channel"]

        data = result["data"]

        cid = ch["channel_id"]



        # update channel name from EPG if available

        if not ch.get("channel_name"):

            ch["channel_name"] = (
                data.get("channel_name")
                or
                f"Channel {cid}"
            )



        events = data.get(
            "result",
            []
        )


        if isinstance(events, dict):

            events = events.get(
                "events",
                []
            )


        for ev in events:


            start = (
                ev.get("startTime")
                or
                ev.get("starttime")
            )

            end = (
                ev.get("endTime")
                or
                ev.get("endtime")
            )


            if not start or not end:
                continue



            p = ET.SubElement(
                root,
                "programme",
                {
                    "start":
                    parse_time(start),

                    "stop":
                    parse_time(end),

                    "channel":
                    str(cid)
                }
            )


            ET.SubElement(
                p,
                "title"
            ).text = (
                ev.get("showname")
                or
                ev.get("title")
                or
                ""
            )


            if ev.get("description"):

                ET.SubElement(
                    p,
                    "desc"
                ).text = ev["description"]



            thumb = (
                ev.get("episodeThumbnail")
                or
                ev.get("episodePoster")
                or
                ev.get("thumbnail")
            )


            if thumb:

                ET.SubElement(
                    p,
                    "icon",
                    {
                        "src": thumb
                    }
                )



print("Saving epg.xml")


tree = ET.ElementTree(root)


tree.write(
    "epg.xml",
    encoding="utf-8",
    xml_declaration=True
)



with open(
    "epg.xml",
    "rb"
) as f:

    with gzip.open(
        "epg.xml.gz",
        "wb"
    ) as gz:

        gz.writelines(f)



print("DONE")
