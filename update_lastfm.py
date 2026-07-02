#!/usr/bin/env python3
"""Refresh the record shelf on other-things.html from Zelia's Last.fm.

Fills the four records (TODAY / WEEK / MONTH / YEAR) with her most-played
song for each period, with the real album cover and a link to the track on
Last.fm. TODAY = most played in the last 24 hours (falls back to her most
recent listen if nothing was played today).

Needs the LASTFM_API_KEY environment variable (stored as a GitHub Actions
secret; never committed to the repo). If the key is missing or Last.fm is
unreachable, the script leaves the page untouched and exits cleanly so the
rest of the daily update still runs.
"""
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter

USERNAME = "zelialerch"
API = "https://ws.audioscrobbler.com/2.0/"
DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(DIR, "other-things.html")
COVERS_DIR = os.path.join(DIR, "covers")
# Last.fm serves this generic star image when a track has no real art
DEFAULT_ART_HASH = "2a96cbd8b46e442fc41c2b86b821562f"

SLOTS = [
    dict(key="today", label="TODAY", label_x=222, cover_x=184, vinyl_cx=256, accent="#c25b73"),
    dict(key="week", label="WEEK", label_x=300, cover_x=262, vinyl_cx=334, accent="#5f9072"),
    dict(key="month", label="MONTH", label_x=378, cover_x=340, vinyl_cx=412, accent="#c0922f"),
    dict(key="year", label="YEAR", label_x=456, cover_x=418, vinyl_cx=490, accent="#5f72a6"),
]
PERIODS = {"week": "7day", "month": "1month", "year": "12month"}


def call(method, **params):
    params.update(method=method, user=USERNAME, api_key=os.environ["LASTFM_API_KEY"], format="json")
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "zelia-website-shelf"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def clean_name(name):
    """Drop noisy suffixes like ' - Remastered 1994' for display."""
    return re.sub(r"\s*-\s*(((\d{4}\s+)?Remaster(ed)?)(\s+\d{4})?|Mono|Stereo)(\s+Version)?\s*$",
                  "", name, flags=re.I).strip()


def top_today():
    tracks = call("user.getrecenttracks", limit=200, **{"from": int(time.time()) - 86400})
    tracks = tracks["recenttracks"].get("track", [])
    if isinstance(tracks, dict):
        tracks = [tracks]
    tracks = [t for t in tracks if not t.get("@attr", {}).get("nowplaying")]
    if tracks:
        counts = Counter((t["artist"]["#text"], t["name"]) for t in tracks)
        artist, name = counts.most_common(1)[0][0]
        return dict(artist=artist, name=name)
    # nothing played in 24h: show the most recent listen instead
    recent = call("user.getrecenttracks", limit=1)["recenttracks"]["track"]
    t = recent[0] if isinstance(recent, list) else recent
    return dict(artist=t["artist"]["#text"], name=t["name"])


def top_period(period):
    t = call("user.gettoptracks", period=period, limit=1)["toptracks"]["track"][0]
    return dict(artist=t["artist"]["name"], name=t["name"])


def enrich(track):
    """Add the Last.fm track URL and a local album-art path (or None)."""
    def lookup(name):
        info = call("track.getinfo", artist=track["artist"], track=name, autocorrect=1)["track"]
        art = None
        for img in info.get("album", {}).get("image", []):
            if img["size"] == "extralarge" and img["#text"] and DEFAULT_ART_HASH not in img["#text"]:
                art = img["#text"]
        return info.get("url"), art

    url, art = lookup(track["name"])
    if art is None and clean_name(track["name"]) != track["name"]:
        # e.g. "Beast Of Burden - Remastered 1994" has no art, "Beast Of Burden" does
        url2, art = lookup(clean_name(track["name"]))
        url = url2 or url
    track["url"] = url or f"https://www.last.fm/user/{USERNAME}"
    track["art"] = art
    return track


def fit(text, widths):  # widths: list of (max_chars, font_size)
    for max_chars, fs in widths:
        if len(text) <= max_chars:
            return html.escape(text), fs
    max_chars, fs = widths[-1]
    return html.escape(text[: max_chars - 1].rstrip() + "…"), fs


def record_svg(slot, track):
    x, cx = slot["cover_x"], slot["label_x"]
    href = html.escape(track["url"], quote=True)
    song, song_fs = fit(clean_name(track["name"]), [(15, 9), (18, 8), (22, 7)])
    artist, artist_fs = fit(track["artist"], [(18, 7.5), (24, 6.5)])

    # album cover if we have one, otherwise a colored sleeve in the slot accent
    cover_path = None
    if track["art"]:
        local = os.path.join(COVERS_DIR, f"lastfm-{slot['key']}.jpg")
        try:
            req = urllib.request.Request(track["art"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(local, "wb") as f:
                f.write(data)
            # content-hash cache-buster: changes only when the artwork changes
            cover_path = f"covers/lastfm-{slot['key']}.jpg?v={hashlib.md5(data).hexdigest()[:8]}"
        except Exception:
            cover_path = None
    if cover_path:
        sleeve = (f'<image href="{cover_path}" x="{x}" y="94" width="76" height="76" '
                  f'preserveAspectRatio="xMidYMid slice"/>')
    else:
        sleeve = f'<rect x="{x}" y="94" width="76" height="76" rx="3" fill="{slot["accent"]}"/>'

    return (
        f'<a class="item" href="{href}" target="_blank" rel="noopener"><g>'
        f'<text x="{cx}" y="84" text-anchor="middle" font-family="Fraunces,serif" font-weight="600" '
        f'font-size="10.5" letter-spacing="2" fill="#9a8a6e">{slot["label"]}</text>'
        f'<circle cx="{slot["vinyl_cx"]}" cy="132" r="34" fill="url(#vinyl)"/>'
        f'<circle cx="{slot["vinyl_cx"]}" cy="132" r="11" fill="{slot["accent"]}"/>'
        f'<circle cx="{slot["vinyl_cx"]}" cy="132" r="2" fill="#1c1b20"/>'
        f'{sleeve}'
        f'<path d="M{x} 146 h76 v24 h-76 Z" fill="#000" opacity="0.45"/>'
        f'<rect x="{x}" y="94" width="76" height="76" fill="none" stroke="#000" stroke-opacity="0.2"/>'
        f'<text x="{cx}" y="158" text-anchor="middle" font-family="Fraunces,serif" font-weight="600" '
        f'font-size="{song_fs}" fill="#fff">{song}</text>'
        f'<text x="{cx}" y="167" text-anchor="middle" font-family="Newsreader,serif" font-style="italic" '
        f'font-size="{artist_fs}" fill="#fff" fill-opacity="0.85">{artist}</text>'
        f'</g></a>'
    )


def main():
    if not os.environ.get("LASTFM_API_KEY"):
        print("LASTFM_API_KEY not set — skipping Last.fm update.")
        return

    try:
        tracks = {"today": enrich(top_today())}
        for key, period in PERIODS.items():
            tracks[key] = enrich(top_period(period))
    except Exception as e:
        print(f"Last.fm unreachable ({e}) — leaving the shelf as it is.")
        return

    records = [record_svg(slot, tracks[slot["key"]]) for slot in SLOTS]
    block = "\n    " + "\n    ".join(records) + "\n    "

    with open(HTML_FILE, encoding="utf-8") as f:
        page = f.read()
    new_page, count = re.subn(
        r"(<!-- LASTFM:START -->).*?(<!-- LASTFM:END -->)",
        lambda m: m.group(1) + block + m.group(2),
        page,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("Could not find the LASTFM:START/END markers in other-things.html")
    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(new_page)
    for slot in SLOTS:
        t = tracks[slot["key"]]
        print(f"{slot['label']}: {t['name']} — {t['artist']}")


if __name__ == "__main__":
    main()
