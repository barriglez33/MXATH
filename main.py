"""World Series 2026 editorial RSS collector. Public Google News RSS, no API key."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'
DATA = ROOT / 'data' / 'articles.json'
STATE = ROOT / 'data' / 'state.json'
FEED = ROOT / 'docs' / 'feed.xml'
HEADERS = {'User-Agent': 'WorldSeriesEditorialRSS/1.0 (+https://github.com; news aggregation)'}
EDITORIAL = re.compile(r'\b(interview|reaction|reacts?|reveal(?:s|ed)?|explain(?:s|ed)?|decision|controvers(?:y|ial)|critic(?:ize|ism|s)|injur(?:y|ies|ed)|clubhouse|family|journey|record|historic|contract|free agen(?:t|cy)|rumo[u]?r|strateg(?:y|ic)|adjust(?:ment|s)|bullpen|velocity|bat speed|future|behind.the.scenes|analysis|says?|statement|comments?|struggle|comeback|emotion|argument|dispute|investigation|suspension|entrevista|declaraci[oó]n|reacci[oó]n|revela|explica|decisi[oó]n|pol[eé]mica|cr[ií]tica|lesi[oó]n|vestidor|historia|familia|r[eé]cord|contrato|agencia libre|rumor|estrategia|ajuste|velocidad|futuro|an[aá]lisis)\b', re.I)
TEAM = re.compile(r'\b(rays|brewers|tampa bay|milwaukee|cerveceros|serie mundial|world series|fall classic)\b', re.I)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def normalized(s):
    import unicodedata
    s = ''.join(ch for ch in unicodedata.normalize('NFKD', s) if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', ' ', s.casefold()).strip()


def queries(config, run_number):
    # Cycle through every player across three runs, while scanning multiple editorial angles.
    all_players = [(team, person) for team, players in config['teams'].items() for person in players]
    rotation = run_number % 3
    player_queries = []
    for idx, (team, person) in enumerate(all_players):
        if idx % 3 == rotation:
            short_team = 'Rays' if 'Rays' in team else 'Brewers'
            player_queries.append(f'"{person}" "{short_team}"')
    extras = config['extra_queries']
    # Rotate context queries. Always include several broad series-specific searches.
    selected_extras = [extras[(run_number * 4 + i) % len(extras)] for i in range(6)]
    # Always check broad catch-all searches; rotating player queries supplement them.
    broad = [extras[i] for i in [-5, -4, -3, -2, -1]]
    other = [q for q in selected_extras if q not in broad]
    return (broad + other + player_queries)[:config['queries_per_run']]


def google_news_url(q, edition):
    if edition == 'es-419':
        return f'https://news.google.com/rss/search?q={quote(q)}&hl=es-419&gl=MX&ceid=MX:es-419'
    return f'https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en'


def article_date(entry):
    try:
        if entry.get('published_parsed'):
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return parsedate_to_datetime(entry.get('published', '')).astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def editorial_score(title, description, config):
    title = BeautifulSoup(title or '', 'html.parser').get_text(' ', strip=True)
    description = BeautifulSoup(description or '', 'html.parser').get_text(' ', strip=True)
    joined = f'{title} {description}'
    title_context = len(EDITORIAL.findall(title))
    full_context = len(EDITORIAL.findall(joined))
    teams = bool(TEAM.search(joined))
    negative = sum(p.casefold() in title.casefold() for p in config['negative_phrases'])
    # Result-only headlines normally get zero editorial points.
    score = 3 * min(title_context, 2) + min(max(full_context - title_context, 0), 2) + int(teams) - 5 * negative
    if re.search(r'\b(?:beat|defeat|win|lose|top|edge|blow out|derrot[aó]|vence|gan[oó])\b', title, re.I) and title_context == 0:
        score -= 4
    if teams and not negative and title_context == 0:
        # Discovery fallback: potentially valuable team-specific stories without
        # an editorial buzzword. Pure result headlines stay negative-scored.
        if not re.search(r'\b(?:beat|defeat|wins?|loses?|top|edge|blow out|derrot[aó]|vence|gan[oó])\b', title, re.I):
            score = max(score, 2)
    return score


def canonical_key(title, link):
    # Google News links can differ between searches; fall back to headline deduplication.
    clean_title = re.sub(r'\s+[-|]\s+[^-|]{2,70}$', '', title).strip()
    return hashlib.sha256(normalized(clean_title).encode()).hexdigest()[:22]


def source_name(entry):
    src = entry.get('source') or {}
    return src.get('title', '') if isinstance(src, dict) else getattr(src, 'title', '')


def collect(config, run_number, now):
    fresh_from = now - timedelta(hours=config['window_hours'])
    output = []
    seen_links = set()
    stats = Counter()
    query_batch = queries(config, run_number)
    for q in query_batch:
        for edition in config['language_editions']:
            url = google_news_url(q, edition)
            try:
                resp = requests.get(url, timeout=20, headers=HEADERS)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
                stats['requests_ok'] += 1
                if parsed.bozo:
                    logging.warning('Feed parser reported issue for %s: %s', q, parsed.bozo_exception)
                logging.info('Search %s query=%r results=%d', edition, q, len(parsed.entries))
                if not parsed.entries:
                    stats['empty_feeds'] += 1
                for e in parsed.entries[:config.get('results_per_query', 75)]:
                    stats['entries_seen'] += 1
                    dt = article_date(e)
                    if dt is None:
                        stats['missing_date'] += 1
                        continue
                    if not (fresh_from <= dt <= now + timedelta(minutes=5)):
                        stats['outside_window'] += 1
                        continue
                    title = html.unescape(BeautifulSoup(e.get('title', ''), 'html.parser').get_text(' ', strip=True))
                    desc = BeautifulSoup(e.get('summary', ''), 'html.parser').get_text(' ', strip=True)
                    link = e.get('link', '')
                    domain = urlparse(link).netloc.casefold()
                    src = source_name(e)
                    if not link or any(b in (domain + ' ' + src.casefold()) for b in config['blocked_domains']):
                        stats['blocked_or_invalid'] += 1
                        continue
                    score = editorial_score(title, desc, config)
                    if score < config['min_editorial_score']:
                        stats['editorial_rejected'] += 1
                        continue
                    key = canonical_key(title, link)
                    if key in seen_links:
                        stats['duplicate'] += 1
                        continue
                    seen_links.add(key)
                    stats['accepted'] += 1
                    output.append(dict(id=key, title=title, url=link, source=src,
                                       summary=desc[:1200], published=dt.isoformat(), score=score,
                                       language=edition, query=q))
            except (requests.RequestException, ValueError) as exc:
                stats['request_failed'] += 1
                logging.warning('Search failed: %s / %s: %s', edition, q, exc)
            time.sleep(0.15)
    logging.info('DISCOVERY DIAGNOSTICS: %s', json.dumps(dict(stats), sort_keys=True))
    if stats['requests_ok'] == 0:
        raise RuntimeError('All news searches failed: check network, Google News and query URLs')
    return output, len(query_batch), dict(stats)


def escape(v):
    return html.escape(str(v or ''), quote=True)


def write_rss(items, config, now):
    link = config['base_url'].rstrip('/')
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
             f'<title>{escape(config["name"])}</title>', f'<link>{escape(link)}</link>',
             '<description>Editorial MLB news beyond game scores. Sources credited; external links.</description>',
             '<language>en-us</language>', f'<lastBuildDate>{format_datetime(now)}</lastBuildDate>',
             '<atom:link xmlns:atom="http://www.w3.org/2005/Atom" href="' + escape(link + '/feed.xml') + '" rel="self" type="application/rss+xml" />']
    for item in items:
        dt = datetime.fromisoformat(item['published'])
        parts.extend(['<item>', f'<title>{escape(item["title"])}</title>',
                      f'<link>{escape(item["url"])}</link>',
                      f'<guid isPermaLink="false">ws2026-{escape(item["id"])}</guid>',
                      f'<pubDate>{format_datetime(dt)}</pubDate>',
                      f'<description>{escape(item["summary"])}</description>',
                      f'<source>{escape(item["source"])}</source>', '</item>'])
    parts.append('</channel></rss>')
    FEED.parent.mkdir(parents=True, exist_ok=True)
    FEED.write_text('\n'.join(parts) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    opts = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    config = load_json(CONFIG, {})
    now = datetime.now(timezone.utc)
    state = load_json(STATE, {'run_number': 0})
    n = int(state.get('run_number', 0))
    fresh, query_count, stats = collect(config, n, now)
    prior = load_json(DATA, [])
    combined = {}
    for a in prior + fresh:
        # Keep more informative version of duplicate headline.
        if a['id'] not in combined or (a['score'], len(a['summary'])) > (combined[a['id']]['score'], len(combined[a['id']]['summary'])):
            combined[a['id']] = a
    # Keep a bounded archive of articles within the recent period; not just one game's reports.
    cutoff = now - timedelta(days=config.get('archive_days', 7))
    items = sorted([a for a in combined.values() if datetime.fromisoformat(a['published']) >= cutoff],
                   key=lambda a: (a['published'], a['score']), reverse=True)[:config['max_articles']]
    logging.info('Queries: %d; newly qualified: %d; RSS items: %d', query_count, len(fresh), len(items))
    if not opts.dry_run:
        DATA.parent.mkdir(exist_ok=True)
        DATA.write_text(json.dumps(items, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        STATE.write_text(json.dumps({'run_number': n + 1, 'last_run_utc': now.isoformat(), 'qualified': len(fresh), 'diagnostics': stats}, indent=2) + '\n', encoding='utf-8')
        write_rss(items, config, now)


if __name__ == '__main__':
    main()
