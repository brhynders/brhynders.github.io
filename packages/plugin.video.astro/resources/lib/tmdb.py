# -*- coding: utf-8 -*-
"""Minimal TMDB v3 client plus helpers to map TMDB JSON to Kodi info/art dicts.

Responses are cached (see cache.py): listings briefly, details/genres for days.
"""
import json
import threading

import requests

from . import kodi
from . import cache

API = 'https://api.themoviedb.org/3'
IMG = 'https://image.tmdb.org/t/p'
# Public default key (validated working). Users can override in settings.
DEFAULT_KEY = '1248868d7003f60f2386595db98455ef'

POSTER_SIZE = 'w500'
FANART_SIZE = 'w1280'
STILL_SIZE = 'w780'
PROFILE_SIZE = 'w185'

# cache TTLs (seconds)
TTL_LIST = 8 * 3600
TTL_DETAIL = 7 * 24 * 3600
TTL_GENRE = 30 * 24 * 3600

YOUTUBE = 'plugin://plugin.video.youtube/play/?video_id={0}'


def _key():
    return kodi.get_setting('tmdb_key', DEFAULT_KEY) or DEFAULT_KEY


def _lang():
    return kodi.get_setting('tmdb_lang', 'en-US') or 'en-US'


def _get(path, ttl=TTL_LIST, **params):
    params.setdefault('api_key', _key())
    params.setdefault('language', _lang())
    ck = 'tmdb:{0}:{1}'.format(path, json.dumps(params, sort_keys=True))
    hit = cache.get(ck)
    if hit is not None:
        return hit
    try:
        r = requests.get('{0}/{1}'.format(API, path.lstrip('/')), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001 - surface but never crash the menu
        kodi.log_error('TMDB request failed for {0}: {1}'.format(path, exc))
        return {}
    if data:
        cache.set(ck, data, ttl)
    return data


# ---------------------------------------------------------------------------
# Listing endpoints
# ---------------------------------------------------------------------------
def movies(category, page=1):
    paths = {
        'trending': 'trending/movie/week',
        'popular': 'movie/popular',
        'top_rated': 'movie/top_rated',
        'now_playing': 'movie/now_playing',
        'upcoming': 'movie/upcoming',
    }
    return _get(paths.get(category, 'movie/popular'), page=page)


def shows(category, page=1):
    paths = {
        'trending': 'trending/tv/week',
        'popular': 'tv/popular',
        'top_rated': 'tv/top_rated',
        'on_the_air': 'tv/on_the_air',
        'airing_today': 'tv/airing_today',
    }
    return _get(paths.get(category, 'tv/popular'), page=page)


def discover(media, genre_id, page=1):
    return _get('discover/{0}'.format(media), with_genres=genre_id, page=page,
                sort_by='popularity.desc')


def recommendations(media, tmdb_id, page=1):
    """TMDB 'recommendations' for a title - powers Because You Watched."""
    return _get('{0}/{1}/recommendations'.format(media, tmdb_id), page=page)


def genres(media):
    data = _get('genre/{0}/list'.format(media), ttl=TTL_GENRE)
    return data.get('genres', [])


def genre_map(media):
    return {g['id']: g['name'] for g in genres(media)}


def search(media, query, page=1):
    # short TTL so fresh searches aren't masked for long
    return _get('search/{0}'.format(media), ttl=3600, query=query, page=page,
                include_adult='false')


def movie_details(tmdb_id):
    return _get('movie/{0}'.format(tmdb_id), ttl=TTL_DETAIL,
                append_to_response='external_ids,credits,videos,release_dates')


def show_details(tmdb_id):
    return _get('tv/{0}'.format(tmdb_id), ttl=TTL_DETAIL,
                append_to_response='external_ids,credits,videos,content_ratings')


def season_details(tmdb_id, season_number):
    return _get('tv/{0}/season/{1}'.format(tmdb_id, season_number), ttl=TTL_DETAIL)


def _bulk(ids, fetch, workers=10):
    """Fetch details for many ids concurrently (cache makes repeats instant)."""
    out = {}
    sem = threading.Semaphore(workers)
    threads = []

    def work(i):
        with sem:
            out[i] = fetch(i)

    for i in ids:
        t = threading.Thread(target=work, args=(i,))
        t.daemon = True
        t.start()
        threads.append(t)
    for t in threads:
        t.join(25)
    return out


def bulk_movie_details(ids):
    return _bulk(ids, movie_details)


def bulk_show_details(ids):
    return _bulk(ids, show_details)


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------
def _img(path, size):
    return '{0}/{1}{2}'.format(IMG, size, path) if path else ''


def _year(date_str):
    return date_str[:4] if date_str else ''


def _cast(details):
    people = ((details.get('credits') or {}).get('cast') or [])[:25]
    return [{
        'name': c.get('name', ''),
        'role': c.get('character', ''),
        'order': c.get('order', i),
        'thumbnail': _img(c.get('profile_path'), PROFILE_SIZE),
    } for i, c in enumerate(people)]


def _directors(details):
    crew = (details.get('credits') or {}).get('crew') or []
    return [c['name'] for c in crew if c.get('job') == 'Director']


def _trailer(details):
    for v in (details.get('videos') or {}).get('results', []):
        if v.get('site') == 'YouTube' and v.get('type') == 'Trailer':
            return YOUTUBE.format(v.get('key'))
    return ''


def _movie_cert(details):
    for entry in (details.get('release_dates') or {}).get('results', []):
        if entry.get('iso_3166_1') == 'US':
            for rd in entry.get('release_dates', []):
                if rd.get('certification'):
                    return rd['certification']
    return ''


def _show_cert(details):
    for entry in (details.get('content_ratings') or {}).get('results', []):
        if entry.get('iso_3166_1') == 'US' and entry.get('rating'):
            return entry['rating']
    return ''


def _studios(details):
    return [c['name'] for c in details.get('production_companies', [])]


def map_movie(item, gmap=None, details=None):
    info = {
        'title': item.get('title') or item.get('original_title', ''),
        'plot': item.get('overview', ''),
        'year': _year(item.get('release_date', '')),
        'premiered': item.get('release_date', ''),
        'rating': item.get('vote_average', 0),
        'tmdb': item.get('id'),
    }
    if gmap and item.get('genre_ids'):
        info['genres'] = [gmap[g] for g in item['genre_ids'] if g in gmap]
    art = {
        'poster': _img(item.get('poster_path'), POSTER_SIZE),
        'thumb': _img(item.get('poster_path'), POSTER_SIZE),
        'fanart': _img(item.get('backdrop_path'), FANART_SIZE),
    }
    if details:
        info['genres'] = [g['name'] for g in details.get('genres', [])] or info.get('genres')
        if details.get('runtime'):
            info['duration'] = details['runtime'] * 60
        info['mpaa'] = _movie_cert(details)
        info['tagline'] = details.get('tagline', '')
        info['imdb'] = (details.get('external_ids') or {}).get('imdb_id', '')
        info['studio'] = _studios(details)
        info['cast'] = _cast(details)
        info['director'] = _directors(details)
        info['trailer'] = _trailer(details)
        if details.get('vote_average'):
            info['rating'] = details['vote_average']
    return info, art


def map_show(item, gmap=None, details=None):
    info = {
        'title': item.get('name') or item.get('original_name', ''),
        'tvshowtitle': item.get('name') or item.get('original_name', ''),
        'plot': item.get('overview', ''),
        'year': _year(item.get('first_air_date', '')),
        'premiered': item.get('first_air_date', ''),
        'rating': item.get('vote_average', 0),
        'tmdb': item.get('id'),
    }
    if gmap and item.get('genre_ids'):
        info['genres'] = [gmap[g] for g in item['genre_ids'] if g in gmap]
    art = {
        'poster': _img(item.get('poster_path'), POSTER_SIZE),
        'thumb': _img(item.get('poster_path'), POSTER_SIZE),
        'fanart': _img(item.get('backdrop_path'), FANART_SIZE),
    }
    if details:
        info['genres'] = [g['name'] for g in details.get('genres', [])] or info.get('genres')
        runtimes = details.get('episode_run_time') or []
        if runtimes:
            info['duration'] = runtimes[0] * 60
        info['mpaa'] = _show_cert(details)
        info['imdb'] = (details.get('external_ids') or {}).get('imdb_id', '')
        info['studio'] = _studios(details)
        info['cast'] = _cast(details)
        info['trailer'] = _trailer(details)
        if details.get('vote_average'):
            info['rating'] = details['vote_average']
    return info, art


def map_episode(item, show_info, show_art, cast=None):
    info = {
        'title': item.get('name', ''),
        'tvshowtitle': show_info.get('tvshowtitle', ''),
        'plot': item.get('overview', ''),
        'season': item.get('season_number'),
        'episode': item.get('episode_number'),
        'premiered': item.get('air_date', ''),
        'rating': item.get('vote_average', 0),
        'tmdb': show_info.get('tmdb'),
        'imdb': show_info.get('imdb'),
        'year': show_info.get('year'),
    }
    if item.get('runtime'):
        info['duration'] = item['runtime'] * 60
    if cast:
        info['cast'] = cast
    still = _img(item.get('still_path'), STILL_SIZE)
    art = {
        'poster': show_art.get('poster', ''),
        'thumb': still or show_art.get('poster', ''),
        'fanart': show_art.get('fanart', ''),
    }
    return info, art
