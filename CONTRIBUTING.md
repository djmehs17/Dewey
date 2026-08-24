# Contributing

Thanks for your interest in Dewey.

Dewey is shared as a **reference implementation**, released to the community under the MIT license. It works and is used in production by its author, but it is **not actively maintained**. Treat it as a solid starting point rather than a supported product.

## Maintenance status

- Issues and pull requests are welcome, but responses may be slow or may not come at all.
- There is no roadmap commitment and no release cadence. See [ROADMAP.md](ROADMAP.md) for ideas, not promises.
- If Dewey is useful to you, **forking is encouraged.** A fork that becomes the living, maintained version is a good outcome, and you are welcome to say so and point people to it.

## If you want to contribute upstream

- Small, focused pull requests are easiest to review if a review happens.
- Bug reports are most useful with clear reproduction steps and your environment (Docker/compose shape, path mapping, qBittorrent version).
- Documentation corrections are always welcome.

## Please be careful with

These are guidelines, not gatekeeping — they exist because Dewey touches a private tracker, credentials, and your filesystem:

- **Never** include credentials, `mam_id`/cookies, API keys, or private tracker details in issues, logs, screenshots, or test data.
- Changes to tracker behavior, purchase flows, authentication, or import/filesystem safety deserve a clear description of intent and impact.
- Keep Dewey's posture toward MyAnonamouse conservative: documented endpoints, manual and personal use, nothing that automates actions a tracker does not allow.

## Security

Report suspected vulnerabilities privately through GitHub's private vulnerability reporting rather than a public issue. See [SECURITY.md](SECURITY.md).
