# Dewey

Dewey is a self-hosted audiobook search and import helper for people who already run an audiobook stack. It uses documented MyAnonamouse endpoints to search, downloads the selected private torrent through Dewey, sends it to qBittorrent, waits for completion, and imports audio files into an Audiobookshelf-style library folder.

Dewey is intentionally manual. It is not an unattended downloader, ratio-management system, or automatic purchasing tool.

## What Dewey Does

- Searches MyAnonamouse directly using documented endpoints.
- Shows audiobook-focused result metadata such as author, narrator, series, language, size, file type, tags, and listing links.
- Downloads the selected `.torrent` through Dewey and sends it to qBittorrent.
- Watches qBittorrent until the download completes.
- Imports audio files into an `Author/Book Title/` folder layout.
- Tries hardlinks first so torrents can keep seeding, then falls back to copying when hardlinks are not possible.
- Stages imports before publishing them to the audiobook library.
- Flags weak metadata for manual review.
- Can optionally request an Audiobookshelf library scan after import.
- Can optionally require Dewey's own app login.

## What You Need

Dewey is not a complete media stack by itself. Before installing Dewey, you should already have:

- Docker and Docker Compose.
- qBittorrent reachable from Dewey.
- A MyAnonamouse account and a `mam_id` session value that is allowed to use the documented JSON endpoints.
- An audiobook library folder that Dewey can write to.
- Optional: Audiobookshelf, if you want Dewey to request library scans after imports.

You also need to understand where your downloads and library live on disk. The most common setup problem is path mapping: Dewey and qBittorrent must agree on the same container paths.

## Responsible Use

Dewey is not affiliated with MyAnonamouse. It is intended for personal, manual library importing by users who already have appropriate tracker access.

Use Dewey only in ways allowed by the trackers, services, and communities you connect it to. Dewey should not be used to bypass tracker rules, automate actions that a tracker disallows, scrape undocumented surfaces, share credentials, or perform unattended purchases. If a tracker policy changes, follow the tracker policy first.

VIP-only results can offer a confirmed 4-week VIP purchase before import, but Dewey does not auto-buy VIP, wedges, upload credit, or any other MyAnonamouse bonus store item.

## Quick Start

Clone the repository, copy the example environment file, and start Dewey:

```bash
cp .env.example .env
docker compose -f docker-compose.example.yml up -d --build
```

Open Dewey:

```text
http://localhost:8686
```

The example compose file builds Dewey locally. Published container images are planned for a future release, but the example will not reference an image until one exists.

## First-Time Setup

After Dewey starts, open Settings and fill in the core services.

1. Add your MyAnonamouse `mam_id`.
   Treat this like a password. Dewey hides saved secret values in the UI.

2. Add qBittorrent connection details.
   Set the URL, username, password, category, and save path. A dedicated category such as `dewey` is recommended.

3. Set your library paths.
   `Audiobooks path` is where finished imports should land. `Torrents path` is the root Dewey uses to find completed qBittorrent downloads and create staging folders.

4. Save settings.

5. Open Diagnostics.
   Run checks before your first import. Diagnostics will report whether Dewey can reach qBittorrent and MyAnonamouse, open the database, and write to the configured paths.

6. Search for an audiobook.
   Pick a result, review the metadata, and click Import.

## Path Mapping

Path mapping matters more than almost anything else.

Dewey imports from files that qBittorrent downloaded. That means Dewey must be able to see qBittorrent's completed download path using the same container-side paths.

Recommended shape:

```text
/data
  /audiobooks
  /torrents
    /dewey
```

Then configure:

```text
DEWEY_AUDIOBOOKS_DIR=/data/audiobooks
DEWEY_TORRENTS_DIR=/data/torrents
DEWEY_QBITTORRENT_CATEGORY=dewey
DEWEY_QBITTORRENT_SAVE_PATH=/data/torrents/dewey
```

For hardlinks to work, the torrent download path and audiobook library path must be on the same filesystem inside the container. If they are not, Dewey will copy files instead.

## qBittorrent Setup

Dewey can create the configured qBittorrent category when `Create category when missing` is enabled.

The recommended category is:

```text
dewey
```

The recommended save path is:

```text
/data/torrents/dewey
```

Using a dedicated category keeps Dewey imports separate from other qBittorrent activity and makes cleanup easier.

## MyAnonamouse Setup

Dewey uses the `mam_id` session value to call documented MyAnonamouse JSON endpoints.

The relevant settings are:

- `mam_id`: required for search, torrent download, account refresh, and VIP purchase actions.
- `Default MAM category`: Audiobooks by default.
- `Default availability`: Any, active, freeleech, VIP-only, or non-VIP.
- `Refresh MyAnonamouse account status automatically`: refreshes VIP/account status on startup and then on the configured interval.

Dewey can detect VIP-only results and block imports unless your VIP status is active. If you choose to buy VIP from Dewey, the action requires explicit confirmation.

## Optional Audiobookshelf Scan

Dewey does file-level imports without needing Audiobookshelf.

Audiobookshelf integration is optional. If enabled, Dewey asks Audiobookshelf to scan the configured library after an import. You need:

- Audiobookshelf URL.
- Audiobookshelf API key.
- Audiobookshelf library ID.

Leave scan integration disabled if Audiobookshelf already picks up filesystem changes reliably in your setup.

## Optional App Login

Dewey includes optional app-level authentication for deployments that are not already protected by a trusted reverse proxy, VPN, Cloudflare Access, or similar access layer.

The simplest setup is:

1. Start Dewey on a private network.
2. Open Settings.
3. Set a Dewey login username and password.
4. Enable `Require Dewey login`.
5. Save settings.

Dewey stores a password hash, not the plaintext password. If Dewey is served over HTTPS, enable `Secure cookie only` so browsers send the session cookie only over HTTPS. Leave that option off for plain `http://localhost` testing.

## Configuration Reference

Configuration is loaded from environment variables first, then `/config/settings.json` if you save changes in the UI.

Important values:

- `DEWEY_MAM_URL`, `DEWEY_MAM_ID`, `DEWEY_MAM_AUDIOBOOK_CATEGORY`, and `DEWEY_MAM_SEARCH_LIMIT`
- `DEWEY_MAM_MIN_RELEVANCE`, `DEWEY_MAM_MIN_SEEDERS`, `DEWEY_MAM_DEFAULT_FORMAT`, and `DEWEY_MAM_DEFAULT_LANGUAGE`
- `DEWEY_MAM_DEFAULT_SEARCH_TYPE` for availability filters such as active, freeleech, VIP, or non-VIP
- `DEWEY_SEARCH_PROFILES` as JSON if you want to seed configurable Search page profiles from the environment
- `DEWEY_MAM_VIP_STATUS`, `DEWEY_MAM_BLOCK_VIP_WHEN_INACTIVE`, and `DEWEY_MAM_VIP_STORE_URL`
- `DEWEY_MAM_ACCOUNT_AUTO_REFRESH_ENABLED` and `DEWEY_MAM_ACCOUNT_REFRESH_INTERVAL_HOURS`
- `DEWEY_QBITTORRENT_URL`, username, password, category, and optional save path
- `DEWEY_AUDIOBOOKS_DIR` and `DEWEY_TORRENTS_DIR`
- optional `DEWEY_AUDIOBOOKSHELF_SCAN_ENABLED`, URL, API key, and library ID
- optional `DEWEY_AUTH_ENABLED`, `DEWEY_AUTH_USERNAME`, `DEWEY_AUTH_COOKIE_SECURE`, and `DEWEY_AUTH_SESSION_TTL_HOURS`
- `DEWEY_AUTHOR_MATCH_THRESHOLD`, `DEWEY_METADATA_CONFIDENCE_THRESHOLD`, and `DEWEY_FALLBACK_CONFIDENCE_THRESHOLD`

MyAnonamouse audiobook search defaults to main category `13`.
The UI shows the documented main categories by name: Audiobooks, E-books, Musicology, and Radio.

Do not commit `.env`, `/config`, SQLite databases, logs, `mam_id`, qBittorrent credentials, or Audiobookshelf API keys.

## Import Behavior

1. Search calls MyAnonamouse `tor/js/loadSearchJSONbasic.php` using the configured `mam_id` cookie.
2. Import downloads the selected `.torrent` through Dewey and uploads the torrent bytes to qBittorrent with the configured category.
3. Dewey polls qBittorrent until the torrent is complete.
4. Audio files are copied or hardlinked into `/data/torrents/.dewey-staging` first.
5. OpenLibrary is queried for canonical title and author when enabled.
6. If metadata is weak, Dewey parses torrent names such as `Author - Series 01 - Book Title`.
7. If author/title confidence is still low, files are published under `_unsorted` and the job is marked for review.
8. Author folders are matched with `rapidfuzz`; high-confidence matches reuse existing folders.
9. Staged files are atomically published into `Author/Book Title/`.
10. Audiobookshelf scanning is skipped unless the optional scan integration is enabled and configured.

## Local Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8686
```

Run tests:

```bash
python -m unittest discover -s tests
```

With Docker Compose:

```bash
docker compose -f docker-compose.example.yml run --rm --no-deps --entrypoint python dewey -B -m unittest discover -s tests
```

## Project Status

Dewey is early, personal, and security-sensitive. The source is public, but the project is not currently open to general code contributions. See [CONTRIBUTING.md](CONTRIBUTING.md).

Future work is tracked in [ROADMAP.md](ROADMAP.md).

## Future Releases

A future release should publish official Dewey images to GitHub Container Registry so deployments can use an image reference such as `ghcr.io/<owner>/dewey:latest` instead of building locally. Until those images are published, prefer the local-build compose example.

## Security

Dewey is a download/import control surface. Keep it LAN-only unless it is protected by real authentication such as Dewey's built-in login, Cloudflare Access, or another trusted reverse-proxy auth layer. See [SECURITY.md](SECURITY.md) for reporting and deployment guidance.
