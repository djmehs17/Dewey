# Dewey v0.1.0 — first public release

Dewey is a self-hosted web app for finding audiobooks and ebooks on MyAnonamouse and filing them away neatly — one click per book, nothing automated. You search, pick a result, and Dewey downloads the torrent through qBittorrent and files the finished book into your library.

This is the first public, versioned release. Dewey is shared as a **reference implementation** under the MIT license: it works and is used in production, but it is **not actively maintained**. Issues and pull requests are welcome but may go unanswered, and **forking is encouraged**.

## Highlights

- **Audiobook import pipeline** — search MyAnonamouse, send the torrent to qBittorrent, wait for completion, and publish into an Audiobookshelf-style `Author/Book Title/` layout. Hardlinks first (so torrents keep seeding), copy as a fallback.
- **Dedicated Ebooks tab** — same search/download machinery, but ebooks are copied into a configurable Ebooks folder (`subfolder` or `flat` layout) for a local tool like Calibre to organize. No metadata guessing, no review gating.
- **Metadata + review** — OpenLibrary lookup with confidence thresholds; weak matches are staged under `_unsorted` for a quick manual author/title fix.
- **Duplicate detection** — results are flagged when they look like something already in your library.
- **Reliable torrent matching** — Dewey identifies the download by its BitTorrent infohash, not by fuzzy name matching, so it never grabs the wrong finished torrent.
- **Diagnostics page** — one-click checks for qBittorrent, MyAnonamouse, folder permissions, and the database.
- **Optional Audiobookshelf rescan** after an import.
- **Optional built-in login** — PBKDF2-hashed passwords and signed sessions, for deployments not already behind a VPN or trusted proxy.
- **`/healthz` endpoint** for uptime monitoring.

## Install

```bash
docker compose -f docker-compose.example.yml up -d
```

The image is published to GitHub Container Registry:

```text
ghcr.io/djmehs17/dewey:v0.1.0     # this release (recommended to pin)
ghcr.io/djmehs17/dewey:latest     # newest build
```

See the [README](../README.md) for first-time setup, path mapping, and troubleshooting.

## Security note

Dewey is a download/import control surface — anyone who can open its web page can use it. Keep it on a trusted network (LAN/VPN) or behind Dewey's built-in login, Cloudflare Access, or another trusted reverse-proxy auth layer. Never expose it directly to the public internet without authentication. See [SECURITY.md](../SECURITY.md).
