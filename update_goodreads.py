#!/usr/bin/env python3
"""Refresh the illustrated bookshelf on reading.html from Zelia's Goodreads.

Reads her public per-shelf RSS feeds and rewrites the labeled book spines:
  shelf 1 (WANT TO READ)      <- "to-read"            6 newest additions
  shelf 2 (READING NOW)       <- "currently-reading"  5 most recent
  shelf 3 (RECENTLY FINISHED) <- "read"               4 most recently finished

Each spine keeps its hand-tuned position/size/colors; only the title, author,
cover, and link change. Covers are saved to covers/gr-<book_id>.jpg. Slots
without a book become plain decorative spines. Decorative fillers and objects
(plant, sailboat, blocks...) live outside the markers and never change.

Run it any time to refresh:   python3 update_goodreads.py
(The daily GitHub Action runs this together with update_letterboxd.py.)
"""
import email.utils
import glob
import html
import os
import re
import urllib.request

USER_ID = "113010533"
DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(DIR, "reading.html")
COVERS_DIR = os.path.join(DIR, "covers")

# Fixed spine slots per shelf, matching the original hand-drawn composition.
# shape "round" = rounded-top spine (no cap). fg = title/author text color.
SHELVES = [
    dict(shelf="currently-reading", marker="S1", y=196, sort="added", slots=[
        dict(x=112, w=34, h=132, spine="#cf7d90", cap="#b96a7d", fg="#fff"),
        dict(x=148, w=28, h=112, spine="#5aa89c", cap=None, fg="#fff", shape="round"),
        dict(x=178, w=30, h=138, spine="#3f5f8a", cap="#324c70", fg="#fff"),
        dict(x=208, w=26, h=102, spine="#e4b24e", cap="#cf9a37", fg="#7a5716"),
        dict(x=234, w=30, h=122, spine="#93b184", cap="#7e9d70", fg="#3f5236"),
        dict(x=328, w=24, h=134, spine="#e4b24e", cap="#cf9a37", fg="#7a5716"),
    ]),
    dict(shelf="read", marker="S2", y=396, sort="read", slots=[
        dict(x=150, w=34, h=144, spine="#7a5a86", cap="#664a72", fg="#fff"),
        dict(x=186, w=30, h=124, spine="#6fa8c0", cap="#5b93ab", fg="#fff"),
        dict(x=216, w=26, h=112, spine="#e4b24e", cap="#cf9a37", fg="#7a5716"),
        dict(x=280, w=24, h=116, spine="#e9c15e", cap="#d3a940", fg="#7a5716", tilt=11),
        dict(x=328, w=24, h=136, spine="#b5533f", cap="#9c4432", fg="#fff"),
    ]),
    dict(shelf="to-read", marker="S3", y=596, sort="added", slots=[
        dict(x=108, w=30, h=130, spine="#8a5a86", cap="#744a72", fg="#fff"),
        dict(x=138, w=32, h=142, spine="#3f5f8a", cap="#324c70", fg="#fff"),
        dict(x=172, w=28, h=116, spine="#5aa89c", cap="#478a80", fg="#fff"),
        dict(x=200, w=28, h=126, spine="#efe3c9", cap="#ddceac", fg="#8a7444"),
    ]),
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def field(item, tag):
    m = re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", item, re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def parse_date(s):
    try:
        return email.utils.parsedate_to_datetime(s)
    except Exception:
        return None


def get_books(shelf, sort, n):
    xml = fetch(f"https://www.goodreads.com/review/list_rss/{USER_ID}?shelf={shelf}").decode("utf-8")
    books = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        book = dict(
            title=field(item, "title"),
            author=field(item, "author_name"),
            book_id=field(item, "book_id"),
            image=field(item, "book_large_image_url") or field(item, "book_image_url"),
            added=parse_date(field(item, "user_date_added")) or parse_date(field(item, "pubDate")),
            read=parse_date(field(item, "user_read_at")),
        )
        if book["title"] and book["book_id"]:
            books.append(book)
    epoch = parse_date("Thu, 01 Jan 1970 00:00:00 +0000")
    if sort == "read":
        books.sort(key=lambda b: b["read"] or b["added"] or epoch, reverse=True)
    else:
        books.sort(key=lambda b: b["added"] or epoch, reverse=True)
    return books[:n]


CHAR_W = 0.62  # approx width of one uppercase Fraunces-bold char, in font-size units


def slot_capacity(slot, book):
    """How much vertical room this slot offers this book's title."""
    return slot["h"] - 34


def assign_books(slots, books):
    """Pair longer titles with taller spines so fewer titles get cut short.
    Returns a list aligned with slots (None = no book for that slot)."""
    order = sorted(range(len(books)), key=lambda i: len(spine_title(books[i]["title"])), reverse=True)
    free = set(range(len(slots)))
    placed = [None] * len(slots)
    for i in order:
        best = max(free, key=lambda s: slot_capacity(slots[s], books[i]))
        placed[best] = books[i]
        free.remove(best)
    return placed


def spine_title(title):
    """Short title for the spine: drop subtitles after ':' or '('. """
    t = re.split(r"[:(]", title)[0].strip()
    return t.upper()


def surname(author):
    parts = author.split()
    return (parts[-1] if parts else "").upper()


def download_cover(book):
    """Save the cover locally; return the local path (or remote URL on failure)."""
    local = f"covers/gr-{book['book_id']}.jpg"
    path = os.path.join(DIR, local)
    if not os.path.exists(path):
        try:
            data = fetch(book["image"])
            with open(path, "wb") as f:
                f.write(data)
        except Exception:
            return book["image"]
    return local


def spine_svg(slot, book, y):
    w, h = slot["w"], slot["h"]
    cx = w / 2
    tilt = f' rotate({slot["tilt"]})' if slot.get("tilt") else ""
    if slot.get("shape") == "round":
        r = w / 2
        body = (f'<path d="M0 0 V-{h - 16} Q0 -{h} {r:g} -{h} '
                f'Q{w} -{h} {w} -{h - 16} V0 Z" fill="{slot["spine"]}"/>')
        top_pad = 8
    else:
        body = f'<rect x="0" y="-{h}" width="{w}" height="{h}" rx="4" fill="{slot["spine"]}"/>'
        if slot["cap"]:
            body += f'<rect x="0" y="-{h}" width="{w}" height="7" rx="3" fill="{slot["cap"]}"/>'
        top_pad = 11

    if book is None:  # more slots than books: plain decorative spine
        return f'<g transform="translate({slot["x"]},{y}){tilt}">{body}</g>'

    title = spine_title(book["title"])
    author = surname(book["author"])

    # title and author run top-to-bottom, side by side, centered on the spine;
    # generous 17px end margins keep tall letters clear of the caps
    space = h - 34
    fs = None
    for candidate in (10.5, 9.5, 8.5, 7.5, 6.5):
        if len(title) * candidate * CHAR_W <= space:
            fs = candidate
            break
    if fs is None:  # won't fit even small: truncate at a still-readable size
        fs = 7.5
        max_chars = int(space / (fs * CHAR_W))
        title = title[: max(1, max_chars - 1)].rstrip() + "…"
    a_max = int(space / (7 * CHAR_W))
    if len(author) > a_max:
        author = author[: max(1, a_max - 1)].rstrip() + "…"

    cy = -h / 2
    tx = cx + 5   # reading top-to-bottom, the title line sits right of the author line
    ax = cx - 6
    label = html.escape(title)
    a_label = html.escape(author)
    fg = slot["fg"]
    # textLength pins the rendered width so no font can push text past the spine
    t_len = min(len(title) * fs * CHAR_W, space)
    a_len_px = min(len(author) * 7 * (CHAR_W + 0.15), space)  # +letter-spacing
    text = (
        f'<text x="{tx:g}" y="{cy:g}" transform="rotate(90 {tx:g} {cy:g})" text-anchor="middle" '
        f'textLength="{t_len:.0f}" lengthAdjust="spacingAndGlyphs" '
        f'font-family="Fraunces,serif" font-weight="700" font-size="{fs:g}" fill="{fg}">{label}</text>'
        f'<text x="{ax:g}" y="{cy:g}" transform="rotate(90 {ax:g} {cy:g})" text-anchor="middle" '
        f'textLength="{a_len_px:.0f}" lengthAdjust="spacingAndGlyphs" '
        f'font-family="Fraunces,serif" font-weight="600" font-size="7" letter-spacing="1" '
        f'fill="{fg}" fill-opacity="0.75">{a_label}</text>'
    )
    href = html.escape(f"https://www.goodreads.com/book/show/{book['book_id']}", quote=True)
    cover = html.escape(download_cover(book), quote=True)
    data_t = html.escape(re.split(r"\(", book["title"])[0].strip(), quote=True)
    data_a = html.escape(book["author"], quote=True)
    return (
        f'<a class="book" href="{href}" target="_blank" rel="noopener" '
        f'data-t="{data_t}" data-a="{data_a}" data-c="{cover}" tabindex="0">'
        f'<g transform="translate({slot["x"]},{y}){tilt}">{body}{text}</g></a>'
    )


def main():
    with open(HTML_FILE, encoding="utf-8") as f:
        page = f.read()

    used_covers = set()
    for shelf in SHELVES:
        books = get_books(shelf["shelf"], shelf["sort"], len(shelf["slots"]))
        if not books:
            raise SystemExit(f"No books found on the '{shelf['shelf']}' shelf — is the profile still public?")
        spines = []
        for slot, book in zip(shelf["slots"], assign_books(shelf["slots"], books)):
            spines.append(spine_svg(slot, book, shelf["y"]))
            if book:
                used_covers.add(f"gr-{book['book_id']}.jpg")
        block = "\n    " + "\n    ".join(spines) + "\n    "
        marker = shelf["marker"]
        page, count = re.subn(
            rf"(<!-- GOODREADS:{marker}:START -->).*?(<!-- GOODREADS:{marker}:END -->)",
            lambda m: m.group(1) + block + m.group(2),
            page,
            flags=re.S,
        )
        if count != 1:
            raise SystemExit(f"Could not find GOODREADS:{marker} markers in reading.html")
        print(f"{shelf['shelf']}: " + ", ".join(b["title"][:40] for b in books))

    # tidy up covers of books that fell off the shelves
    for path in glob.glob(os.path.join(COVERS_DIR, "gr-*.jpg")):
        if os.path.basename(path) not in used_covers:
            os.remove(path)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(page)
    print("reading.html updated.")


if __name__ == "__main__":
    main()
