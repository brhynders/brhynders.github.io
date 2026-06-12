# -*- coding: utf-8 -*-
"""Background service: scrobbles Astro playback to Trakt.

When playback.py resolves a stream it stashes the TMDB ids on the home window
property 'astro.now_playing'. We consume that on start, track progress, and
send Trakt scrobble start/stop (Trakt auto-marks watched at >=80%).
"""
import json

import xbmc
import xbmcgui

from resources.lib import trakt
from resources.lib import kodi

PROP = 'astro.now_playing'


class AstroPlayer(xbmc.Player):
    def __init__(self):
        super().__init__()
        self.payload = None
        self.percent = 0.0

    def onAVStarted(self):
        # one-shot consume so unrelated playback can't reuse a stale payload
        win = xbmcgui.Window(10000)
        raw = win.getProperty(PROP)
        win.clearProperty(PROP)
        self.payload = None
        self.percent = 0.0
        if not raw:
            return
        try:
            self.payload = json.loads(raw)
        except ValueError:
            return
        if self.payload and trakt.is_authorised():
            trakt.scrobble('start', self.payload, 0)
            kodi.log('Trakt scrobble start: {0}'.format(self.payload))

    def onPlayBackStopped(self):
        self._finish()

    def onPlayBackEnded(self):
        self.percent = 100.0
        self._finish()

    def _finish(self):
        if self.payload and trakt.is_authorised():
            trakt.scrobble('stop', self.payload, self.percent)
            kodi.log('Trakt scrobble stop @ {0:.0f}%'.format(self.percent))
        self.payload = None

    def track(self):
        try:
            if self.isPlayingVideo():
                total = self.getTotalTime()
                if total > 0:
                    self.percent = min(100.0, self.getTime() / total * 100.0)
        except Exception:  # noqa: BLE001 - player can vanish mid-call
            pass


def main():
    monitor = xbmc.Monitor()
    player = AstroPlayer()
    kodi.log('Astro service started')
    while not monitor.abortRequested():
        if player.payload:
            player.track()
        if monitor.waitForAbort(5):
            break


if __name__ == '__main__':
    main()
