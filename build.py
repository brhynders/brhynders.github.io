#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the Astro Kodi repository for GitHub Pages.

Two roles:
  * The *served* add-on(s) - distributed and auto-updated through the repo.
    Source + versioned zips live in packages/<id>/, listed in packages/addons.xml.
  * The *repository* add-on - the one-time installer. It only carries a static
    datadir URL and never changes, so we keep just the prebuilt (unversioned)
    repository.astro.zip at the project root (no source) and a static index.html
    that links to it. Neither is touched by this script. The repo add-on is
    intentionally NOT in addons.xml. (Kodi installs it by the addon.xml inside
    the zip, so its filename needs no version.)

Usage:
    python3 build.py              # build + install plugin into local Kodi (dev)
    python3 build.py --no-install # build only
"""
import hashlib
import os
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PKGS = os.path.join(ROOT, 'packages')

REPO_BASE = 'https://brhynders.github.io'      # GitHub Pages root
DATADIR = '{0}/packages'.format(REPO_BASE)

SERVED = ['plugin.video.astro']                # auto-updated through the repo

# Local dev install target (WSL path to Windows Kodi).
WIN_KODI = '/mnt/c/Users/brand/AppData/Roaming/Kodi'
WIN_ADDONS = os.path.join(WIN_KODI, 'addons')

EXCLUDE = {'__pycache__', '.git', '.DS_Store', '.pytest_cache'}


def version_of(src_dir):
    return ET.parse(os.path.join(src_dir, 'addon.xml')).getroot().get('version')


def _keep(rel):
    parts = set(rel.split(os.sep))
    return not (parts & EXCLUDE) and not rel.endswith(('.pyc', '.pyo', '.zip'))


def zip_addon(src_dir, arc_base, out_dir):
    """Zip src_dir into out_dir/<id>-<version>.zip with <id>/... as top folder."""
    addon_id = os.path.basename(src_dir)
    version = version_of(src_dir)
    zip_path = os.path.join(out_dir, '{0}-{1}.zip'.format(addon_id, version))
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for folder, _dirs, files in os.walk(src_dir):
            for fn in files:
                full = os.path.join(folder, fn)
                rel = os.path.relpath(full, arc_base)
                if _keep(rel):
                    zf.write(full, rel)
    print('  zipped {0} v{1}'.format(addon_id, version))
    return os.path.basename(zip_path)


def build_addons_xml():
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '<addons>']
    for addon_id in SERVED:
        with open(os.path.join(PKGS, addon_id, 'addon.xml'), 'r', encoding='utf-8') as f:
            lines = [ln for ln in f.read().splitlines() if not ln.strip().startswith('<?xml')]
        parts.append('\n'.join('    ' + ln if ln.strip() else ln for ln in lines).rstrip())
    parts.append('</addons>\n')
    xml = '\n'.join(parts)

    xml_path = os.path.join(PKGS, 'addons.xml')
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(xml)
    md5 = hashlib.md5(xml.encode('utf-8')).hexdigest()
    with open(xml_path + '.md5', 'w', encoding='utf-8') as f:
        f.write(md5)
    print('  wrote addons.xml (+md5 {0})'.format(md5[:8]))


def install_plugin():
    if not os.path.isdir(WIN_ADDONS):
        print('  ! Windows Kodi not found at {0}; skipping install'.format(WIN_ADDONS))
        return
    src = os.path.join(PKGS, 'plugin.video.astro')
    dst = os.path.join(WIN_ADDONS, 'plugin.video.astro')
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*EXCLUDE, '*.pyc', '*.zip'))
    print('  installed plugin.video.astro -> Kodi (restart Kodi to apply)')


def main():
    args = set(sys.argv[1:])
    print('Building Astro repository...')
    for addon_id in SERVED:
        zip_addon(os.path.join(PKGS, addon_id), PKGS, os.path.join(PKGS, addon_id))
    build_addons_xml()
    if '--no-install' not in args:
        install_plugin()
    print('Done. Serve the repo root at {0}'.format(REPO_BASE))


if __name__ == '__main__':
    main()
