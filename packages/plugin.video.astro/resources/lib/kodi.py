# -*- coding: utf-8 -*-
"""Thin convenience layer over the Kodi Python API.

Everything UI/settings/logging related funnels through here so the rest of the
addon stays readable and we only touch xbmc* modules in one place.
"""
import sys
from urllib.parse import urlencode, parse_qsl

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
ADDON_PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
ADDON_ICON = ADDON.getAddonInfo('icon')
ADDON_FANART = ADDON.getAddonInfo('fanart')

# Populated by router.dispatch() at startup.
BASE_URL = sys.argv[0] if len(sys.argv) > 0 else 'plugin://plugin.video.astro/'
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip('-').isdigit() else -1


def set_runtime(argv):
    """Refresh BASE_URL / HANDLE from the live argv (called by the router)."""
    global BASE_URL, HANDLE
    BASE_URL = argv[0]
    HANDLE = int(argv[1])


# ---------------------------------------------------------------------------
# URLs / params
# ---------------------------------------------------------------------------
def build_url(**params):
    """Build a plugin:// url for a callback into this addon."""
    clean = {k: v for k, v in params.items() if v is not None}
    return '{0}?{1}'.format(BASE_URL, urlencode(clean))


def parse_params(query):
    """Parse the ?a=b&c=d query string Kodi hands us into a dict."""
    return dict(parse_qsl(query.lstrip('?')))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def get_setting(key, default=''):
    val = ADDON.getSetting(key)
    return val if val != '' else default


def get_bool(key, default=False):
    val = ADDON.getSetting(key)
    if val == '':
        return default
    return val.lower() == 'true'


def get_int(key, default=0):
    val = ADDON.getSetting(key)
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def set_setting(key, value):
    ADDON.setSetting(key, str(value))


def open_settings():
    # Use the builtin so the modal opens on the GUI thread - calling
    # ADDON.openSettings() from inside a directory fetch fails silently.
    xbmc.executebuiltin('Addon.OpenSettings({0})'.format(ADDON_ID))


def cancel_directory():
    """End a directory request without navigating (used by action=settings)."""
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


# ---------------------------------------------------------------------------
# Logging / dialogs
# ---------------------------------------------------------------------------
def log(msg, level=xbmc.LOGINFO):
    xbmc.log('[{0}] {1}'.format(ADDON_ID, msg), level)


def log_error(msg):
    log(msg, xbmc.LOGERROR)


def notify(message, heading=ADDON_NAME, icon=None, time=4000):
    xbmcgui.Dialog().notification(heading, message, icon or ADDON_ICON, time)


def ok(message, heading=ADDON_NAME):
    xbmcgui.Dialog().ok(heading, message)


def select(heading, options):
    """Native selection dialog. Returns chosen index or -1 if cancelled."""
    return xbmcgui.Dialog().select(heading, options)


def keyboard(heading, default=''):
    """Native text entry. Returns the typed string or '' if cancelled."""
    kb = xbmc.Keyboard(default, heading)
    kb.doModal()
    if kb.isConfirmed():
        return kb.getText()
    return ''


class Progress(object):
    """Context-manager wrapper around the background progress dialog."""
    def __init__(self, heading=ADDON_NAME):
        self.dialog = xbmcgui.DialogProgressBG()
        self.heading = heading

    def __enter__(self):
        self.dialog.create(self.heading)
        return self

    def update(self, percent, message=''):
        self.dialog.update(int(percent), self.heading, message)

    def __exit__(self, *args):
        self.dialog.close()


# ---------------------------------------------------------------------------
# Directory / list item building
# ---------------------------------------------------------------------------
def _apply_info(li, info, media_type):
    """Set video metadata using the Omega InfoTagVideo API (setInfo is deprecated)."""
    tag = li.getVideoInfoTag()
    tag.setMediaType(media_type)
    if info.get('title'):
        tag.setTitle(info['title'])
    if info.get('plot'):
        tag.setPlot(info['plot'])
    if info.get('year'):
        try:
            tag.setYear(int(info['year']))
        except (ValueError, TypeError):
            pass
    if info.get('rating'):
        try:
            tag.setRating(float(info['rating']))
        except (ValueError, TypeError):
            pass
    if info.get('premiered'):
        tag.setPremiered(info['premiered'])
    if info.get('genres'):
        tag.setGenres(info['genres'])
    if info.get('duration'):
        try:
            tag.setDuration(int(info['duration']))
        except (ValueError, TypeError):
            pass
    if info.get('mpaa'):
        tag.setMpaa(info['mpaa'])
    if info.get('tagline'):
        tag.setTagLine(info['tagline'])
    if info.get('imdb'):
        tag.setUniqueID(info['imdb'], 'imdb')
    if info.get('tmdb'):
        tag.setUniqueID(str(info['tmdb']), 'tmdb')
    if info.get('season') is not None:
        try:
            tag.setSeason(int(info['season']))
        except (ValueError, TypeError):
            pass
    if info.get('episode') is not None:
        try:
            tag.setEpisode(int(info['episode']))
        except (ValueError, TypeError):
            pass
    if info.get('tvshowtitle'):
        tag.setTvShowTitle(info['tvshowtitle'])
    if info.get('playcount'):
        try:
            tag.setPlaycount(int(info['playcount']))
        except (ValueError, TypeError):
            pass
    if info.get('studio'):
        tag.setStudios(info['studio'])
    if info.get('director'):
        tag.setDirectors(info['director'])
    if info.get('trailer'):
        tag.setTrailer(info['trailer'])
    if info.get('cast'):
        actors = [xbmc.Actor(c.get('name', ''), c.get('role', ''),
                             c.get('order', 0), c.get('thumbnail', ''))
                  for c in info['cast']]
        tag.setCast(actors)


def make_listitem(label, info=None, art=None, media_type='video', playable=False):
    li = xbmcgui.ListItem(label=label)
    if art:
        li.setArt(art)
    if info:
        _apply_info(li, info, media_type)
    if playable:
        li.setProperty('IsPlayable', 'true')
    return li


def add_directory(label, params, info=None, art=None, media_type='video', context_menu=None):
    """Add a folder row that calls back into the addon."""
    li = make_listitem(label, info=info, art=art, media_type=media_type)
    if context_menu:
        li.addContextMenuItems(context_menu)
    url = build_url(**params)
    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)


def add_playable(label, params, info=None, art=None, media_type='movie', context_menu=None):
    """Add a row that, when clicked, resolves to a stream."""
    li = make_listitem(label, info=info, art=art, media_type=media_type, playable=True)
    if context_menu:
        li.addContextMenuItems(context_menu)
    url = build_url(**params)
    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)


def end_directory(content='videos', sort_methods=None, cache=True):
    if content:
        xbmcplugin.setContent(HANDLE, content)
    for method in (sort_methods or [xbmcplugin.SORT_METHOD_NONE]):
        xbmcplugin.addSortMethod(HANDLE, method)
    xbmcplugin.endOfDirectory(HANDLE, cacheToDisc=cache)


def resolve(url, listitem):
    xbmcplugin.setResolvedUrl(HANDLE, True, listitem)


def resolve_fail():
    li = xbmcgui.ListItem()
    xbmcplugin.setResolvedUrl(HANDLE, False, li)
