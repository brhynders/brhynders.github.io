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
_BTIH_RE = re.compile(r'btih:([a-fA-F0-9]{40})', re.I)


def _dedup_key(source):
    """Identify the same torrent across sources by its info-hash."""
    m = _BTIH_RE.search(source.get('magnet', '') or '')
    if m:
        return m.group(1).lower()
    return (source.get('url') or source.get('release_title', '')).lower().strip()


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


def _q(source):
    return QUALITY_ORDER.get(source.get('quality', 'SD'), 1)


def _passes_filters(source):
    """Apply the Settings > Sources > Filter options."""
    q = _q(source)
    floor = QUALITY_ORDER.get(kodi.get_setting('min_quality', 'SD'), 0)
    ceil = QUALITY_ORDER.get(kodi.get_setting('max_quality', '4K'), 4)
    if q < floor or q > ceil:
        return False
    if kodi.get_bool('hide_cam', True) and source.get('quality') == 'CAM':
        return False
    min_seeders = kodi.get_int('min_seeders', 0)
    if min_seeders and (source.get('seeders') or 0) < min_seeders:
        return False
    max_size = kodi.get_int('max_size_gb', 0)
    size = source.get('size') or 0
    if max_size and size and size > max_size:
        return False
    return True


def _sort_key(source):
    q = _q(source)
    seeders = source.get('seeders', 0) or 0
    size = source.get('size', 0) or 0
    field = kodi.get_setting('sort_by', 'quality')
    if field == 'seeders':
        return (seeders, q, size)
    if field == 'size':
        return (size, q, seeders)
    return (q, seeders, size)


def sort_sources(sources):
    """Filter, sort and de-dupe sources per the user's Sources settings."""
    filtered = [s for s in sources if _passes_filters(s)]
    filtered.sort(key=_sort_key, reverse=True)
    # Same release often appears from multiple indexers - keep the best-ranked
    # copy of each info-hash (already sorted, so the first seen is the best).
    seen, deduped = set(), []
    for s in filtered:
        key = _dedup_key(s)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(s)
    limit = kodi.get_int('results_limit', 50)
    return deduped[:limit] if limit else deduped


def label_for(source):
    """Human label for the source-selection dialog (style from settings)."""
    style = kodi.get_setting('label_style', 'detailed')
    quality = source.get('quality', 'SD')
    title = source.get('release_title', '')
    if style == 'minimal':
        return '{0}  -  {1}'.format(quality, title)
    bits = [quality]
    if source.get('size'):
        bits.append('{0:.2f} GB'.format(source['size']))
    if style == 'detailed':
        if source.get('seeders'):
            bits.append('{0} S'.format(source['seeders']))
        bits.append('[{0}]'.format(source.get('source', '?')))
    return '{0}  -  {1}'.format(' | '.join(bits), title)
