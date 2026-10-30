# MXATH — Mexican Athletes RSS

Automated English/Spanish Google News discovery across **47 Mexican athletes and athletes of Mexican heritage**, covering boxing, MMA/UFC, F1, soccer, basketball, cycling, NFL and MLB.

## What gets published?

Articles focusing on interviews, injuries, transfers, contracts, analysis, controversies, records and human-interest reporting. Pure box scores, live updates, odds, schedules and score-only items are filtered. Every relevant article can still be included even when it has no predefined editorial keyword, so we avoid the empty-feed failure seen with overly restrictive scoring.

## Setup

1. Create a public GitHub repository **`MXATH`**.
2. Upload **the CONTENTS of this folder to the repository root** (not as a nested `MXATH` directory). Include the hidden `.github` folder.
3. GitHub → **Settings → Actions → General** → allow Actions to read and write repository content if your repository settings require it. Workflow `permissions: contents: write` must also be permitted by repository settings.
4. GitHub → **Settings → Pages** → **Deploy from a branch**, branch **main**, folder **/docs** → Save.
5. GitHub → **Actions → Update MXATH News RSS → Run workflow**. Open the scanner diagnostics; verify `entries_seen` and `accepted`.
6. Once Pages publishes the repository, the feed should appear at **https://barriglez33.github.io/MXATH/feed.xml** (assuming the repository owner is `barriglez33` and the repository is named exactly `MXATH`).

## Configuration

- The 47 athletes, aliases, sport categories and editorial scoring are stored in `config.json` and `main.py`.
- Every 30 minutes (`9,39 * * * *`). Change cron if desired; GitHub Actions schedules can be delayed.
- Six high-profile athlete queries are checked each run; the other 41 profiles rotate through the remaining search budget across runs. Searches run in both `es-MX` and `en-US` editions.
- Lookback is 48 hours, archive retention 10 days; deduplication is by stable item ID and normalized headline.
- Freshness is determined from Google News publication metadata, not article page scraping.
- The feed contains original URLs (often Google News URLs), original news headlines, source and excerpt; **no full text is republished or automatically translated**.
- No guarantee of coverage: Google News indexing, ambiguous names, editorial heuristics, query limits and news availability affect discovery.

## Troubleshooting

Read `Show scanner diagnostics` for `requests`, `request_failed`, `entries_seen`, `outside_window`, `editorial_rejected`, `accepted`, `empty_feeds`, `duplicates`. If RSS URL 404s, check `docs/feed.xml` exists on `main`, verify Pages is set to `main /docs`, and check `pages build and deployment` Actions.

Local check: `pip install -r requirements.txt && python -m unittest discover -s tests -v && python main.py`

## Project structure

- `main.py`: scanner, editor, RSS generator, diagnostics
- `config.json`: athlete profiles and parameters
- `.github/workflows/update.yml`: robust GitHub Actions job, logs, checks and retrying commits
- `data/articles.json`: retained items; `data/state.json`: rotation cursor / diagnostics
- `docs/feed.xml`: public RSS for GitHub Pages
- `tests/test_scanner.py`: validation tests
