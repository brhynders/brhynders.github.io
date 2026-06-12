# -*- coding: utf-8 -*-
"""Base class every source scraper inherits from.

To add a source: create a new file in this folder with a class that subclasses
ScraperBase, set `name`, and implement scrape_movie / scrape_episode. The
registry auto-discovers it - no wiring needed.

Each scraper returns a list of "source" dicts:
    {
        'release_title': str,   # the torrent/file name (used for quality parsing)
        'magnet':        str,   # magnet uri  (preferred for Torbox)   OR
        'url':           str,   # direct http(s) link to a torrent/file
        'quality':       str,   # optional; auto-parsed from release_title if absent
        'size':          float, # optional, in GB
        'seeders':       int,   # optional
        'source':        str,   # provider label shown to the user
    }
"""


class ScraperBase(object):
    name = 'base'
    # Flip to False in a subclass (or via settings) to skip it.
    enabled = True

    def scrape_movie(self, title, year, imdb=None, tmdb=None):
        """Return a list of source dicts for a movie. Override me."""
        return []

    def scrape_episode(self, show_title, year, season, episode, imdb=None, tmdb=None):
        """Return a list of source dicts for an episode. Override me."""
        return []

    # -- small shared helpers ------------------------------------------------
    @staticmethod
    def magnet_from_hash(info_hash, name=''):
        from urllib.parse import quote
        trackers = (
            '&tr=udp://tracker.opentrackr.org:1337/announce'
            '&tr=udp://open.demonii.com:1337/announce'
            '&tr=udp://tracker.openbittorrent.com:6969/announce'
        )
        dn = '&dn={0}'.format(quote(name)) if name else ''
        return 'magnet:?xt=urn:btih:{0}{1}{2}'.format(info_hash, dn, trackers)
