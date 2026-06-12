# -*- coding: utf-8 -*-
"""Example torrent scraper - copy this file to add your own source.

It queries a public torrent-index JSON API, turns each result's info_hash into
a magnet, and hands it back. Torbox then converts the magnet to a stream.

The whole contract is: build a query, fetch results, return source dicts.
Swap the URL/parsing for any indexer (Torznab/Jackett, a site's JSON, etc.).
"""
import requests

from .base import ScraperBase
from .. import kodi
from ..quality import parse_size_gb

API = 'https://apibay.org/q.php'
_NULL_HASH = '0000000000000000000000000000000000000000'


class ExampleTorrents(ScraperBase):
    name = 'example'        # settings key: scraper_example
    enabled = True

    def _query(self, term):
        try:
            r = requests.get(API, params={'q': term, 'cat': '200'}, timeout=15)
            r.raise_for_status()
            return r.json() or []
        except Exception as exc:  # noqa: BLE001
            kodi.log_error('example scraper query failed: {0}'.format(exc))
            return []

    def _to_sources(self, rows):
        out = []
        for row in rows:
            ih = row.get('info_hash', '')
            if not ih or ih == _NULL_HASH:
                continue
            name = row.get('name', '')
            size_bytes = int(row.get('size', 0) or 0)
            out.append({
                'release_title': name,
                'magnet': self.magnet_from_hash(ih, name),
                'size': round(size_bytes / (1024 ** 3), 2) if size_bytes else parse_size_gb(name),
                'seeders': int(row.get('seeders', 0) or 0),
                'source': self.name,
            })
        return out

    def scrape_movie(self, title, year, imdb=None, tmdb=None):
        term = '{0} {1}'.format(title, year).strip()
        return self._to_sources(self._query(term))

    def scrape_episode(self, show_title, year, season, episode, imdb=None, tmdb=None):
        term = '{0} S{1:02d}E{2:02d}'.format(show_title, int(season), int(episode))
        return self._to_sources(self._query(term))
