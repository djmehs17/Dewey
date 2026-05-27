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

Most settings can be changed from Dewey's Settings page after the first start. The environment file is mainly useful for initial defaults and Docker deployments.

### Core Paths

| Variable | Default | What it does |
| --- | --- | --- |
| `DEWEY_CONFIG_DIR` | `/config` | Stores Dewey's SQLite database, saved UI settings, and logs. Mount this to persistent storage. |
| `DEWEY_AUDIOBOOKS_DIR` | `/data/audiobooks` | Destination library folder where Dewey publishes finished imports. This should be the folder Audiobookshelf watches, if you use Audiobookshelf. |
| `DEWEY_TORRENTS_DIR` | `/data/torrents` | Torrent root Dewey uses to find completed qBittorrent downloads and create `.dewey-staging`. This must line up with qBittorrent's save paths inside the container. |
| `DEWEY_UNSORTED_FOLDER` | `_unsorted` | Folder under `DEWEY_AUDIOBOOKS_DIR` for imports that need manual metadata review. |

### MyAnonamouse

| Variable | Default | What it does |
| --- | --- | --- |
| `DEWEY_MAM_URL` | `https://www.myanonamouse.net` | Base MyAnonamouse URL. Most users should leave this alone. |
| `DEWEY_MAM_ID` | blank | Your MAM session cookie value. Required for search, torrent downloads, account refresh, and VIP purchase actions. Treat it like a password. |
| `DEWEY_MAM_AUDIOBOOK_CATEGORY` | `13` | Default main category for searches. `13` is Audiobooks. |
| `DEWEY_MAM_SEARCH_LIMIT` | `100` | Maximum number of search results Dewey asks MAM for before local filtering. |
| `DEWEY_MAM_DEFAULT_FORMAT` | blank | Optional default format filter, such as `m4b` or `mp3`. Blank means any format. |
| `DEWEY_MAM_DEFAULT_LANGUAGE` | blank | Optional default language filter, such as `ENG`. Blank means any language. |
| `DEWEY_MAM_DEFAULT_SEARCH_TYPE` | `all` | Default availability filter. Common values include `all`, `active`, `fl`, `VIP`, and `nVIP`. |
| `DEWEY_MAM_BLOCK_VIP_WHEN_INACTIVE` | `true` | Blocks VIP-only imports unless Dewey believes your VIP status is active. |
| `DEWEY_MAM_ACCOUNT_AUTO_REFRESH_ENABLED` | `true` | Refreshes MAM account status automatically on startup and on the configured interval. |
| `DEWEY_MAM_ACCOUNT_REFRESH_INTERVAL_HOURS` | `8` | How often Dewey refreshes MAM account status in the background. |
| `DEWEY_MAM_VIP_STORE_URL` | MAM store URL | Link Dewey opens when you want to view the MAM bonus store manually. |

### qBittorrent

| Variable | Default | What it does |
| --- | --- | --- |
| `DEWEY_QBITTORRENT_URL` | `http://qbittorrent:8080` | qBittorrent Web UI/API URL from Dewey's point of view. In Docker Compose, this is often the service name plus port. |
| `DEWEY_QBITTORRENT_USERNAME` | blank | qBittorrent Web UI username, if auth is enabled. |
| `DEWEY_QBITTORRENT_PASSWORD` | blank | qBittorrent Web UI password, if auth is enabled. Treat it like a secret. |
| `DEWEY_QBITTORRENT_CATEGORY` | `dewey` | Category Dewey assigns to added torrents. A dedicated category keeps Dewey downloads separate. |
| `DEWEY_QBITTORRENT_SAVE_PATH` | `/data/torrents/dewey` | Optional save path for Dewey torrents. This should live under `DEWEY_TORRENTS_DIR` and be visible to both Dewey and qBittorrent. |
| `DEWEY_ENSURE_QBITTORRENT_CATEGORY` | `true` | Creates the qBittorrent category if it does not exist. |
| `DEWEY_MONITOR_INTERVAL_SECONDS` | `30` | How often Dewey checks qBittorrent for download progress. |

### Optional Audiobookshelf Scan

| Variable | Default | What it does |
| --- | --- | --- |
| `DEWEY_AUDIOBOOKSHELF_SCAN_ENABLED` | `false` | Enables scan requests after imports. Dewey can still import files with this disabled. |
| `DEWEY_AUDIOBOOKSHELF_URL` | `http://audiobookshelf:80` | Audiobookshelf URL from Dewey's point of view. |
| `DEWEY_AUDIOBOOKSHELF_API_KEY` | blank | Audiobookshelf API key. Required only if scan requests are enabled. |
| `DEWEY_AUDIOBOOKSHELF_LIBRARY_ID` | blank | Audiobookshelf library ID to scan. Required only if scan requests are enabled. |
| `DEWEY_AUDIOBOOKSHELF_FORCE_SCAN` | `false` | Requests a fuller scan when supported. Leave off unless you know you need it. |

### Optional Dewey Login

| Variable | Default | What it does |
| --- | --- | --- |
| `DEWEY_AUTH_ENABLED` | `false` | Requires users to log in to Dewey. Leave off if Dewey is already protected by a trusted reverse proxy or VPN. |
| `DEWEY_AUTH_USERNAME` | `admin` | Username for Dewey's built-in login. |
| `DEWEY_AUTH_PASSWORD_HASH` | blank | Stored password hash. Prefer setting the password from the UI so Dewey creates this safely. |
| `DEWEY_AUTH_SESSION_SECRET` | blank | Signing secret for login sessions. Dewey can generate one when auth is configured through the UI. |
| `DEWEY_AUTH_COOKIE_NAME` | `dewey_session` | Browser cookie name for Dewey sessions. Most users should leave this alone. |
| `DEWEY_AUTH_COOKIE_SECURE` | `false` | Sends the login cookie only over HTTPS. Turn on for HTTPS deployments; leave off for plain local HTTP testing. |
| `DEWEY_AUTH_SESSION_TTL_HOURS` | `168` | How long a Dewey login session lasts before re-authentication. |

### Advanced Tuning

| Variable | Default | What it does |
| --- | --- | --- |
| `DEWEY_MAM_MIN_RELEVANCE` | `45` | Minimum local match score for search results. Higher values hide more weak matches. |
| `DEWEY_MAM_MIN_SEEDERS` | `0` | Minimum seed count for search results. |
| `DEWEY_MAM_SORT_TYPE` | `default` | MAM sort type. Leave as `default` unless you know the documented sort value you want. |
| `DEWEY_MAM_UPDATE_SEEDBOX_IP` | `false` | Calls MAM's dynamic seedbox IP endpoint before searching. Most users should leave this off. |
| `DEWEY_SEARCH_PROFILES` | built-in defaults | JSON list of search profiles to seed the UI with. Easier to manage from the Profiles page. |
| `DEWEY_AUTHOR_MATCH_THRESHOLD` | `85` | Match score needed to reuse an existing author folder. |
| `DEWEY_METADATA_CONFIDENCE_THRESHOLD` | `74` | Minimum external metadata score before Dewey trusts the match. |
| `DEWEY_FALLBACK_CONFIDENCE_THRESHOLD` | `65` | Minimum parsed metadata confidence before Dewey publishes directly instead of sending to review. |
| `DEWEY_INCLUDE_SERIES_IN_BOOK_FOLDER` | `false` | Includes series text in the book folder name when Dewey can identify it. |
| `DEWEY_OPENLIBRARY_URL` | `https://openlibrary.org` | Metadata lookup base URL. Most users should leave this alone. |
| `DEWEY_OPENLIBRARY_USER_AGENT` | Dewey default | User-Agent sent to OpenLibrary. |
| `DEWEY_METADATA_PROVIDER` | `openlibrary` | Metadata provider name. Currently only OpenLibrary is supported. |
| `DEWEY_LOG_LEVEL` | `INFO` | Logging verbosity. |

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
