#!/usr/bin/env python3
"""Refresh the DVD shelf on other-things.html from Zelia's Letterboxd.

Reads her public "recently watched" RSS feed and rewrites the row of DVD
spines so it always shows her latest films. Each spine links to that film
on her Letterboxd profile.

Run it any time to refresh:   python3 update_letterboxd.py
(A GitHub Action can run this on a schedule so the site updates itself.)
"""
import html
import os
import re
import urllib.request

USERNAME = "zelialerch"
RSS_URL = f"https://letterboxd.com/{USERNAME}/rss/"
HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "other-things.html")
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
    """Return the most recent films as [{'title':..., 'link':...}, ...]."""
    films = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        title = re.search(r"<letterboxd:filmTitle>(.*?)</letterboxd:filmTitle>", item, re.S)
        link = re.search(r"<link>(.*?)</link>", item, re.S)
        if not title or not link:
            continue  # skip list/diary items that aren't a single film
        films.append({
            "title": html.unescape(title.group(1)).strip(),
            "link": html.unescape(link.group(1)).strip(),
        })
        if len(films) >= N:
            break
    return films


def font_size(title):
    """Shrink the font so longer titles still fit down the spine."""
    length = len(title)
    if length <= 13:
        return 10
    if length <= 17:
        return 9
    return 8


def fit_title(title, max_len=22):
    title = title.upper()
    if len(title) > max_len:
        title = title[: max_len - 1].rstrip() + "…"  # ellipsis
    return title


def spine(slot, film):
    title = fit_title(film["title"])
    fs = font_size(title)
    w = slot["w"]
    cx = w / 2
    cy = -88
    band = ""
    if slot["band"]:
        band = f'<rect x="0" y="-150" width="{w}" height="16" fill="{slot["band"]}"/>'
    href = html.escape(film["link"], quote=True)
    label = html.escape(title)
    cx_s = f"{cx:g}"
    return (
        f'<a class="item" href="{href}" target="_blank" rel="noopener">'
        f'<g transform="translate({slot["x"]},{SHELF_Y})">'
        f'<rect x="0" y="-150" width="{w}" height="150" rx="2" fill="{slot["spine"]}"/>'
        f'{band}'
        f'<text x="{cx_s}" y="{cy}" transform="rotate(90 {cx_s} {cy})" text-anchor="middle" '
        f'font-family="Fraunces,serif" font-weight="600" font-size="{fs}" fill="{slot["text"]}">{label}</text>'
        f'</g></a>'
    )


def main():
    films = parse_films(fetch_feed())
    if not films:
        raise SystemExit("No films found in the Letterboxd feed — is the profile still public?")

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
