# grok-web

Browser UI for Grok Bot cloud agents. A FastAPI BFF imports [`grokbot`](https://git.stackken.com/kenzim/grokbot-client) and a Vite SPA talks only to the BFF. Cursor tokens stay on the host (`grokbot.auth.auto()` / `HostFiles`). The browser never sees them.

## Run

Needs a Cursor login on the machine (`~/.config/cursor/auth.json`) or `GROKBOT_TOKEN`.

```bash
python3 -m venv .venv
.venv/bin/pip install -e /path/to/grokbot-client
.venv/bin/pip install -e ".[dev]"
cd frontend && npm ci && cd ..
./dev.sh
```

- SPA: http://127.0.0.1:5180 (proxies `/api` and `/ws`)
- BFF: http://127.0.0.1:8787

## Tests

Automated tests must not send to live agents.

```bash
.venv/bin/pytest
cd frontend && npm test
```

## Docker

```bash
docker build -t grok-web .
# override the grokbot-client git URL if needed:
docker build --build-arg GROKBOT_CLIENT_GIT=https://git.stackken.com/kenzim/grokbot-client.git -t grok-web .
docker run --rm -p 8787:8787 -v ~/.config/cursor:/root/.config/cursor:ro grok-web
```

The image serves the built SPA from FastAPI on port 8787.

## CI

Forgejo Actions:

- `ci` — ruff, pytest, tsc, vitest
- `SonarQube` — coverage, sonar-scanner, quality gate
- `OWASP` — Dependency-Check JSON (not imported into Sonar)
- `Container Build` — image to the Forgejo package registry

Repo secrets: `SONAR_HOST_URL`, `SONAR_TOKEN`, and for image push `REGISTRY_USER` + `REGISTRY_TOKEN` (or `PACKAGE_WRITABLE_TOKEN`).
