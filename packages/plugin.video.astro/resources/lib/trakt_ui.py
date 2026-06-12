# -*- coding: utf-8 -*-
"""Trakt-facing screens: device auth, list browsing and push actions.

Rendering reuses ui._movie_row / ui._show_row by resolving each Trakt entry's
TMDB id to full TMDB details (cached + concurrent), so Trakt lists look exactly
like the rest of the addon.
"""
import xbmc
import xbmcgui

from . import kodi
from . import tmdb
from . import trakt
from . import ui


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def authorise():
    dc = trakt._device_code()
    if not dc:
        kodi.ok('Could not reach Trakt to start authorisation.')
        return
    url = dc.get('verification_url', 'https://trakt.tv/activate')
    code = dc.get('user_code', '')
    device = dc.get('device_code')
    interval = int(dc.get('interval', 5))
    expires = int(dc.get('expires_in', 600))
    message = 'Go to: [B]{0}[/B]\nEnter code: [B]{1}[/B]'.format(url, code)

    pd = xbmcgui.DialogProgress()
    pd.create('Trakt Authorisation', message)
    waited = 0
    while waited < expires:
        if pd.iscanceled():
            break
        xbmc.sleep(interval * 1000)
        waited += interval
        token, keep = trakt._poll_token(device)
        if token:
            trakt._save(token)
            pd.close()
            kodi.notify('Trakt authorised')
            xbmc.executebuiltin('Container.Refresh')
            return
        if not keep:
            break
        pd.update(int(waited * 100 / expires), message)
    pd.close()
    kodi.notify('Trakt authorisation cancelled or timed out')


def sign_out():
    if xbmcgui.Dialog().yesno('Trakt', 'Sign out of Trakt?'):
        trakt.sign_out()
        kodi.notify('Signed out of Trakt')


# ---------------------------------------------------------------------------
# Menus & lists
# ---------------------------------------------------------------------------
_MENU = [
    ('Continue Watching', 'trakt_continue', None, 'continue'),
    ('Watchlist', 'trakt_list', 'watchlist', 'watchlist'),
    ('Collection', 'trakt_list', 'collection', 'collection'),
    ('Recommended', 'trakt_list', 'recommended', 'recommended'),
    ('Trending', 'trakt_list', 'trending', 'trending'),
    ('Popular', 'trakt_list', 'popular', 'popular'),
    ('Anticipated', 'trakt_list', 'anticipated', 'anticipated'),
    ('Lists', 'trakt_lists', None, 'lists'),
]

_FEEDS = {
    'watchlist': trakt.watchlist,
    'collection': trakt.collection,
    'recommended': trakt.recommendations,
    'trending': trakt.trending,
    'popular': trakt.popular,
    'anticipated': trakt.anticipated,
}


def menu(media):
    for label, action, kind, icon in _MENU:
        params = {'action': action, 'media': media}
        if kind:
            params['kind'] = kind
        kodi.add_directory(label, params, art=ui.folder_art(icon))
    kodi.end_directory(content='')


def _plural(media):
    return 'movies' if media == 'movie' else 'shows'


def _tmdb_ids(items, media):
    key = 'movie' if media == 'movie' else 'show'
    ids = []
    for it in items:
        if not isinstance(it, dict):
            continue
        obj = it.get(key, it)   # wrapped (watchlist/list) or bare (recommendations)
        tmdb_id = (obj.get('ids') or {}).get('tmdb')
        if tmdb_id and tmdb_id not in ids:
            ids.append(tmdb_id)
    return ids


def _render(media, items):
    ids = _tmdb_ids(items, media)
    if media == 'movie':
        details = tmdb.bulk_movie_details(ids)
        gmap = tmdb.genre_map('movie')
        watched = trakt.watched_movie_ids()
        for tid in ids:
            d = details.get(tid)
            if d:
                ui._movie_row(d, gmap=gmap, details=d, watched=watched)
        kodi.end_directory(content='movies')
    else:
        details = tmdb.bulk_show_details(ids)
        gmap = tmdb.genre_map('tv')
        for tid in ids:
            d = details.get(tid)
            if d:
                ui._show_row(d, gmap=gmap, details=d)
        kodi.end_directory(content='tvshows')


def show_list(kind, media):
    feed = _FEEDS.get(kind, trakt.watchlist)
    _render(media, feed(_plural(media)) or [])


def watched_seeds(media):
    """List recently-watched titles; each opens its TMDB recommendations."""
    hist = trakt.history('movies' if media == 'movie' else 'episodes')
    key = 'movie' if media == 'movie' else 'show'
    ids = []
    for it in hist:
        tid = (it.get(key) or {}).get('ids', {}).get('tmdb')
        if tid and tid not in ids:
            ids.append(tid)
        if len(ids) >= 20:
            break
    if not ids:
        kodi.notify('No Trakt history yet - watch something first')
    details = (tmdb.bulk_movie_details(ids) if media == 'movie'
               else tmdb.bulk_show_details(ids))
    gmap = tmdb.genre_map('movie' if media == 'movie' else 'tv')
    for tid in ids:
        d = details.get(tid)
        if not d:
            continue
        info, art = (tmdb.map_movie(d, gmap=gmap, details=d) if media == 'movie'
                     else tmdb.map_show(d, gmap=gmap, details=d))
        kodi.add_directory('Because you watched {0}'.format(info['title']),
                           {'action': 'recommendations', 'media': media, 'tmdb': tid},
                           info=info, art=art,
                           media_type='movie' if media == 'movie' else 'tvshow')
    kodi.end_directory(content='movies' if media == 'movie' else 'tvshows')


def continue_watching(media):
    """In-progress items from Trakt, with a resume point so playback resumes."""
    if media == 'movie':
        items = sorted(trakt.playback('movies'),
                       key=lambda i: i.get('paused_at', ''), reverse=True)
        ids, prog = [], {}
        for it in items:
            tid = (it.get('movie') or {}).get('ids', {}).get('tmdb')
            if tid and tid not in prog:
                ids.append(tid)
                prog[tid] = it.get('progress', 0)
        details = tmdb.bulk_movie_details(ids)
        gmap = tmdb.genre_map('movie')
        watched = trakt.watched_movie_ids()
        for tid in ids:
            d = details.get(tid)
            if not d:
                continue
            rt = (d.get('runtime') or 0) * 60
            resume = (rt * prog[tid] / 100.0, rt) if rt and prog[tid] else None
            ui._movie_row(d, gmap=gmap, details=d, watched=watched, resume=resume)
        kodi.end_directory(content='movies')
        return

    # episodes
    items = sorted(trakt.playback('episodes'),
                   key=lambda i: i.get('paused_at', ''), reverse=True)
    for it in items[:40]:
        show = it.get('show') or {}
        ep = it.get('episode') or {}
        tid = (show.get('ids') or {}).get('tmdb')
        imdb = (show.get('ids') or {}).get('imdb') or ''
        season = ep.get('season')
        number = ep.get('number')
        progress = it.get('progress', 0)
        if not (tid and season and number):
            continue
        sdetails = tmdb.show_details(tid)
        show_info, show_art = tmdb.map_show(sdetails, details=sdetails)
        season_data = tmdb.season_details(tid, season)
        epobj = next((x for x in season_data.get('episodes', [])
                      if x.get('episode_number') == number), None)
        if not epobj:
            continue
        info, art = tmdb.map_episode(epobj, show_info, show_art)
        rt = (epobj.get('runtime') or (sdetails.get('episode_run_time') or [0])[0] or 0) * 60
        resume = (rt * progress / 100.0, rt) if rt and progress else None
        ui.episode_row(tid, season, number, show_info['title'],
                       show_info.get('year', ''), imdb, info, art, resume=resume)
    kodi.end_directory(content='episodes')


def custom_lists(media):
    lists = trakt.my_lists()
    if not lists:
        kodi.notify('No Trakt lists found')
    for lst in lists:
        ids = lst.get('ids', {})
        list_id = ids.get('trakt') or ids.get('slug')
        if not list_id:
            continue
        kodi.add_directory(lst.get('name') or 'List',
                           {'action': 'trakt_list_items', 'owner': lst['owner'],
                            'list_id': list_id, 'media': media},
                           art=ui.folder_art('lists'))
    kodi.end_directory(content='')


def list_items(owner, list_id, media):
    items = trakt.list_items(owner, list_id, _plural(media))
    _render(media, items or [])


# ---------------------------------------------------------------------------
# Push actions (called via RunPlugin from context menus)
# ---------------------------------------------------------------------------
def do_action(do, media, tmdb_id, season=None, episode=None):
    ok = False
    msg = 'Trakt action failed'
    if media == 'movie':
        if do == 'wl_add':
            ok, msg = trakt.watchlist_movie(tmdb_id, True), 'Added to Trakt watchlist'
        elif do == 'wl_rem':
            ok, msg = trakt.watchlist_movie(tmdb_id, False), 'Removed from Trakt watchlist'
        elif do == 'hist_add':
            ok, msg = trakt.watched_movie(tmdb_id, True), 'Marked watched on Trakt'
        elif do == 'hist_rem':
            ok, msg = trakt.watched_movie(tmdb_id, False), 'Marked unwatched on Trakt'
    else:
        if do == 'hist_add':
            ok, msg = trakt.watched_episode(tmdb_id, season, episode, True), 'Marked watched on Trakt'
        elif do == 'hist_rem':
            ok, msg = trakt.watched_episode(tmdb_id, season, episode, False), 'Marked unwatched on Trakt'
    kodi.notify(msg if ok else 'Trakt action failed')
    xbmc.executebuiltin('Container.Refresh')
