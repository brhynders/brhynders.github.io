# -*- coding: utf-8 -*-
# Astro - entry point. Kodi calls this with sys.argv = [base_url, handle, query].
import sys
from resources.lib import router

if __name__ == '__main__':
    router.dispatch(sys.argv)
