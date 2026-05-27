# Dewey Roadmap

Last refreshed: 2026-05-27

## Resume Here

Pick back up from this list when returning to Dewey:

1. Ebook mode and library profiles: make audiobooks and ebooks separate workflows with their own destinations, import rules, and search defaults.

## Active To Do

- Ebook mode and library profiles: separate audiobook and ebook destinations, import rules, and search defaults.

## Completed In Current App

- Diagnostics page: quick checks for qBittorrent, MyAnonamouse auth, paths, permissions, and Audiobookshelf scan settings.
- Metadata improvements: richer matching, narrator/series handling, and clearer review suggestions before publishing.
- App-level authentication for open-source readiness: optional built-in login/session support for deployments without Cloudflare Access or another trusted auth proxy.
- Release packaging: GitHub Container Registry publishing workflow and image-based compose example.

## Parked For Now

- Home stack access model: plan a separate infrastructure pass for Sonarr, Radarr, and qBittorrent so local/LAN access stays direct while external access is gated through Cloudflare Access or an equivalent reverse-proxy policy, with no public origin bypass.
- Expanded VIP purchase controls beyond the current 4-week buy-before-import action.
- Active import controls such as pausing, canceling, or changing a running qBittorrent job from Dewey.
