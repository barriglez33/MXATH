"""MXATH: news discovery and editorial RSS, Python 3.12."""
from __future__ import annotations
import calendar
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import json
import logging
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode, urlparse
import xml.etree.ElementTree as ET

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger('mxath')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', stream=sys.stdout)
MARKETS = [('es-MX','MX','MX:es-419'), ('en-US','US','US:en')]
# Editorial keywords affect ranking, NOT whether an athlete's article is discoverable.
POSITIVE = {'interview':3,'entrevista':3,'reveals':3,'revela':3,'confirms':2,'confirma':2,'injury':3,'lesión':3,'lesion':3,'recovery':2,'recuperación':2,'contract':3,'contrato':3,'trade':3,'traspaso':3,'transfer':3,'fichaje':3,'controversy':3,'polémica':3,'controversia':3,'explains':2,'explica':2,'future':2,'futuro':2,'reaction':2,'reacción':2,'decision':2,'decisión':2,'statement':2,'declaraciones':2,'suspension':3,'suspensión':3,'coach':2,'entrenador':2,'training':1,'entrenamiento':1,'family':2,'familia':2,'story':2,'historia':2,'record':2,'récord':2,'extension':2,'renovación':2,'rumor':2,'rumores':2,'breaks silence':3,'rompe el silencio':3,'free agent':2,'agente libre':2}
RESULT_ONLY = ('final score','box score','live score','live updates','play by play','minute by minute','minuto a minuto','resultado en vivo','marcador final','dónde ver','donde ver','how to watch','odds','apuestas','betting odds','pronóstico','pronostico','horario y canal','schedule and results')
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; MXATH-Editorial-RSS/1.0; +https://github.com/barriglez33/MXATH)','Accept':'application/rss+xml,application/xml;q=0.9,*/*;q=0.8'}

def load_json(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError): return default

def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')

def normalize(value):
    import unicodedata
    value=unicodedata.normalize('NFKD',value or '')
    value=''.join(c for c in value if not unicodedata.combining(c))
    return re.sub(r'\s+',' ',re.sub('[^a-z0-9]+',' ',value.lower())).strip()

def editorial_score(title, summary):
    text=normalize((title or '')+' '+(summary or ''))
    score=sum(points for word,points in POSITIVE.items() if normalize(word) in text)
    if any(normalize(word) in normalize(title) for word in RESULT_ONLY): score-=8
    if re.search(r'\b\d{1,3}\s*[-–]\s*\d{1,3}\b', title or '') and not any(normalize(w) in text for w in POSITIVE): score-=4
    return score

def make_queries(athletes, cursor, budget):
    # Always cover the high-volume names; rotate through everyone else over successive runs.
    priority=['Canelo Álvarez','Sergio Pérez','Javier Hernández','Hirving Lozano','Karim López','Isaac del Toro']
    by_name={a['name']:a for a in athletes}
    def phrase(a):
        primary='"'+a['name']+'"'
        if a['aliases']:
            alias='"'+a['aliases'][0]+'"'
            if normalize(a['name']) != normalize(a['aliases'][0]):
                return '('+primary+' OR '+alias+')'
        return primary
    fixed=[]
    for name in priority:
        a=by_name.get(name)
        if a: fixed.append((a,phrase(a)))
    roster=[a for a in athletes if a['name'] not in priority]
    slots=max(1,budget-len(fixed))
    rotate=[roster[(cursor+i)%len(roster)] for i in range(min(slots,len(roster)))] if roster else []
    rotating=[(a,phrase(a)) for a in rotate]
    next_cursor=(cursor+len(rotate)) % len(roster) if roster else 0
    # Two locales per name; capped by budget of *people* not total network requests.
    return fixed+rotating,next_cursor

def query_url(query, market, lookback):
    hl,gl,ceid=market
    search=query+' when:'+str(max(1,(int(lookback)+23)//24))+'d'
    return 'https://news.google.com/rss/search?'+urlencode({'q':search,'hl':hl,'gl':gl,'ceid':ceid})

def parse_time(entry):
    for key in ('published_parsed','updated_parsed'):
        if entry.get(key):
            try:return datetime.fromtimestamp(calendar.timegm(entry[key]),timezone.utc)
            except (TypeError, ValueError, OverflowError):pass
    for key in ('published','updated'):
        if entry.get(key):
            try:return date_parser.parse(entry[key]).astimezone(timezone.utc)
            except (ValueError,TypeError,OverflowError):pass
    return None

def extract_source(entry):
    source=entry.get('source') or {}
    return source.get('title','') if isinstance(source,dict) else getattr(source,'title','')

def clean_title(title,source):
    title=html.unescape(BeautifulSoup(title or '','html.parser').get_text(' ',strip=True))
    if source and title.lower().endswith(' - '+source.lower()): return title[:-(len(source)+3)].strip()
    return title

def key_for(entry, title):
    link=entry.get('link','')
    key=entry.get('id') or link or normalize(title)
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]

def title_is_noise(title,score):
    return score < 0 and any(normalize(phrase) in normalize(title) for phrase in RESULT_ONLY)

def build_rss(articles, feed):
    ET.register_namespace('atom','http://www.w3.org/2005/Atom')
    rss=ET.Element('rss',{'version':'2.0','xmlns:content':'http://purl.org/rss/1.0/modules/content/'})
    channel=ET.SubElement(rss,'channel')
    for tag,value in [('title',feed['title']),('link',feed['link']),('description',feed['description']),('language',feed['language'])]: ET.SubElement(channel,tag).text=value
    ET.SubElement(channel,'lastBuildDate').text=datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
    for item in sorted(articles,key=lambda x:x['published'],reverse=True):
        node=ET.SubElement(channel,'item')
        for tag,key in [('title','title'),('link','link'),('guid','id'),('description','description')]:
            el=ET.SubElement(node,tag)
            if tag=='guid':el.set('isPermaLink','false')
            el.text=item.get(key,'')
        ET.SubElement(node,'pubDate').text=datetime.fromisoformat(item['published']).strftime('%a, %d %b %Y %H:%M:%S GMT')
        ET.SubElement(node,'category').text=item.get('category','')
        ET.SubElement(node,'author').text=item.get('source','')
    tree=ET.ElementTree(rss)
    ET.indent(tree,space='  ')
    destination=ROOT/'docs/feed.xml'; destination.parent.mkdir(parents=True,exist_ok=True)
    tree.write(destination,encoding='utf-8',xml_declaration=True)
    ET.parse(destination)

def run():
    cfg=load_json(ROOT/'config.json',{})
    if not cfg.get('athletes') or not cfg.get('scanner'):raise RuntimeError('Missing config.json athletes/scanner')
    opts=cfg['scanner']; athletes=cfg['athletes']; state=load_json(ROOT/'data/state.json',{'cursor':0})
    existing=load_json(ROOT/'data/articles.json',[])
    now=datetime.now(timezone.utc); cutoff=now-timedelta(hours=opts['lookback_hours'])
    expire=now-timedelta(days=opts['retain_days'])
    existing=[x for x in existing if x.get('published') and datetime.fromisoformat(x['published'])>=expire]
    seen={x['id'] for x in existing}
    searches,new_cursor=make_queries(athletes,int(state.get('cursor',0)),opts['queries_per_run'])
    stats=Counter(); stats['profiles_total']=len(athletes)
    session=requests.Session(); session.headers.update(HEADERS)
    started=time.monotonic(); new=[]
    for athlete,query in searches:
        for market in MARKETS:
            stats['requests']+=1
            url=query_url(query,market,opts['lookback_hours'])
            try:
                response=session.get(url,timeout=opts['request_timeout_seconds']);response.raise_for_status()
                feed=feedparser.parse(response.content)
                if feed.bozo and not feed.entries: raise RuntimeError(str(feed.bozo_exception))
            except (requests.RequestException,RuntimeError) as exc:
                stats['request_failed']+=1;LOG.warning('FETCH FAILED athlete=%s locale=%s error=%s',athlete['name'],market[0],exc);continue
            if not feed.entries:stats['empty_feeds']+=1
            stats['entries_seen']+=len(feed.entries)
            for entry in feed.entries[:opts['max_entries_per_query']]:
                pub=parse_time(entry)
                if not pub:stats['undated']+=1;continue
                if pub<cutoff or pub>now+timedelta(hours=1):stats['outside_window']+=1;continue
                source=extract_source(entry)
                title=clean_title(entry.get('title',''),source)
                link=entry.get('link','')
                if not link or not title:stats['invalid']+=1;continue
                if any(ex in (urlparse(link).hostname or '').lower() or ex in source.lower() for ex in opts.get('exclude_domains',[])):
                    stats['excluded_source']+=1;continue
                kid=key_for(entry,title)
                if kid in seen:stats['duplicates']+=1;continue
                snippet=BeautifulSoup(entry.get('summary',''),'html.parser').get_text(' ',strip=True)
                score=editorial_score(title,snippet)
                if title_is_noise(title,score) or score<int(opts.get('min_score',0)):
                    stats['editorial_rejected']+=1;continue
                seen.add(kid)
                item={'id':kid,'title':title,'link':link,'published':pub.isoformat(),'description':snippet[:1300], 'source':source,'category':athlete['category'],'athlete':athlete['name'],'score':score}
                new.append(item);stats['accepted']+=1
                if len(new)>=opts['max_new_per_run']:break
            LOG.info('SEARCH %s %s entries=%d total_accepted=%d',athlete['name'],market[0],len(feed.entries),stats['accepted'])
            if len(new)>=opts['max_new_per_run']:break
        if len(new)>=opts['max_new_per_run']:break
    # Persist cursor even on empty results, so the next scheduled run covers different athletes.
    state['cursor']=new_cursor
    state['last_run']=now.isoformat()
    state['last_stats']=dict(stats)
    save_json(ROOT/'data/state.json',state)
    articles=existing+new
    # Cross-query/cross-run duplicate headlines (different Google News URLs).
    unique={}
    for item in sorted(articles,key=lambda x:(x.get('score',0),x['published']),reverse=True):
        title_key=normalize(item['title'])
        if title_key not in unique:unique[title_key]=item
    articles=sorted(unique.values(),key=lambda x:x['published'],reverse=True)
    save_json(ROOT/'data/articles.json',articles)
    build_rss(articles,cfg['feed'])
    LOG.info('DIAGNOSTICS %s',json.dumps(dict(stats),ensure_ascii=False,sort_keys=True))
    LOG.info('OUTPUT total=%s new=%s elapsed=%.1fs docs/feed.xml',len(articles),len(new),time.monotonic()-started)
    if stats['requests'] and stats['request_failed']/stats['requests']>=float(opts['max_requests_fail_ratio']):
        raise RuntimeError('Nearly all Google News requests failed; see FETCH FAILED logs')

if __name__=='__main__':run()
