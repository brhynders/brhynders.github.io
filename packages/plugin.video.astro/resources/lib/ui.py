# -*- coding: utf-8 -*-
"""Builds every directory screen from native Kodi list items."""
import xbmcplugin

from . import kodi
from . import tmdb
from . import trakt

ART = {'icon': kodi.ADDON_ICON, 'fanart': kodi.ADDON_FANART}

# Per-folder icons drawn from the active skin's built-in "Default*.png" set, so
# they look native to the user's skin and need no bundled assets.
ICONS = {
    'movies': 'DefaultMovies.png',
    'tvshows': 'DefaultTVShows.png',
    'search': 'DefaultAddonsSearch.png',
    'tools': 'DefaultAddonProgram.png',
    'settings': 'DefaultAddonService.png',
    'genres': 'DefaultGenre.png',
    'trending': 'DefaultRecentlyAddedMovies.png',
    'popular': 'DefaultFavourites.png',
    'now_playing': 'DefaultInProgressShows.png',
    'on_the_air': 'DefaultInProgressShows.png',
    'airing_today': 'DefaultInProgressShows.png',
    'top_rated': 'DefaultMusicTop100.png',
    'upcoming': 'DefaultYear.png',
    'trakt': 'DefaultFavourites.png',
    'because': 'DefaultRecentlyAddedEpisodes.png',
    'continue': 'DefaultInProgressShows.png',
    'watchlist': 'DefaultPlaylist.png',
    'collection': 'DefaultVideoPlaylists.png',
    'recommended': 'DefaultFavourites.png',
    'anticipated': 'DefaultYear.png',
    'lists': 'DefaultPlaylist.png',
}


def folder_art(key):
    """Art dict for a folder row using a skin Default icon (falls back to logo)."""
    icon = ICONS.get(key, kodi.ADDON_ICON)
    return {'icon': icon, 'thumb': icon, 'fanart': kodi.ADDON_FANART}


def _trakt_ctx(media, tmdb_id, season=None, episode=None):
    """Build Trakt context-menu entries for a row (empty if not authorised)."""
    if not trakt.is_authorised():
        return []
    base = {'action': 'trakt_action', 'media': media, 'tmdb': tmdb_id}
    if season is not None:
        base.update({'season': season, 'episode': episode})
    items = []
    for label, do in (('Trakt: Watchlist +', 'wl_add'),
                      ('Trakt: Watchlist -', 'wl_rem'),
                      ('Trakt: Mark watched', 'hist_add'),
                      ('Trakt: Mark unwatched', 'hist_rem')):
        # episodes can't be watchlisted at episode level here; skip those two
        if season is not None and do.startswith('wl_'):
            continue
        url = kodi.build_url(do=do, **base)
        items.append((label, 'RunPlugin({0})'.format(url)))
    return items

MOVIE_CATS = [
    ('Trending', 'trending'),
    ('Popular', 'popular'),
    ('Now Playing', 'now_playing'),
    ('Top Rated', 'top_rated'),
    ('Upcoming', 'upcoming'),
]
SHOW_CATS = [
    ('Trending', 'trending'),
    ('Popular', 'popular'),
    ('On The Air', 'on_the_air'),
    ('Airing Today', 'airing_today'),
    ('Top Rated', 'top_rated'),
]


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------
def root():
    kodi.add_directory('Movies', {'action': 'movies_menu'}, art=folder_art('movies'))
    kodi.add_directory('TV Shows', {'action': 'shows_menu'}, art=folder_art('tvshows'))
    kodi.add_directory('Search', {'action': 'search_menu'}, art=folder_art('search'))
    kodi.add_directory('Tools', {'action': 'tools'}, art=folder_art('tools'))
    kodi.end_directory(content='')


def movies_menu():
    for label, cat in MOVIE_CATS:
        kodi.add_directory(label, {'action': 'movies_list', 'category': cat},
                           art=folder_art(cat))
    kodi.add_directory('Genres', {'action': 'genres', 'media': 'movie'},
                       art=folder_art('genres'))
    kodi.add_directory('Search Movies', {'action': 'search', 'media': 'movie'},
                       art=folder_art('search'))
    if trakt.is_authorised():
        kodi.add_directory('Because You Watched', {'action': 'watched_seeds', 'media': 'movie'},
                           art=folder_art('because'))
        kodi.add_directory('Trakt', {'action': 'trakt_menu', 'media': 'movie'},
                           art=folder_art('trakt'))
    kodi.end_directory(content='')


def shows_menu():
    for label, cat in SHOW_CATS:
        kodi.add_directory(label, {'action': 'shows_list', 'category': cat},
                           art=folder_art(cat))
    kodi.add_directory('Genres', {'action': 'genres', 'media': 'tv'},
                       art=folder_art('genres'))
    kodi.add_directory('Search TV Shows', {'action': 'search', 'media': 'tv'},
                       art=folder_art('search'))
    if trakt.is_authorised():
        kodi.add_directory('Because You Watched', {'action': 'watched_seeds', 'media': 'tv'},
                           art=folder_art('because'))
        kodi.add_directory('Trakt', {'action': 'trakt_menu', 'media': 'tv'},
                           art=folder_art('trakt'))
    kodi.end_directory(content='')


def search_menu():
    kodi.add_directory('Search Movies', {'action': 'search', 'media': 'movie'},
                       art=folder_art('search'))
    kodi.add_directory('Search TV Shows', {'action': 'search', 'media': 'tv'},
                       art=folder_art('search'))
    kodi.end_directory(content='')


def genres(media):
    for g in tmdb.genres(media):
        kodi.add_directory(g['name'],
                           {'action': 'discover', 'media': media, 'genre': g['id']},
                           art=folder_art('genres'))
    kodi.end_directory(content='')


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------
def _rich():
    return kodi.get_bool('rich_metadata', True)


def _movie_row(item, gmap=None, details=None, watched=None, resume=None):
    info, art = tmdb.map_movie(item, gmap=gmap, details=details)
    if not info['title']:
        return
    if watched and info['tmdb'] in watched:
        info['playcount'] = 1
    if resume:
        info['resume'] = resume
    kodi.add_playable(info['title'],
                      {'action': 'play_movie', 'tmdb_id': info['tmdb']},
                      info=info, art=art, media_type='movie',
                      context_menu=_trakt_ctx('movie', info['tmdb']))


def episode_row(tmdb_id, season, episode, show_title, year, imdb, info, art, resume=None):
    """Add a playable episode row (shared by the season view and Continue Watching)."""
    if resume:
        info['resume'] = resume
    label = '{0} - {1}x{2:02d}. {3}'.format(show_title, season, episode, info.get('title', ''))
    kodi.add_playable(label,
                      {'action': 'play_episode', 'tmdb_id': tmdb_id, 'season': season,
                       'episode': episode, 'show_title': show_title, 'year': year,
                       'imdb': imdb},
                      info=info, art=art, media_type='episode',
                      context_menu=_trakt_ctx('tv', tmdb_id, season=season, episode=episode))


def _show_row(item, gmap=None, details=None, watched=None):
    info, art = tmdb.map_show(item, gmap=gmap, details=details)
    if not info['title']:
        return
    kodi.add_directory(info['title'],
                       {'action': 'seasons', 'tmdb_id': info['tmdb']},
                       info=info, art=art, media_type='tvshow')


def _enrich(media, items):
    """Return (genre_map, {id: details}, watched_set) for a page of results."""
    gmap = tmdb.genre_map(media)
    details = {}
    if _rich() and items:
        ids = [it['id'] for it in items if it.get('id')]
        details = (tmdb.bulk_movie_details(ids) if media == 'movie'
                   else tmdb.bulk_show_details(ids))
    watched = trakt.watched_movie_ids() if media == 'movie' else set()
    return gmap, details, watched


def _paged(data, page, more_params):
    page = int(page)
    total = int(data.get('total_pages', 1) or 1)
    if page < total:
        nxt = dict(more_params)
        nxt['page'] = page + 1
        kodi.add_directory('Next Page >>', nxt, art=ART)


def movies_list(category, page=1):
    data = tmdb.movies(category, page=page)
    items = data.get('results', [])
    gmap, details, watched = _enrich('movie', items)
    for item in items:
        _movie_row(item, gmap=gmap, details=details.get(item.get('id')), watched=watched)
    _paged(data, page, {'action': 'movies_list', 'category': category})
    kodi.end_directory(content='movies',
                       sort_methods=[xbmcplugin.SORT_METHOD_NONE,
                                     xbmcplugin.SORT_METHOD_VIDEO_YEAR,
                                     xbmcplugin.SORT_METHOD_TITLE])


def shows_list(category, page=1):
    data = tmdb.shows(category, page=page)
    items = data.get('results', [])
    gmap, details, _watched = _enrich('tv', items)
    for item in items:
        _show_row(item, gmap=gmap, details=details.get(item.get('id')))
    _paged(data, page, {'action': 'shows_list', 'category': category})
    kodi.end_directory(content='tvshows')


def _mixed_rows(media, items):
    gmap, details, watched = _enrich(media, items)
    for item in items:
        d = details.get(item.get('id'))
        if media == 'movie':
            _movie_row(item, gmap=gmap, details=d, watched=watched)
        else:
            _show_row(item, gmap=gmap, details=d)


def discover(media, genre, page=1):
    data = tmdb.discover(media, genre, page=page)
    _mixed_rows(media, data.get('results', []))
    _paged(data, page, {'action': 'discover', 'media': media, 'genre': genre})
    kodi.end_directory(content='movies' if media == 'movie' else 'tvshows')


def recommendations(media, tmdb_id, page=1):
    data = tmdb.recommendations(media, tmdb_id, page=page)
    _mixed_rows(media, data.get('results', []))
    _paged(data, page, {'action': 'recommendations', 'media': media, 'tmdb': tmdb_id})
    kodi.end_directory(content='movies' if media == 'movie' else 'tvshows')


def search(media, page=1, query=None):
    if not query:
        query = kodi.keyboard('Search')
        if not query:
            kodi.end_directory(content='')
            return
    data = tmdb.search(media, query, page=page)
    _mixed_rows(media, data.get('results', []))
    _paged(data, page, {'action': 'search', 'media': media, 'query': query})
    kodi.end_directory(content='movies' if media == 'movie' else 'tvshows')


# ---------------------------------------------------------------------------
# TV drill-down
# ---------------------------------------------------------------------------
def seasons(tmdb_id):
    details = tmdb.show_details(tmdb_id)
    show_info, show_art = tmdb.map_show(details, details=details)
    imdb = (details.get('external_ids') or {}).get('imdb_id', '')
    for season in details.get('seasons', []):
        num = season.get('season_number')
        if num is None or num == 0:  # skip "Specials" by default
            continue
        info = dict(show_info)
        info['season'] = num
        info['plot'] = season.get('overview') or show_info.get('plot', '')
        art = dict(show_art)
        if season.get('poster_path'):
            art['poster'] = art['thumb'] = '{0}/{1}{2}'.format(
                tmdb.IMG, tmdb.POSTER_SIZE, season['poster_path'])
        kodi.add_directory('Season {0}'.format(num),
                           {'action': 'episodes', 'tmdb_id': tmdb_id, 'season': num,
                            'show_title': show_info['title'], 'year': show_info.get('year', ''),
                            'imdb': imdb},
                           info=info, art=art, media_type='season')
    kodi.end_directory(content='seasons')


def episodes(tmdb_id, season, show_title, year, imdb=''):
    details = tmdb.show_details(tmdb_id)
    show_info, show_art = tmdb.map_show(details, details=details)
    show_info['imdb'] = imdb
    cast = show_info.get('cast') if _rich() else None
    watched = trakt.watched_episode_map().get(str(tmdb_id), set())
    season_data = tmdb.season_details(tmdb_id, season)
    for ep in season_data.get('episodes', []):
        epnum = ep.get('episode_number')
        info, art = tmdb.map_episode(ep, show_info, show_art, cast=cast)
        if (int(season), epnum) in watched:
            info['playcount'] = 1
        label = '{0}x{1:02d}. {2}'.format(season, epnum or 0, info['title'])
        kodi.add_playable(label,
                          {'action': 'play_episode', 'tmdb_id': tmdb_id, 'season': season,
                           'episode': epnum, 'show_title': show_title,
                           'year': year, 'imdb': imdb},
                          info=info, art=art, media_type='episode',
                          context_menu=_trakt_ctx('tv', tmdb_id, season=season, episode=epnum))
    kodi.end_directory(content='episodes')


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
def tools():
    from .resolvers import torbox
    from . import scrapers
    tb = 'configured' if torbox.is_configured() else 'NOT set'
    tk = 'authorised' if trakt.is_authorised() else 'not authorised'
    kodi.add_directory('Settings', {'action': 'settings'}, art=folder_art('settings'))
    kodi.add_directory('Torbox API key: {0}'.format(tb), {'action': 'settings'},
                       art=folder_art('tools'))
    kodi.add_directory('Trakt: {0}'.format(tk), {'action': 'settings'},
                       art=folder_art('trakt'))
    enabled = [n for n, on in scrapers.available() if on]
    kodi.add_directory('Active scrapers: {0}'.format(', '.join(enabled) or 'none'),
                       {'action': 'settings'}, art=folder_art('tools'))
    kodi.add_directory('Clear cache', {'action': 'clear_cache'}, art=folder_art('tools'))
    kodi.end_directory(content='')
