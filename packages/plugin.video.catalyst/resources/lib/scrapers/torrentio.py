# -*- coding: utf-8 -*-
"""Torrentio - a debrid-oriented torrent indexer keyed by IMDb id. Covers both
movies and TV, and because it's built for debrid services its results have high
Torbox cache-hit rates. Size/seeders are embedded in each stream's title text;
the registry parses those out, so this stays a pure ApiScraper config."""
from .base import ApiScraper


class Torrentio(ApiScraper):
    name = 'torrentio'                    # settings key: scraper_torrentio
    enabled = True

    movie_url = 'https://torrentio.strem.fun/stream/movie/{imdb}.json'
    episode_url = 'https://torrentio.strem.fun/stream/series/{imdb}:{season}:{episode}.json'
    results_path = 'streams'
    fields = {'release_title': 'title', 'hash': 'infoHash'}
