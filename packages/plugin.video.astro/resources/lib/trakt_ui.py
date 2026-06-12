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
def menu(media):
    kodi.add_directory('Watchlist',
                       {'action': 'trakt_list', 'kind': 'watchlist', 'media': media},
                       art=ui.folder_art('watchlist'))
    kodi.add_directory('Collection',
                       {'action': 'trakt_list', 'kind': 'collection', 'media': media},
                       art=ui.folder_art('collection'))
    kodi.add_directory('Recommended',
                       {'action': 'trakt_list', 'kind': 'recommended', 'media': media},
                       art=ui.folder_art('recommended'))
    kodi.add_directory('Lists', {'action': 'trakt_lists', 'media': media},
                       art=ui.folder_art('lists'))
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
    plural = _plural(media)
    if kind == 'watchlist':
        items = trakt.watchlist(plural)
    elif kind == 'collection':
        items = trakt.collection(plural)
    else:
        items = trakt.recommendations(plural)
    _render(media, items or [])


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
