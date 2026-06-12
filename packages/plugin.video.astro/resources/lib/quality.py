# -*- coding: utf-8 -*-
"""Release-name parsing and source ranking - shared by every scraper."""
import re

from . import kodi

QUALITY_ORDER = {'4K': 4, '1080p': 3, '720p': 2, 'SD': 1, 'CAM': 0}

_PATTERNS = [
    ('4K', re.compile(r'\b(2160p|4k|uhd)\b', re.I)),
    ('1080p', re.compile(r'\b(1080p|1080i|fhd)\b', re.I)),
    ('720p', re.compile(r'\b(720p|hd)\b', re.I)),
    ('CAM', re.compile(r'\b(cam|camrip|hdcam|ts|telesync|hdts|scr|screener)\b', re.I)),
    ('SD', re.compile(r'\b(480p|360p|dvdrip|web-?dl|webrip|bluray|brrip|xvid)\b', re.I)),
]

_SIZE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(gb|mb)', re.I)


def parse_quality(release_title):
    title = release_title or ''
    for label, pattern in _PATTERNS:
        if pattern.search(title):
            return label
    return 'SD'


def parse_size_gb(text):
    """Best-effort size extraction from a release name; returns GB float or 0."""
    m = _SIZE_RE.search(text or '')
    if not m:
        return 0.0
    value = float(m.group(1))
    return value / 1024.0 if m.group(2).lower() == 'mb' else value


def _rank(source):
    q = QUALITY_ORDER.get(source.get('quality', 'SD'), 1)
    seeders = source.get('seeders', 0) or 0
    return (q, seeders, source.get('size', 0) or 0)


def sort_sources(sources):
    """Apply the quality floor from settings, then sort best-first."""
    floor_label = kodi.get_setting('min_quality', 'SD')
    floor = QUALITY_ORDER.get(floor_label, 0)
    filtered = [s for s in sources
                if QUALITY_ORDER.get(s.get('quality', 'SD'), 1) >= floor]
    filtered.sort(key=_rank, reverse=True)
    limit = kodi.get_int('results_limit', 50)
    return filtered[:limit] if limit else filtered


def label_for(source):
    """Human label for the source-selection dialog."""
    bits = [source.get('quality', 'SD')]
    if source.get('size'):
        bits.append('{0:.2f} GB'.format(source['size']))
    if source.get('seeders'):
        bits.append('{0} S'.format(source['seeders']))
    bits.append('[{0}]'.format(source.get('source', '?')))
    title = source.get('release_title', '')
    return '{0}  -  {1}'.format(' | '.join(bits), title)
