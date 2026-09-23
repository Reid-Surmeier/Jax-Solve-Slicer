---
name: reference_corpus
purpose: Targeted scrape of the listed painters' work into SQLite with source and a description of what each image depicts
interface: modules/reference_corpus/scrape.py
errors: Python standard exceptions; per-image failures are recorded in the rejects table, not raised
tests: modules/reference_corpus/scrape.py --selftest
depends-on: []
---

# reference_corpus

A closed list of painters (`artists.json`) and up to 500 kept artworks each. Printmakers count only through their prints.

Sources, in order, stopping once an artist's limit is reached: Artsy's public GraphQL, the artist's and galleries' own sites (Scrapling; `browser` sites, and any page that answers 403/429/503, render in one Browserbase session per crawl, or Scrapling's local browser when no Browserbase key is set), then Instagram and Google search results through the Scrape Creators API. A search result page is crawled alone, and an image from it counts only when its own alt text or caption names the artist. Every image is downloaded, deduplicated per artist by dHash, and given one OpenRouter vision call (`google/gemini-2.5-flash-lite`) that classifies it and writes `depicts`.

`outputs/reference-corpus/corpus.sqlite` (git-ignored, with `images/<artist>/`):

- `images` holds every stored image, including the source page (`source_url`), the published caption or catalogue line (`source_text`), title, year, medium, `kind`, `depicts`, `subjects`, `palette`, and `keep`/`why_excluded`.
- `artworks` is the view of kept rows: paintings, painting details, murals and prints that pass the artist's `only` filter. Avery Singer's filter is grayscale work from 2016 or earlier.
- `rejects` holds images skipped as small, duplicate or unreachable, so a rerun does not fetch them again.

Run with both keys injected through the Bitwarden runner:

```bash
R=~/.claude/skills/access-bitwarden-secrets/scripts/stored_bws.sh
$R run "Scrape Creators" SCRAPECREATORS_API_KEY -- $R run OPENROUTER_API_KEY OPENROUTER_API_KEY -- \
  .venv/bin/python modules/reference_corpus/scrape.py --out outputs/reference-corpus [--artists slug,…] [--limit 500]
```

A rerun resumes: stored and rejected images are skipped. Each run appends its OpenRouter cost to `spend.jsonl`. The scraped images are other artists' copyrighted work, kept locally for study, and are never committed.
