# Astro

A lightweight movie & TV streaming add-on for **Kodi 21 "Omega"**, served from
its own repository on GitHub Pages.

- TMDB-powered **Movies** and **TV Shows** (Trending, Popular, Top Rated, Now
  Playing / Airing, Genres, Search) with full metadata (cast, runtime, studio,
  trailer) and watched overlays.
- Pluggable **scraper base** — drop a file into
  `packages/plugin.video.astro/resources/lib/scrapers/` to add a source.
- **Torbox** debrid resolver and two-way **Trakt** sync (lists, watchlist,
  scrobble, watched status).
- Native Kodi GUI only — no custom windows.

## Install in Kodi

1. **Settings → System → Add-ons** → enable **Unknown sources**.
2. **Settings → File manager → Add source** → enter:
   ```
   https://brhynders.github.io/
   ```
   Name it `astro` and save.
3. **Settings → Add-ons → Install from zip file** → `astro` →
   `repository.astro.zip`.
4. **Install from repository → Astro Repository → Video add-ons → Astro**.

Or just open <https://brhynders.github.io/> and download the repository zip.

Then open **Astro → Tools → Settings → Services** to add your Torbox key and
authorise Trakt.

## Repository layout

```
.
├── index.html                  static link to the installer zip
├── repository.astro.zip        the one-time installer (static, unversioned)
├── build.py
└── packages/                   <- GitHub Pages datadir (the served repo)
    ├── addons.xml  /  addons.xml.md5   (lists plugin.video.astro only)
    └── plugin.video.astro/     source + plugin.video.astro-x.y.z.zip
```

Install `repository.astro.zip` once; it points Kodi at `packages/` so
`plugin.video.astro` auto-updates. The repository add-on is a static, unversioned
zip with no source kept — it only holds the datadir URL
`https://brhynders.github.io/packages/` and never changes. (Kodi installs it by
the `addon.xml` *inside* the zip, so the filename needs no version. To change the
URL: edit `addon.xml` inside the zip, or ask Claude to regenerate it.)

## Building

```bash
python3 build.py              # build everything + install plugin into local Kodi (dev)
python3 build.py --no-install # build only
```

`build.py` zips `plugin.video.astro` into `packages/` (excluding
`*.zip`/`__pycache__`) and regenerates `packages/addons.xml`(+`.md5`). Commit the
generated zip and `addons.xml*` — GitHub Pages serves them as the live
repository. `index.html` and the repository zip are static and left untouched.

## Publishing

This repo is the GitHub **user site** `brhynders/brhynders.github.io`, served at
`https://brhynders.github.io/`. Push to `main`; Pages serves the root. After a
version bump, run `build.py`, commit, and push — Kodi picks up the update.

## Adding a source

Drop a file in `…/resources/lib/scrapers/`; it's auto-discovered and gets a
`scraper_<name>` settings toggle. Three bases (see `scrapers/base.py`):

- **`ApiScraper`** (JSON) — config only. Declare URL templates, a dotted
  `results_path` to the list, and a `fields` map. Example (`apibay.py`):
  ```python
  class Apibay(ApiScraper):
      name = 'apibay'
      movie_url = 'https://apibay.org/q.php?q={query}&cat=200'
      episode_url = 'https://apibay.org/q.php?q={title_url}+{se}&cat=200'
      fields = {'release_title': 'name', 'hash': 'info_hash',
                'size': 'size', 'seeders': 'seeders'}
      size_unit = 'bytes'
  ```
- **`HtmlScraper`** (HTML) — declare a `row_selector` and per-field
  `{css, attr}` selectors (`html_example.py`). Needs
  `script.module.beautifulsoup4`.
- **`ScraperBase`** — full control: implement `scrape_movie` / `scrape_episode`.

URL template vars: `{title} {title_url} {year} {query} {imdb} {imdb_num} {tmdb}
{season} {episode} {season2} {episode2} {se}`. Return source dicts with a
`magnet` (or `hash`, or `url`); size/seeders are parsed from the release name if
not supplied, and duplicate releases are de-duped by info-hash across sources.
