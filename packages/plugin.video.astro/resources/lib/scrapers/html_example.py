# -*- coding: utf-8 -*-
"""Disabled template showing how to scrape an HTML index with CSS selectors.

To use: copy this file, point the URLs at a real site, fix the selectors, set
enabled = True, and install the script.module.beautifulsoup4 add-on. The engine
visits movie_url/episode_url, iterates rows matching row_selector, and pulls each
field with its {css, attr} selector ('text' = element text, else an attribute).
"""
from .base import HtmlScraper


class HtmlExample(HtmlScraper):
    name = 'htmlexample'
    enabled = False                       # template only - never runs

    movie_url = 'https://example.org/search?q={query}'
    episode_url = 'https://example.org/search?q={title_url}+{se}'

    row_selector = 'tr.result'
    fields = {
        'release_title': {'css': 'a.name', 'attr': 'text'},
        'magnet': {'css': 'a[href^="magnet:"]', 'attr': 'href'},
        'size': {'css': 'td.size', 'attr': 'text'},
        'seeders': {'css': 'td.seeders', 'attr': 'text'},
    }
