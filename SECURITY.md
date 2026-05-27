# Security Policy

## Supported Versions

Dewey is pre-release software. Until versioned releases are published, only the latest `main` branch is considered supported for security fixes.

## Reporting A Vulnerability

Please report security issues through GitHub private vulnerability reporting for this repository. Do not open a public issue for suspected vulnerabilities.

When reporting, include:

- A short description of the issue.
- Steps to reproduce, if safe to share.
- Affected version, commit, or Docker image tag.
- Any relevant deployment details, such as whether Dewey is behind a reverse proxy or exposed directly.

## Deployment Guidance

Dewey controls searches, torrent downloads, qBittorrent imports, filesystem writes, and optional library scan requests. Treat it as a privileged internal service.

Do not expose Dewey directly to the public internet without authentication. Recommended options include:

- A trusted identity-aware reverse proxy such as Cloudflare Access.
- A VPN or private network.
- Dewey's built-in login for single-user or small personal deployments.

If Dewey is reachable over HTTPS, enable `Secure cookie only` for built-in auth so browsers send Dewey's session cookie only over HTTPS. For local plain-HTTP testing, leave that option disabled.

Keep connected services such as qBittorrent, Audiobookshelf, reverse proxies, and the host operating system updated. Avoid exposing qBittorrent or other administrative media-management tools directly to the public internet.

## Secrets

Never publish or commit:

- MyAnonamouse `mam_id` cookies.
- qBittorrent credentials.
- Audiobookshelf API keys.
- Dewey `/config` contents.
- SQLite databases or logs.
- Reverse-proxy credentials or tunnel configuration.

The example configuration files intentionally leave secrets blank.
