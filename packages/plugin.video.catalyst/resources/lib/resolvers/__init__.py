# -*- coding: utf-8 -*-
"""Debrid resolvers. Torbox is the only one wired up, but the interface
(resolve(source) -> playable url or None) is deliberately generic so another
debrid service can be dropped in alongside it later.
"""
from . import torbox  # noqa: F401
