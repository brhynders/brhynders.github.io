# -*- coding: utf-8 -*-
"""apibay - the JSON API behind The Pirate Bay. A flat list of torrents with an
info_hash each, so it's a pure ApiScraper config (no method code)."""
from .base import ApiScraper


class Apibay(ApiScraper):
    name = 'apibay'                       # settings key: scraper_apibay
    enabled = True

    movie_url = 'https://apibay.org/q.php?q={query}&cat=200'
    episode_url = 'https://apibay.org/q.php?q={title_url}+{se}&cat=200'
    results_path = ''                     # the response IS the list
    fields = {'release_title': 'name', 'hash': 'info_hash',
              'size': 'size', 'seeders': 'seeders'}
    size_unit = 'bytes'
    # apibay's "no results" sentinel row has an all-zero info_hash, which
    # magnet_from_hash() rejects, so it's dropped automatically.
