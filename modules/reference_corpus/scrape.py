"""Targeted reference corpus: images by the listed painters, where each came from, and what it depicts, in SQLite.

Sources, in order: Artsy's public GraphQL, the artists' and galleries' own sites (Scrapling), Instagram, then pages
found by Google search (both through the Scrape Creators API). Each new image gets one vision call through OpenRouter that classifies it and describes it.
Only clean reproductions of paintings and prints count toward an artist's limit: no photographs of the artist, studio,
installation, wall or street. Everything else is stored with `keep = 0`.

    SCRAPECREATORS_API_KEY=… OPENROUTER_API_KEY=… python scrape.py --out outputs/reference-corpus
    python scrape.py --selftest
"""
import argparse
import base64
import hashlib
import io
import itertools
import json
import logging
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image, ImageOps
from scrapling.fetchers import Fetcher, StealthyFetcher
from scrapling.parser import Selector

HERE = Path(__file__).resolve().parent
MODEL = "google/gemini-2.5-flash-lite"
KEEP_KINDS = {"painting", "painting_detail", "print"}
MIN_SIDE = 400
DUP_BITS = 5  # dHash Hamming distance at or below which two images are the same work
GRAY_SATURATION = 0.25  # at or below this 95th-percentile saturation, and labelled grayscale, a work counts as black and white
IMG_EXT = re.compile(r"\.(jpe?g|png|webp)(\?|$)", re.I)
SKIP_SRC = re.compile(r"(logo|icon|sprite|avatar|favicon|placeholder|\.svg|\.gif|^data:)", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS artists(slug TEXT PRIMARY KEY, name TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS images(
  id INTEGER PRIMARY KEY,
  artist TEXT NOT NULL REFERENCES artists(slug),
  image_key TEXT UNIQUE NOT NULL,    -- image URL, or ig:<media id> for Instagram's expiring CDN URLs
  image_url TEXT, sha256 TEXT, dhash TEXT, path TEXT, width INTEGER, height INTEGER,
  source TEXT,                       -- artsy | site | instagram
  source_url TEXT,                   -- the page or post the image was found on
  source_text TEXT,                  -- caption, alt text or catalogue line as published
  title TEXT, year TEXT, medium TEXT, dimensions TEXT,
  kind TEXT, depicts TEXT, subjects TEXT, palette TEXT,
  saturation REAL,                   -- 95th-percentile HSV saturation, 0..1
  artwork_only INTEGER,              -- a straight reproduction of one work, cropped to it, nothing else in frame
  verified INTEGER,                  -- the caption-blind painting check passed (1), failed (0), not yet asked (NULL)
  keep INTEGER, why_excluded TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS rejects(image_key TEXT PRIMARY KEY, artist TEXT, reason TEXT);
CREATE VIEW IF NOT EXISTS artworks AS SELECT * FROM images WHERE keep = 1;
"""

PROMPT = """You are cataloguing reference images for a painting study corpus. Artist: {name}.
Text published with the image (caption, alt text or catalogue line; may be empty or unrelated):
{text}

Return one JSON object with these keys:
kind: one of painting, painting_detail, print, drawing, mural, sculpture, installation_view, studio_or_process, exhibition_graphic, photo_other
  (any photograph of a real person, the artist included, is photo_other)
title: the title of this artwork if the text names it (not an exhibition, course or event name), else null
year: the artwork's year if the text gives one, else null
medium: the medium if the text gives it or it is clearly visible, else null
depicts: 2 to 4 sentences on what is depicted: subject, setting, composition, light, palette, and how the paint or ink is handled
subjects: a list of short tags such as figure, portrait, nude, interior, landscape, still life, animal, architecture, abstraction
palette: grayscale, limited or full_color
photo_context: true if the photograph shows real surroundings outside the artwork's edges (a real person or hand, the artist,
  a studio, gallery wall or floor, an easel, a building or street, several separate works) or has text or graphics laid over it.
  false for a plain reproduction of one work, even with a thin margin of wall or table around it.
  Whatever is painted inside the artwork (painted people, rooms, streets) never counts.
text_overlay: true only if typeset words, dates, logos or a caption are visibly printed in the image pixels on top of or beside the work,
  as on a flyer, poster, magazine page or book cover. The published text given above never counts, and neither do letters painted into the work itself
other_artist: true if the text or the image suggests the work is by someone other than {name} (a caption crediting another artist, a famous historical work, a page from a book about another painter)"""


VERIFY = """Judge only the pixels of this image. Is it a reproduction (a photograph or scan) of one hand-made painting or print that fills most of the frame?
Answer false for a photograph of a real person, place or object; a 3D render, video still or screenshot; a page of text or a document;
a book, magazine or poster; several artworks side by side; an installation, studio or exhibition view.
Paintings that imitate photographs or computer graphics still count as paintings.
Return JSON: {"painting": true or false}"""


def best_src(attrib):
    """The largest image a tag offers: srcset entries by width, then lazy-load attributes, then src."""
    for key in ("data-srcset", "srcset"):
        entries = [p.strip().rsplit(" ", 1) for p in (attrib.get(key) or "").split(",") if p.strip()]
        sized = [(int(w[:-1]) if w.endswith("w") and w[:-1].isdigit() else 0, u) for u, w in (e if len(e) == 2 else (e[0], "0w") for e in entries)]
        if sized:
            return max(sized)[1]
    src = attrib.get("data-src") or attrib.get("data-image") or attrib.get("data-lazy-src") or attrib.get("src")
    if src and "squarespace-cdn.com" in src:
        src = src.split("?")[0] + "?format=2500w"
    return src


def dhash(im):
    g = im.convert("L").resize((9, 8), Image.LANCZOS).tobytes()
    return sum(1 << i for i in range(64) if g[(i // 8) * 9 + i % 8] > g[(i // 8) * 9 + i % 8 + 1])


def is_dup(h, known):
    return any(bin(h ^ k).count("1") <= DUP_BITS for k in known)


def saturation(im):
    """95th-percentile saturation: a mean hides a coloured passage on a white ground."""
    hist = im.convert("RGB").convert("HSV").getchannel("S").histogram()
    total, seen = sum(hist), 0
    for level, count in enumerate(hist):
        seen += count
        if seen >= 0.95 * total:
            return round(level / 255, 4)


def exclusion(kind, artwork_only, saturation, year, only, palette=None):
    if kind not in KEEP_KINDS:
        return f"kind: {kind}"
    if artwork_only is not True:
        return "not a clean reproduction"
    if only.get("grayscale") and (saturation > GRAY_SATURATION or palette != "grayscale"):
        return "not grayscale"
    years = [int(y) for y in re.findall(r"(?:19|20)\d\d", str(year or ""))]
    if only.get("max_year") and years and min(years) > only["max_year"]:
        return f"after {only['max_year']}"
    return None


# ---- sources: each yields candidate dicts ------------------------------------------------------------

ARTSY_Q = """query($id:String!,$after:String){artist(id:$id){artworksConnection(first:50,after:$after){
pageInfo{hasNextPage endCursor} edges{node{title date medium category dimensions{in cm} href
image{url(version:["larger","large"])}}}}}}"""


def artsy(slug):
    after = None
    while True:
        d = Fetcher.post("https://metaphysics-production.artsy.net/v2", json={"query": ARTSY_Q, "variables": {"id": slug, "after": after}}, timeout=60).json()
        conn = ((d.get("data") or {}).get("artist") or {}).get("artworksConnection")
        if not conn:
            return
        for e in conn["edges"]:
            n = e["node"]
            url = (n.get("image") or {}).get("url")
            if url:
                dims = n.get("dimensions") or {}
                line = ", ".join(x for x in (n["title"], n.get("date"), n.get("medium"), dims.get("in"), dims.get("cm")) if x)
                yield dict(image_key=url, image_url=url, source="artsy", source_url="https://www.artsy.net" + n["href"],
                           title=n["title"], year=n.get("date"), medium=n.get("medium") or n.get("category"),
                           dimensions=dims.get("in"), source_text=line)
        if not conn["pageInfo"]["hasNextPage"]:
            return
        after = conn["pageInfo"]["endCursor"]


class Browser:
    """A rendered page as a Scrapling Selector: one Browserbase session per crawl when a key is set, else Scrapling's local browser."""

    def __init__(self):
        self.pw = self.browser = self.tab = None

    def get(self, url):
        if not os.environ.get("BROWSERBASE_API_KEY"):
            return StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=60000)
        try:
            return self.render(url)
        except Exception:  # Browserbase sessions time out mid-crawl: reconnect once with a fresh one
            self.close()
            return self.render(url)

    def render(self, url):
        if self.tab is None:
            from patchright.sync_api import sync_playwright
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.connect_over_cdp(f"wss://connect.browserbase.com?apiKey={os.environ['BROWSERBASE_API_KEY']}")
            ctx = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            self.tab = ctx.pages[0] if ctx.pages else ctx.new_page()
        resp = self.tab.goto(url, wait_until="load", timeout=60000)
        self.tab.wait_for_timeout(2500)
        for _ in range(8):  # lazy-loaded galleries only fill in as they scroll into view
            self.tab.mouse.wheel(0, 4000)
            self.tab.wait_for_timeout(400)
        page = Selector(self.tab.content(), url=url)
        page.status = resp.status if resp else 200
        return page

    def close(self):
        if self.pw:
            try:
                self.browser.close()
            except Exception:  # already disconnected
                pass
            self.pw.stop()
        self.pw = self.browser = self.tab = None


def site(s):
    start, match = s["url"], s.get("match")
    host = urlparse(start).netloc
    queue, seen, pages, browser = [(start, 0)], {start}, 0, Browser()
    try:
        while queue and pages < s.get("max_pages", 80):
            url, depth = queue.pop(0)
            pages += 1
            try:
                page = browser.get(url) if s.get("browser") else Fetcher.get(url, timeout=20, retries=1)
                if page.status in (403, 429, 503) and not s.get("browser"):  # blocked plain fetch: render it instead
                    page = browser.get(url)
            except Exception as e:  # one bad page must not end the crawl
                print(f"  page failed {url}: {e}", file=sys.stderr)
                continue
            if not 200 <= page.status < 300:
                continue
            title = (page.css("title::text").get() or "").strip()
            for img in page.css("img"):
                src = best_src(img.attrib)
                if not src or SKIP_SRC.search(src):
                    continue
                text, node = img.attrib.get("alt") or img.attrib.get("title") or "", img.parent
                for _ in range(3):
                    if text or node is None:
                        break
                    text, node = (node.get_all_text(strip=True) or "")[:400], node.parent
                full = urljoin(url, src)
                if s.get("require") and s["require"] not in text.lower():
                    continue
                yield dict(image_key=full, image_url=full, source="site", source_url=url, source_text=" | ".join(x for x in (text, title) if x))
            for a in page.css("a[href]"):
                href = urljoin(url, a.attrib["href"]).split("#")[0]
                if IMG_EXT.search(href) and not SKIP_SRC.search(href):
                    if s.get("require") and s["require"] not in (a.get_all_text(strip=True) or "").lower():
                        continue
                    yield dict(image_key=href, image_url=href, source="site", source_url=url, source_text=" | ".join(x for x in ((a.get_all_text(strip=True) or "")[:400], title) if x))
                elif urlparse(href).netloc == host and href not in seen and depth < s.get("depth", 2) and (not match or match in href.lower()):
                    seen.add(href)
                    queue.append((href, depth + 1))
            time.sleep(0.5)
    finally:
        browser.close()


SEARCH_SKIP = re.compile(r"(instagram|facebook|pinterest|twitter|x\.com|tiktok|youtube|reddit|artsy\.net|wikipedia)", re.I)


def google(a):
    """Pages found by Google search, each crawled alone; an image counts only if its own alt text or caption names the artist."""
    surname = a["name"].split("(")[0].split()[-1].lower()
    for query in a.get("searches") or [f'"{a["name"]}" painting oil on canvas', f'"{a["name"]}" exhibition']:
        for n in (1, 2):
            d = Fetcher.get("https://api.scrapecreators.com/v1/google/search", params={"query": query, "page": n},
                            headers={"x-api-key": os.environ["SCRAPECREATORS_API_KEY"]}, timeout=90).json()
            for r in d.get("results") or []:
                if r.get("url") and not SEARCH_SKIP.search(urlparse(r["url"]).netloc):
                    yield from site({"url": r["url"], "depth": 0, "require": surname})


def instagram(handle):
    cursor = None
    while True:
        params = {"handle": handle, **({"next_max_id": cursor} if cursor else {})}
        d = Fetcher.get("https://api.scrapecreators.com/v2/instagram/user/posts", params=params,
                        headers={"x-api-key": os.environ["SCRAPECREATORS_API_KEY"]}, timeout=90).json()
        for it in d.get("items") or []:
            text = ((it.get("caption") or {}).get("text") or "").strip()
            posted = (it.get("created_at") or "")[:10]
            for m in it.get("carousel_media") or [it]:
                cands = (m.get("image_versions2") or {}).get("candidates") or []
                if m.get("media_type") != 1 or not cands:
                    continue
                yield dict(image_key=f"ig:{m.get('pk') or m.get('id')}", image_url=max(cands, key=lambda c: c.get("width") or 0)["url"],
                           source="instagram", source_url=f"https://www.instagram.com/p/{it['code']}/",
                           source_text=f"Posted {posted}. {text}".strip())
        cursor = d.get("next_max_id")
        if not d.get("more_available") or not cursor:
            return


# ---- per-image work ---------------------------------------------------------------------------------

def download(c):
    try:
        r = Fetcher.get(c["image_url"], timeout=45, retries=1)
        if r.status != 200:
            return c, None, f"http {r.status}"
        im = Image.open(io.BytesIO(r.body))
        im.load()
    except Exception as e:  # unreadable or unreachable image: record and move on
        return c, None, f"error: {type(e).__name__}"
    if min(im.size) < MIN_SIDE:
        return c, None, f"small {im.size[0]}x{im.size[1]}"
    return c, (r.body, im), None


def describe(name, c, im):
    return ask(PROMPT.format(name=name, text=(c.get("source_text") or "(none)")[:1500]), im, c["image_key"])


def is_painting(im):
    """A second, caption-blind yes/no check on every image the description kept."""
    d, cost = ask(VERIFY, im, "verify")
    return (None if d is None else d.get("painting") is True), cost


def ask(prompt, im, label):
    small = im.convert("RGB")
    small.thumbnail((768, 768))
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=85)
    body = {"model": MODEL, "response_format": {"type": "json_object"}, "usage": {"include": True},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}]}]}
    for attempt in range(3):
        try:
            d = Fetcher.post("https://openrouter.ai/api/v1/chat/completions", json=body, timeout=120,
                             headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}).json()
            text = d["choices"][0]["message"]["content"].strip().removeprefix("```json").removesuffix("```")
            out = json.loads(text)
            out = out[0] if isinstance(out, list) and out else out  # the model sometimes wraps the object in a list
            if not isinstance(out, dict):
                raise ValueError(f"not an object: {text[:80]}")
            return out, float((d.get("usage") or {}).get("cost") or 0)
        except Exception as e:  # malformed reply or transient failure: retry, then leave undescribed
            err = e
            time.sleep(2 * (attempt + 1))
    print(f"  model call failed {label[:80]}: {err}", file=sys.stderr)
    return None, 0.0


def classified(a, c, d):
    """The description-derived columns for one image; published catalogue facts win over the model's reading."""
    d = d or {}
    row = {"kind": d.get("kind"), "depicts": d.get("depicts"), "palette": d.get("palette"), "subjects": json.dumps(d.get("subjects") or []),
           "artwork_only": None if not d else int(d.get("photo_context") is False),
           "title": c.get("title") or d.get("title"), "year": c.get("year") or d.get("year"), "medium": c.get("medium") or d.get("medium")}
    row["why_excluded"] = ("text over the image" if d.get("text_overlay") else "by another artist" if d.get("other_artist") else
                           exclusion(row["kind"], d.get("photo_context") is False, c["saturation"], row["year"], a.get("only", {}), row["palette"])) if d else "undescribed"
    row["keep"] = int(row["why_excluded"] is None)
    return row


class Corpus:
    def __init__(self, out, workers):
        self.out, self.workers, self.cost = Path(out), workers, 0.0
        self.out.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.out / "corpus.sqlite", timeout=300)  # one process per artist may share the file
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        columns = {r[1] for r in self.db.execute("PRAGMA table_info(images)")}
        for column in ("artwork_only", "verified"):
            if column not in columns:
                self.db.execute(f"ALTER TABLE images ADD COLUMN {column} INTEGER")

    def verify(self, pairs):
        """Run the painting check on each kept (row, image) pair and demote the rows that fail it."""
        pairs = [(r, im) for r, im in pairs if r["keep"]]
        with ThreadPoolExecutor(self.workers) as pool:
            answers = list(pool.map(lambda p: is_painting(p[1]), pairs))
        for (r, _), (ok, cost) in zip(pairs, answers):
            self.cost += cost
            r["verified"] = None if ok is None else int(ok)
            if ok is not True:
                r["keep"], r["why_excluded"] = 0, "failed painting check" if ok is False else "unverified"

    def seen(self, key):
        return self.db.execute("SELECT 1 FROM images WHERE image_key=? UNION SELECT 1 FROM rejects WHERE image_key=?", (key, key)).fetchone()

    def kept(self, artist):
        return self.db.execute("SELECT count(*) FROM images WHERE artist=? AND keep=1", (artist,)).fetchone()[0]

    def flush(self, a, batch, known):
        with ThreadPoolExecutor(self.workers) as pool:
            fetched = list(pool.map(download, batch))
        fresh, rejects, rows = [], [], []
        for c, got, why in fetched:
            if why:
                rejects.append((c["image_key"], a["slug"], why))
                continue
            body, im = got
            sha, h = hashlib.sha256(body).hexdigest(), dhash(im)
            if is_dup(h, known):
                rejects.append((c["image_key"], a["slug"], "duplicate"))
                continue
            known.append(h)
            path = self.out / "images" / a["slug"] / f"{sha[:16]}.{'jpg' if im.format == 'JPEG' else (im.format or 'img').lower()}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            fresh.append((c, im, dict(sha256=sha, dhash=f"{h:016x}", path=str(path.relative_to(self.out)), width=im.size[0], height=im.size[1], saturation=saturation(im))))
        with ThreadPoolExecutor(self.workers) as pool:
            described = list(pool.map(lambda f: describe(a["name"], f[0], f[1]), fresh))
        for (c, _, facts), (d, cost) in zip(fresh, described):
            self.cost += cost
            rows.append({**c, **facts, "artist": a["slug"], "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **classified(a, {**c, **facts}, d)})
        self.verify([(r, im) for r, (_, im, _) in zip(rows, fresh)])
        with self.db:  # one short write per batch; never hold the lock across network calls
            self.db.executemany("INSERT OR IGNORE INTO rejects VALUES (?,?,?)", rejects)
            for row in rows:
                self.db.execute(f"INSERT OR IGNORE INTO images({','.join(row)}) VALUES ({','.join('?' * len(row))})", list(row.values()))

    def recheck(self, a):
        """From local files: describe again the images that predate the current rules, and run the painting check on kept ones that lack it."""
        self.db.row_factory = sqlite3.Row
        old = [dict(r) for r in self.db.execute("SELECT * FROM images WHERE artist=? AND (artwork_only IS NULL OR (keep=1 AND verified IS NULL))", (a["slug"],))]
        self.db.row_factory = None
        for i in range(0, len(old), 50):
            chunk = old[i:i + 50]
            images = [Image.open(self.out / r["path"]) for r in chunk]
            stale = [(r, im) for r, im in zip(chunk, images) if r["artwork_only"] is None]
            with ThreadPoolExecutor(self.workers) as pool:
                described = list(pool.map(lambda p: describe(a["name"], p[0], p[1]), stale))
            for (r, im), (d, cost) in zip(stale, described):
                self.cost += cost
                r["saturation"] = saturation(im)
                r.update(classified(a, r, d))
            self.verify(list(zip(chunk, images)))
            fields = ("saturation", "kind", "depicts", "palette", "subjects", "artwork_only", "title", "year", "medium", "why_excluded", "keep", "verified")
            with self.db:
                for r in chunk:
                    self.db.execute(f"UPDATE images SET {', '.join(k + '=?' for k in fields)} WHERE id=?", [*(r[k] for k in fields), r["id"]])
            print(f"  {a['slug']}: rechecked {i + len(chunk)}/{len(old)}, ${self.cost:.3f}", flush=True)

    def run(self, a, limit):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO artists VALUES (?,?,?)", (a["slug"], a["name"], a.get("note")))
        self.recheck(a)
        known = [int(h, 16) for (h,) in self.db.execute("SELECT dhash FROM images WHERE artist=?", (a["slug"],))]
        sources = ([artsy(a["artsy"])] if a.get("artsy") else []) + [site(s) for s in a.get("sites", [])] + ([instagram(a["instagram"])] if a.get("instagram") else []) + [google(a)]
        batch, size = [], self.workers * 3
        for c in itertools.chain(*sources):
            if self.kept(a["slug"]) >= limit:
                break
            if self.seen(c["image_key"]) or any(b["image_key"] == c["image_key"] for b in batch):
                continue
            batch.append(c)
            if len(batch) >= min(size, limit - self.kept(a["slug"])):
                self.flush(a, batch, known)
                batch = []
                print(f"  {a['slug']}: {self.kept(a['slug'])} kept, ${self.cost:.3f} described so far", flush=True)
        if batch:
            self.flush(a, batch, known)


def selftest():
    assert best_src({"srcset": "a.jpg 300w, b.jpg 1200w, c.jpg 800w", "src": "x.jpg"}) == "b.jpg"
    assert best_src({"src": "https://images.squarespace-cdn.com/p/x.jpg?format=300w"}).endswith("x.jpg?format=2500w")
    a = Image.linear_gradient("L").rotate(90).resize((500, 400))
    assert is_dup(dhash(a), [dhash(a.resize((250, 200)))]) and not is_dup(dhash(a), [dhash(ImageOps.mirror(a))])
    assert exclusion("painting", True, 0.03, "2014", {"grayscale": True, "max_year": 2016}, "grayscale") is None
    assert exclusion("painting", True, 0.40, "2014", {"grayscale": True}, "grayscale") == "not grayscale"
    assert exclusion("painting", True, 0.03, "2014", {"grayscale": True}, "limited") == "not grayscale"
    assert saturation(Image.new("RGB", (100, 100), "white")) == 0
    stripe = Image.new("RGB", (100, 100), "white")
    stripe.paste((255, 0, 0), (0, 0, 100, 10))
    assert saturation(stripe) == 1.0
    assert exclusion("painting", True, 0.02, "2019", {"max_year": 2016}) == "after 2016"
    assert exclusion("installation_view", True, 0.1, None, {}) == "kind: installation_view"
    assert exclusion("painting", False, 0.1, None, {}) == "not a clean reproduction"
    assert exclusion("mural", True, 0.1, None, {}) == "kind: mural"
    a = {"slug": "x", "only": {}}
    assert classified(a, {"saturation": 0.3}, {"kind": "painting", "photo_context": False})["keep"] == 1
    assert classified(a, {"saturation": 0.3}, {"kind": "painting", "photo_context": True})["keep"] == 0
    assert classified(a, {"saturation": 0.3}, None)["why_excluded"] == "undescribed"
    assert classified(a, {"saturation": 0.3}, {"kind": "painting", "photo_context": False, "text_overlay": True})["why_excluded"] == "text over the image"
    assert classified(a, {"saturation": 0.3}, {"kind": "painting", "photo_context": False, "other_artist": True})["why_excluded"] == "by another artist"
    sqlite3.connect(":memory:").executescript(SCHEMA)
    print("reference_corpus selftest ok")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="outputs/reference-corpus")
    p.add_argument("--artists", help="comma-separated slugs from artists.json; default all")
    p.add_argument("--limit", type=int, default=500, help="artworks kept per artist")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        sys.exit(selftest())
    logging.getLogger("scrapling").setLevel(logging.WARNING)
    artists = json.loads((HERE / "artists.json").read_text())
    wanted = set(args.artists.split(",")) if args.artists else None
    corpus = Corpus(args.out, args.workers)
    for a in artists:
        if wanted is None or a["slug"] in wanted:
            print(f"== {a['name']}", flush=True)
            corpus.run(a, args.limit)
    for slug, kept, total in corpus.db.execute("SELECT artist, sum(keep), count(*) FROM images GROUP BY artist"):
        print(f"{slug:24} {kept:4} artworks of {total:4} images")
    spend = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "provider": "openrouter", "model": MODEL, "cost_usd": round(corpus.cost, 4)}
    with open(Path(args.out) / "spend.jsonl", "a") as f:
        f.write(json.dumps(spend) + "\n")
    print(f"OpenRouter spend this run: ${corpus.cost:.4f}")
