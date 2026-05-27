# Contributing

Thanks for your interest in Dewey.

Dewey is public source, but it is not currently open to general code contributions. The project is still early, security-sensitive, and closely tied to cautious tracker integration choices.

## What Is Welcome

- Bug reports with clear reproduction steps.
- Documentation corrections.
- Feature ideas or workflow feedback.
- Private security reports through GitHub private vulnerability reporting.

## What May Be Declined

- Pull requests that change tracker behavior, purchase flows, authentication, import safety, or filesystem behavior without prior discussion.
- Changes that automate actions a tracker does not explicitly allow.
- Logs, screenshots, or test data containing credentials, cookies, private tracker details, or personally identifying deployment information.

## Local Checks

Before proposing a change, run:

```bash
python -m unittest discover -s tests
```

With Docker Compose:

```bash
docker compose -f docker-compose.example.yml run --rm --no-deps --entrypoint python dewey -B -m unittest discover -s tests
```
