# -*- coding: utf-8 -*-
"""URL dispatch. Maps the ?action= param to a handler."""
from . import kodi
from . import ui
from . import playback
from . import trakt_ui


def dispatch(argv):
    kodi.set_runtime(argv)
    params = kodi.parse_params(argv[2] if len(argv) > 2 else '')
    action = params.get('action')

    try:
        _route(action, params)
    except Exception as exc:  # noqa: BLE001
        kodi.log_error('Unhandled error in action={0}: {1}'.format(action, exc))
        kodi.notify('Something went wrong - check the log')
        # If Kodi is waiting on a resolved url, release it cleanly.
        if action in ('play_movie', 'play_episode'):
            kodi.resolve_fail()


def _route(action, p):
    if action is None:
        return ui.root()

    if action == 'movies_menu':
        return ui.movies_menu()
    if action == 'shows_menu':
        return ui.shows_menu()
    if action == 'genres':
        return ui.genres(p['media'])

    if action == 'movies_list':
        return ui.movies_list(p['category'], p.get('page', 1))
    if action == 'shows_list':
        return ui.shows_list(p['category'], p.get('page', 1))
    if action == 'discover':
        return ui.discover(p['media'], p['genre'], p.get('page', 1))
    if action == 'recommendations':
        return ui.recommendations(p['media'], p['tmdb'], p.get('page', 1))
    if action == 'named':
        return ui.named_list(p['media'], p['key'], p.get('page', 1))
    if action == 'years':
        return ui.years_menu(p['media'])
    if action == 'year':
        return ui.year_list(p['media'], p['year'], p.get('page', 1))
    if action == 'langs':
        return ui.langs_menu(p['media'])
    if action == 'lang':
        return ui.lang_list(p['media'], p['lang'], p.get('page', 1))
    if action == 'networks':
        return ui.networks_menu()
    if action == 'network':
        return ui.network_list(p['network'], p.get('page', 1))
    if action == 'boxoffice':
        return trakt_ui.boxoffice()
    if action == 'search':
        return ui.search(p['media'], p.get('page', 1), p.get('query'))

    if action == 'seasons':
        return ui.seasons(p['tmdb_id'])
    if action == 'episodes':
        return ui.episodes(p['tmdb_id'], int(p['season']), p['show_title'],
                           p.get('year', ''), p.get('imdb', ''))

    if action == 'play_movie':
        return playback.play_movie(p['tmdb_id'])
    if action == 'play_episode':
        return playback.play_episode(p['tmdb_id'], int(p['season']), int(p['episode']),
                                     p['show_title'], p.get('year', ''), p.get('imdb', ''))

    if action == 'trakt_menu':
        return trakt_ui.menu(p['media'])
    if action == 'trakt_continue':
        return trakt_ui.continue_watching(p['media'])
    if action == 'watched_seeds':
        return trakt_ui.watched_seeds(p['media'])
    if action == 'calendar_menu':
        return trakt_ui.calendar_menu()
    if action == 'calendar':
        return trakt_ui.calendar(p['window'])
    if action == 'trakt_list':
        return trakt_ui.show_list(p['kind'], p['media'])
    if action == 'trakt_lists':
        return trakt_ui.custom_lists(p['media'])
    if action == 'trakt_list_items':
        return trakt_ui.list_items(p['owner'], p['list_id'], p['media'])
    if action == 'trakt_action':
        return trakt_ui.do_action(p['do'], p['media'], p['tmdb'],
                                  p.get('season'), p.get('episode'))
    if action == 'trakt_auth':
        return trakt_ui.authorise()
    if action == 'trakt_signout':
        return trakt_ui.sign_out()

    if action == 'set_view':
        return ui.set_view(p['content'])

    if action == 'tools':
        return ui.tools()
    if action == 'settings':
        kodi.open_settings()
        return kodi.cancel_directory()
    if action == 'clear_cache':
        from . import cache
        kodi.notify('Cache cleared' if cache.clear() else 'Could not clear cache')
        return kodi.cancel_directory()

    kodi.log_error('Unknown action: {0}'.format(action))
