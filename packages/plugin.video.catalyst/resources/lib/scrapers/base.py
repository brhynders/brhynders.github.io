# -*- coding: utf-8 -*-
"""Scraper bases.

Three ways to add a source, simplest first:

1. ApiScraper  - a JSON API. Declare URL templates + where the list lives +
   which keys map to our fields. No method code needed. (see torrentio.py)
2. HtmlScraper - an HTML page. Declare URL templates + a row CSS selector +
   per-field {css, attr} selectors. (see html_example.py)
3. ScraperBase - full control: subclass and implement scrape_movie /
   scrape_episode yourself for anything the declarative bases can't express.

Every scraper returns a list of "source" dicts:
    {'release_title': str, 'magnet'|'url': str,
     'quality'?: str, 'size'?: float GB, 'seeders'?: int, 'source'?: str}

URL templates may use these substitution vars:
    {title} {title_url} {year} {query} {imdb} {imdb_num} {tmdb}
    {season} {episode} {season2} {episode2} {se}        (e.g. se = S01E05)
"""
import re
from urllib.parse import quote_plus

from .. import kodi
from ..quality import parse_size_gb

# `requests` imported lazily in _fetch - off the import path until a scrape runs.

_HASH_RE = re.compile(r'^[a-fA-F0-9]{40}$')

# Many indexers reject the default "python-requests" UA (e.g. Torrentio 403s).
DEFAULT_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
}


def _valid_hash(h):
    return bool(h) and bool(_HASH_RE.match(h)) and set(h) != {'0'}


class ScraperBase(object):
    name = 'base'
    enabled = True
    timeout = 15
    headers = None

    def scrape_movie(self, title, year, imdb=None, tmdb=None):
        return []

    def scrape_episode(self, show_title, year, season, episode, imdb=None, tmdb=None):
        return []

    # -- shared helpers ------------------------------------------------------
    @staticmethod
    def magnet_from_hash(info_hash, name=''):
        if not _valid_hash(info_hash):
            return None
        trackers = (
            '&tr=udp://tracker.opentrackr.org:1337/announce'
            '&tr=udp://open.demonii.com:1337/announce'
            '&tr=udp://tracker.openbittorrent.com:6969/announce'
        )
        dn = '&dn={0}'.format(quote_plus(name)) if name else ''
        return 'magnet:?xt=urn:btih:{0}{1}{2}'.format(info_hash, dn, trackers)

    @staticmethod
    def _ctx(title=None, year=None, season=None, episode=None, imdb=None, tmdb=None):
        def pad(v):
            try:
                return '{0:02d}'.format(int(v))
            except (TypeError, ValueError):
                return ''
        se = ''
        if season not in (None, '') and episode not in (None, ''):
            se = 'S{0}E{1}'.format(pad(season), pad(episode))
        query = ' '.join(str(x) for x in (title, year) if x)
        imdb = imdb or ''
        return {
            'title': title or '',
            'title_url': quote_plus(title or ''),
            'year': year or '',
            'query': quote_plus(query),
            'imdb': imdb,
            'imdb_num': imdb.replace('tt', ''),
            'tmdb': tmdb or '',
            'season': season if season not in (None, '') else '',
            'episode': episode if episode not in (None, '') else '',
            'season2': pad(season),
            'episode2': pad(episode),
            'se': se,
        }

    def _fetch(self, url):
        import requests
        headers = dict(DEFAULT_HEADERS)
        if self.headers:
            headers.update(self.headers)
        r = requests.get(url, headers=headers, timeout=self.timeout)
        r.raise_for_status()
        return r


class ApiScraper(ScraperBase):
    """JSON source defined entirely by class attributes."""
    movie_url = None
    episode_url = None
    results_path = ''          # dotted path to the results list ('' = root)
    fields = {}                # our key -> source json key
    size_unit = 'auto'         # bytes | mb | gb | auto

    def _list(self, data):
        node = data
        for part in (p for p in self.results_path.split('.') if p):
            node = node.get(part, []) if isinstance(node, dict) else []
        return node if isinstance(node, list) else []

    def _size_gb(self, raw, title):
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return parse_size_gb(str(raw)) or parse_size_gb(title)
        if self.size_unit == 'bytes':
            return round(val / 1024 ** 3, 2)
        if self.size_unit == 'mb':
            return round(val / 1024, 2)
        if self.size_unit == 'gb':
            return round(val, 2)
        return round(val / 1024 ** 3, 2) if val > 100000 else round(val, 2)  # auto

    def _row(self, row):
        f = self.fields
        title = row.get(f.get('release_title', ''), '') or row.get('title') or row.get('name', '')
        src = {'release_title': title, 'source': self.name}
        if f.get('magnet'):
            src['magnet'] = row.get(f['magnet'])
        elif f.get('hash'):
            src['magnet'] = self.magnet_from_hash(row.get(f['hash'], ''), title)
        elif f.get('url'):
            src['url'] = row.get(f['url'])
        if f.get('size') and row.get(f['size']) is not None:
            src['size'] = self._size_gb(row.get(f['size']), title)
        if f.get('seeders'):
            try:
                src['seeders'] = int(row.get(f['seeders']) or 0)
            except (TypeError, ValueError):
                pass
        return src if (src.get('magnet') or src.get('url')) else None

    def _run(self, url):
        if not url:
            return []
        try:
            data = self._fetch(url).json()
        except Exception as exc:  # noqa: BLE001
            kodi.log_error('{0}: api fetch failed: {1}'.format(self.name, exc))
            return []
        out = []
        for row in self._list(data):
            if isinstance(row, dict):
                s = self._row(row)
                if s:
                    out.append(s)
        return out

    def scrape_movie(self, title, year, imdb=None, tmdb=None):
        if not self.movie_url:
            return []
        return self._run(self.movie_url.format(**self._ctx(title, year, imdb=imdb, tmdb=tmdb)))

    def scrape_episode(self, show_title, year, season, episode, imdb=None, tmdb=None):
        if not self.episode_url:
            return []
        return self._run(self.episode_url.format(
            **self._ctx(show_title, year, season, episode, imdb, tmdb)))


class HtmlScraper(ScraperBase):
    """HTML source defined by a row selector + per-field CSS selectors.

    fields values are dicts: {'css': 'a.magnet', 'attr': 'href'} where attr is
    'text' (default) or an attribute name. Needs script.module.beautifulsoup4.
    """
    movie_url = None
    episode_url = None
    row_selector = 'tr'
    fields = {}

    def _soup(self, html):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            kodi.log_error('{0}: install script.module.beautifulsoup4 to use HTML '
                           'scrapers'.format(self.name))
            return None
        return BeautifulSoup(html, 'html.parser')

    def _row(self, row):
        data = {}
        for key, spec in self.fields.items():
            el = row.select_one(spec['css']) if spec.get('css') else row
            if el is None:
                continue
            attr = spec.get('attr', 'text')
            data[key] = el.get_text(strip=True) if attr == 'text' else (el.get(attr) or '')
        title = data.get('release_title', '')
        src = {'release_title': title, 'source': self.name}
        if data.get('magnet'):
            src['magnet'] = data['magnet']
        elif data.get('hash'):
            src['magnet'] = self.magnet_from_hash(data['hash'], title)
        elif data.get('url'):
            src['url'] = data['url']
        if data.get('size'):
            src['size'] = parse_size_gb(data['size'])
        if data.get('seeders'):
            m = re.search(r'\d+', str(data['seeders']))
            if m:
                src['seeders'] = int(m.group())
        return src if (src.get('magnet') or src.get('url')) else None

    def _run(self, url):
        if not url:
            return []
        try:
            html = self._fetch(url).text
        except Exception as exc:  # noqa: BLE001
            kodi.log_error('{0}: html fetch failed: {1}'.format(self.name, exc))
            return []
        soup = self._soup(html)
        if soup is None:
            return []
        out = []
        for row in soup.select(self.row_selector):
            s = self._row(row)
            if s:
                out.append(s)
        return out

    def scrape_movie(self, title, year, imdb=None, tmdb=None):
        if not self.movie_url:
            return []
        return self._run(self.movie_url.format(**self._ctx(title, year, imdb=imdb, tmdb=tmdb)))

    def scrape_episode(self, show_title, year, season, episode, imdb=None, tmdb=None):
        if not self.episode_url:
            return []
        return self._run(self.episode_url.format(
            **self._ctx(show_title, year, season, episode, imdb, tmdb)))
