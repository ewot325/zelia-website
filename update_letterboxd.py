#!/usr/bin/env python3
"""Refresh the DVD shelf on other-things.html from Zelia's Letterboxd.

Reads her public "recently watched" RSS feed and rewrites the row of DVD
spines so it always shows her latest films. Each spine links to the film's
general Letterboxd page (never her profile) and carries data attributes for
the hover popup: poster (saved to covers/lb-<slug>.jpg), title, director
(looked up on the keyless iTunes Search API; omitted if not found), and her
star rating from the feed.

Run it any time to refresh:   python3 update_letterboxd.py
(A GitHub Action can run this on a schedule so the site updates itself.)
"""
import glob
import html
import json
import os
import re
import urllib.parse
import urllib.request

USERNAME = "zelialerch"
RSS_URL = f"https://letterboxd.com/{USERNAME}/rss/"
DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(DIR, "other-things.html")
COVERS_DIR = os.path.join(DIR, "covers")
N = 10  # number of DVD spines on the shelf
SHELF_Y = 445  # y of the shelf-2 plank top the spines sit on

# Fixed spine "slots" — position, width and colours — that preserve the hand-tuned
# look of the shelf. The script only swaps in the film title + link for each slot.
SLOTS = [
    dict(x=150, w=20, spine="#2f3a44", band="#c25b73", text="#fff"),
    dict(x=172, w=18, spine="#7c5230", band="#e2a862", text="#fff"),
    dict(x=192, w=22, spine="#c0922f", band="#7a5716", text="#fff"),
    dict(x=216, w=18, spine="#3f5f8a", band="#7db2c9", text="#fff"),
    dict(x=236, w=20, spine="#b5533f", band="#e07a5f", text="#fff"),
    dict(x=258, w=16, spine="#5f9072", band=None,      text="#fff"),
    dict(x=276, w=20, spine="#8a5a86", band="#c58fbf", text="#fff"),
    dict(x=298, w=16, spine="#efe3c9", band=None,      text="#8a7444"),
    dict(x=316, w=18, spine="#4a4952", band="#b5533f", text="#fff"),
    dict(x=334, w=22, spine="#6fa8c0", band="#3f5f8a", text="#fff"),
]


def fetch_feed():
    req = urllib.request.Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_films(xml):
    """Return the most recent films with title/link/year/rating/poster/slug."""
    films = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        title = re.search(r"<letterboxd:filmTitle>(.*?)</letterboxd:filmTitle>", item, re.S)
        link = re.search(r"<link>(.*?)</link>", item, re.S)
        if not title or not link:
            continue  # skip list/diary items that aren't a single film
        # general film page, not Zelia's log of it — keeps her profile off the site
        url = html.unescape(link.group(1)).strip()
        url = re.sub(r"letterboxd\.com/[^/]+/film/", "letterboxd.com/film/", url)
        url = re.sub(r"/\d+/$", "/", url)
        year = re.search(r"<letterboxd:filmYear>(\d+)</letterboxd:filmYear>", item)
        rating = re.search(r"<letterboxd:memberRating>([\d.]+)</letterboxd:memberRating>", item)
        poster = re.search(r'<img src="([^"]+)"', item)
        slug = re.search(r"/film/([^/]+)/", url)
        films.append({
            "title": html.unescape(title.group(1)).strip(),
            "link": url,
            "year": int(year.group(1)) if year else None,
            "rating": float(rating.group(1)) if rating else None,
            "poster": html.unescape(poster.group(1)) if poster else None,
            "slug": slug.group(1) if slug else None,
        })
        if len(films) >= N:
            break
    return films


def stars(rating):
    """4.5 -> '★★★★½'"""
    if not rating:
        return ""
    full = int(rating)
    return "★" * full + ("½" if rating - full >= 0.5 else "")


def find_director(film):
    """Read the director from the film's own Letterboxd page metadata."""
    try:
        req = urllib.request.Request(film["link"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            page = resp.read().decode("utf-8", "replace")
        m = re.search(r'twitter:data1"\s+content="([^"]*)"', page)
        return html.unescape(m.group(1)).strip() if m else ""
    except Exception:
        return ""


def fetch_poster(film):
    """Save the poster locally; return the local path ('' if unavailable)."""
    if not film["poster"] or not film["slug"]:
        return ""
    local = f"covers/lb-{film['slug']}.jpg"
    path = os.path.join(DIR, local)
    if not os.path.exists(path):
        try:
            req = urllib.request.Request(film["poster"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            return ""
    return local


def spine(slot, film):
    title = film["title"].upper()
    w = slot["w"]
    cx = w / 2
    # text reads top-to-bottom and stays well below the top band (y=-150..-134)
    space = 110  # region from y=-122 down to y=-12
    fs = None
    for candidate in (10, 9, 8):
        if len(title) * candidate * 0.62 <= space:
            fs = candidate
            break
    if fs is None:
        fs = 8
        max_chars = int(space / (8 * 0.62))
        title = title[: max_chars - 1].rstrip() + "…"
    # textLength pins the rendered width so no font can push text past the spine
    t_len = min(len(title) * fs * 0.62, space)
    cy = -67  # centre of that region
    band = ""
    if slot["band"]:
        band = f'<rect x="0" y="-150" width="{w}" height="16" fill="{slot["band"]}"/>'
    href = html.escape(film["link"], quote=True)
    label = html.escape(title)
    data = (
        f' data-t="{html.escape(film["title"], quote=True)}"'
        f' data-d="{html.escape(film.get("director", ""), quote=True)}"'
        f' data-r="{stars(film["rating"])}"'
        f' data-c="{html.escape(film.get("poster_local", ""), quote=True)}"'
    ) if film.get("poster_local") else ""
    cx_s = f"{cx:g}"
    return (
        f'<a class="item" href="{href}" target="_blank" rel="noopener"{data} tabindex="0">'
        f'<g transform="translate({slot["x"]},{SHELF_Y})">'
        f'<rect x="0" y="-150" width="{w}" height="150" rx="2" fill="{slot["spine"]}"/>'
        f'{band}'
        f'<text x="{cx_s}" y="{cy}" transform="rotate(90 {cx_s} {cy})" text-anchor="middle" '
        f'textLength="{t_len:.0f}" lengthAdjust="spacingAndGlyphs" '
        f'font-family="Fraunces,serif" font-weight="600" font-size="{fs}" fill="{slot["text"]}">{label}</text>'
        f'</g></a>'
    )


def main():
    films = parse_films(fetch_feed())
    if not films:
        raise SystemExit("No films found in the Letterboxd feed — is the profile still public?")

    for film in films:
        film["poster_local"] = fetch_poster(film)
        film["director"] = find_director(film)

    # tidy up posters of films that fell off the shelf
    keep = {f"lb-{f['slug']}.jpg" for f in films if f["slug"]}
    for path in glob.glob(os.path.join(COVERS_DIR, "lb-*.jpg")):
        if os.path.basename(path) not in keep:
            os.remove(path)

    spines = [spine(SLOTS[i], films[i]) for i in range(min(N, len(films)))]
    block = "\n    " + "\n    ".join(spines) + "\n    "

    with open(HTML_FILE, encoding="utf-8") as f:
        page = f.read()

    new_page, count = re.subn(
        r"(<!-- LETTERBOXD:START -->).*?(<!-- LETTERBOXD:END -->)",
        lambda m: m.group(1) + block + m.group(2),
        page,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("Could not find the LETTERBOXD:START/END markers in other-things.html")

    if new_page != page:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(new_page)
        print(f"Updated shelf with {len(spines)} films:")
        for film in films[:len(spines)]:
            print(f"  - {film['title']}")
    else:
        print("Shelf already up to date.")


if __name__ == "__main__":
    main()
