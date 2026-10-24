# World Series 2026 – Beyond the Score RSS

Editorial news discovery for the 2026 Tampa Bay Rays vs. Milwaukee Brewers World Series. **No API key needed.**

## What it does

- Searches **all 52 official World Series roster players** (26 Rays + 26 Brewers), plus both managers and topical World Series searches.
- Rotates player queries over **three runs** so that all names are checked within ~45 minutes when GitHub Actions executes every 15 minutes (GitHub schedules can be delayed).
- Searches US English and Mexican Spanish Google News RSS editions; expands with controversies, player interviews, injuries, clubhouse, contracts, analytics, human stories, historic records, etc.
- Uses a headline- and snippet-based editorial scoring filter to exclude most routine scores, highlights, viewing guides, betting odds and recaps, while allowing genuinely newsworthy articles mentioning a result.
- Checks a **rolling 2-hour discovery window**, deduplicates headlines and keeps up to 250 accepted items published within the past 4 days.
- Publishes `docs/feed.xml` as an RSS 2.0 feed on GitHub Pages.
- Excludes `albat.com` when detectable from the source. Links point to the original publisher or Google News canonical redirects; no copyrighted full-text scraping.

## Quick start

1. Create an empty public GitHub repository named `world-series-2026-rss` and upload these files at its root (including `.github/workflows/update.yml`).
2. Edit `config.json` and replace `REPLACE_WITH_GITHUB_USERNAME` in `base_url` with your actual GitHub username.
3. In GitHub, enable **Settings → Pages → Deploy from a branch → main → /docs**.
4. Under **Settings → Actions → General**, give GitHub Actions **Read and write permissions** if workflow commits are blocked by repository policy.
5. Open **Actions → Update World Series Editorial RSS → Run workflow** to launch it manually. The schedule then aims to run every 15 minutes.
6. Feed URL: `https://YOUR_USERNAME.github.io/world-series-2026-rss/feed.xml` (once Pages is published).

## Local setup

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python main.py                 # live collection and feed creation
python main.py --dry-run       # preview query results without writing files
```

## Configuration

- `window_hours`: how far back to search (default 2 hours).
- `min_editorial_score`: increase for higher precision; decrease to surface more candidates.
- `queries_per_run`: upper bound on per-run distinct searches (each in two languages).
- `extra_queries`: contextual searches; rotate across runs.
- `teams`: official roster-based searches; update after any roster replacements.
- `negative_phrases`: editorial deprioritization, not a hard blanket ban.

## Limitations

Google News indexes selectively, so this cannot guarantee every article. Published timestamps and RSS snippets can be missing or misleading. Scheduled Actions may run later than 15 minutes. This feed **preserves publishers' original languages**, rather than claiming translation without a translation service. Headline-based article classification is heuristic and may generate false positives or false negatives. Source blocking is best effort when the Google News link hides the final publisher domain.

Rosters verified against MLB.com's October 23, 2026 official rosters:
- https://www.mlb.com/news/rays-2026-world-series-roster
- https://www.mlb.com/news/brewers-2026-world-series-roster
