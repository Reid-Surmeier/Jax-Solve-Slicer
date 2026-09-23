"""Targeted reference corpus: images by the listed painters, where each came from, and what it depicts, in SQLite.

Sources, in order: Artsy's public GraphQL, the artists' and galleries' own sites (Scrapling), then Instagram
(Scrape Creators API). Each new image gets one vision call through OpenRouter that classifies it and describes it.
Only paintings, murals and prints count toward an artist's limit; everything else is stored with `keep = 0`.

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

from PIL import Image, ImageOps, ImageStat
from scrapling.fetchers import Fetcher, StealthyFetcher

HERE = Path(__file__).resolve().parent
MODEL = "google/gemini-2.5-flash-lite"
KEEP_KINDS = {"painting", "painting_detail", "mural", "print"}
MIN_SIDE = 400
DUP_BITS = 5  # dHash Hamming distance at or below which two images are the same work
GRAY_SATURATION = 0.12
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
  kind TEXT, depicts TEXT, subjects TEXT, palette TEXT, saturation REAL,
  keep INTEGER, why_excluded TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS rejects(image_key TEXT PRIMARY KEY, artist TEXT, reason TEXT);
CREATE VIEW IF NOT EXISTS artworks AS SELECT * FROM images WHERE keep = 1;
"""

PROMPT = """You are cataloguing reference images for a painting study corpus. Artist: {name}.
Text published with the image (caption, alt text or catalogue line; may be empty or unrelated):
{text}

Return one JSON object with these keys:
kind: one of painting, painting_detail, print, drawing, mural, sculpture, installation_view, studio_or_process, exhibition_graphic, photo_other
title: the title of this artwork if the text names it (not an exhibition, course or event name), else null
year: the artwork's year if the text gives one, else null
medium: the medium if the text gives it or it is clearly visible, else null
depicts: 2 to 4 sentences on what is depicted: subject, setting, composition, light, palette, and how the paint or ink is handled
subjects: a list of short tags such as figure, portrait, nude, interior, landscape, still life, animal, architecture, abstraction
palette: grayscale, limited or full_color"""


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


def exclusion(kind, saturation, year, only):
    if kind not in KEEP_KINDS:
        return f"kind: {kind}"
    if only.get("grayscale") and saturation > GRAY_SATURATION:
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


def site(s):
    start, match = s["url"], s.get("match")
    host = urlparse(start).netloc
    queue, seen, pages = [(start, 0)], {start}, 0
    while queue and pages < s.get("max_pages", 80):
        url, depth = queue.pop(0)
        pages += 1
        try:
            page = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=60000) if s.get("stealth") else Fetcher.get(url, timeout=30)
        except Exception as e:  # one bad page must not end the crawl
            print(f"  page failed {url}: {e}", file=sys.stderr)
            continue
        if page.status != 200:
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
            yield dict(image_key=full, image_url=full, source="site", source_url=url, source_text=" | ".join(x for x in (text, title) if x))
        for a in page.css("a[href]"):
            href = urljoin(url, a.attrib["href"]).split("#")[0]
            if IMG_EXT.search(href) and not SKIP_SRC.search(href):
                yield dict(image_key=href, image_url=href, source="site", source_url=url, source_text=" | ".join(x for x in ((a.get_all_text(strip=True) or "")[:400], title) if x))
            elif urlparse(href).netloc == host and href not in seen and depth < s.get("depth", 2) and (not match or match in href.lower()):
                seen.add(href)
                queue.append((href, depth + 1))
        time.sleep(0.5)


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
        r = Fetcher.get(c["image_url"], timeout=60)
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
    small = im.convert("RGB")
    small.thumbnail((768, 768))
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=85)
    body = {"model": MODEL, "response_format": {"type": "json_object"}, "usage": {"include": True},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT.format(name=name, text=(c.get("source_text") or "(none)")[:1500])},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}]}]}
    for attempt in range(3):
        try:
            d = Fetcher.post("https://openrouter.ai/api/v1/chat/completions", json=body, timeout=120,
                             headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}).json()
            text = d["choices"][0]["message"]["content"].strip().removeprefix("```json").removesuffix("```")
            return json.loads(text), float((d.get("usage") or {}).get("cost") or 0)
        except Exception as e:  # malformed reply or transient failure: retry, then leave undescribed
            err = e
            time.sleep(2 * (attempt + 1))
    print(f"  describe failed {c['image_key'][:80]}: {err}", file=sys.stderr)
    return None, 0.0


class Corpus:
    def __init__(self, out, workers):
        self.out, self.workers, self.cost = Path(out), workers, 0.0
        self.out.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.out / "corpus.sqlite", timeout=300)  # one process per artist may share the file
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def seen(self, key):
        return self.db.execute("SELECT 1 FROM images WHERE image_key=? UNION SELECT 1 FROM rejects WHERE image_key=?", (key, key)).fetchone()

    def reject(self, artist, key, reason):
        self.db.execute("INSERT OR IGNORE INTO rejects VALUES (?,?,?)", (key, artist, reason))

    def kept(self, artist):
        return self.db.execute("SELECT count(*) FROM images WHERE artist=? AND keep=1", (artist,)).fetchone()[0]

    def flush(self, a, batch, known):
        with ThreadPoolExecutor(self.workers) as pool:
            fetched = list(pool.map(download, batch))
        fresh = []
        for c, got, why in fetched:
            if why:
                self.reject(a["slug"], c["image_key"], why)
                continue
            body, im = got
            sha, h = hashlib.sha256(body).hexdigest(), dhash(im)
            if is_dup(h, known):
                self.reject(a["slug"], c["image_key"], "duplicate")
                continue
            known.append(h)
            path = self.out / "images" / a["slug"] / f"{sha[:16]}.{'jpg' if im.format == 'JPEG' else (im.format or 'img').lower()}"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            sat = ImageStat.Stat(im.convert("RGB").convert("HSV").getchannel("S")).mean[0] / 255
            fresh.append((c, im, dict(sha256=sha, dhash=f"{h:016x}", path=str(path.relative_to(self.out)), width=im.size[0], height=im.size[1], saturation=round(sat, 4))))
        with ThreadPoolExecutor(self.workers) as pool:
            described = list(pool.map(lambda f: describe(a["name"], f[0], f[1]), fresh))
        for (c, _, facts), (d, cost) in zip(fresh, described):
            self.cost += cost
            d = d or {}
            row = {**c, **facts, "artist": a["slug"], "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "kind": d.get("kind"), "depicts": d.get("depicts"), "palette": d.get("palette"),
                   "subjects": json.dumps(d.get("subjects") or []),
                   "title": c.get("title") or d.get("title"), "year": c.get("year") or d.get("year"), "medium": c.get("medium") or d.get("medium")}
            row["why_excluded"] = exclusion(row["kind"], row["saturation"], row["year"], a.get("only", {})) if d else "undescribed"
            row["keep"] = int(row["why_excluded"] is None)
            cols = ",".join(row)
            self.db.execute(f"INSERT OR IGNORE INTO images({cols}) VALUES ({','.join('?' * len(row))})", list(row.values()))
        self.db.commit()

    def run(self, a, limit):
        self.db.execute("INSERT OR REPLACE INTO artists VALUES (?,?,?)", (a["slug"], a["name"], a.get("note")))
        known = [int(h, 16) for (h,) in self.db.execute("SELECT dhash FROM images WHERE artist=?", (a["slug"],))]
        sources = ([artsy(a["artsy"])] if a.get("artsy") else []) + [site(s) for s in a.get("sites", [])] + ([instagram(a["instagram"])] if a.get("instagram") else [])
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
    assert exclusion("painting", 0.03, "2014", {"grayscale": True, "max_year": 2016}) is None
    assert exclusion("painting", 0.40, "2014", {"grayscale": True}) == "not grayscale"
    assert exclusion("painting", 0.02, "2019", {"max_year": 2016}) == "after 2016"
    assert exclusion("installation_view", 0.1, None, {}) == "kind: installation_view"
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
