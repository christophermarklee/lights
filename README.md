# lights

Circadian-aware BLE LED controller for ELK-BLEDOM and MELK-OA21 strips.

A FastAPI backend connects over Bluetooth Low Energy and a Vue 3 frontend lets you pick colours, save favourites, and run science-based lighting scenes that follow a 24-hour schedule designed to support natural melatonin rhythms.

## Features

- **Manual colour control** — RGB colour picker or direct hex entry
- **Scenes** — seven phases (Dawn → Morning → Afternoon → Golden Hour → Evening → Night → Late Night) with smooth cross-fades and configurable hold times
- **Continuous mode** — automatically advances through scenes based on the current time (America/New_York)
- **Favourites** — save and recall named colours, persisted to `/data/favorites.json`
- **WebSocket live sync** — all connected clients stay in sync in real time
- **Multi-device** — controls ELK-BLEDOM and two MELK-OA21 strips simultaneously

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.13, FastAPI, Uvicorn, Bleak (BLE) |
| Frontend | Vue 3, Vite |
| Container | Podman / podman-compose |
| CI/CD | GitHub Actions → self-hosted runner (`lights`) |

## Running locally

```bash
# Backend (requires BlueZ / D-Bus access)
uv run uvicorn src.server:app --host 0.0.0.0 --port 8000

# Frontend (dev server)
cd frontend && npm install && npm run dev
```

## Running in a container

```bash
podman-compose up --build
```

The service is then available at `http://localhost:8000`.

> **Note:** the container requires host networking and D-Bus socket access to reach the Bluetooth stack — see `compose.yaml`.

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/state` | Current RGB and connected device count |
| `POST` | `/api/color` | Set colour `{r, g, b}` |
| `POST` | `/api/on` / `/api/off` | Power on / off |
| `GET` | `/api/scenes` | List all scenes |
| `GET` | `/api/scenes/status` | Currently playing scene / phase |
| `POST` | `/api/scenes/{key}/play` | Play a named scene |
| `POST` | `/api/scenes/continuous` | Start 24-hour auto-schedule |
| `POST` | `/api/scenes/stop` | Stop any running scene |
| `GET` | `/api/favorites` | List saved favourites |
| `POST` | `/api/favorites` | Add a favourite `{r, g, b, name}` |
| `DELETE` | `/api/favorites/{index}` | Remove a favourite |
| `WS` | `/ws` | Real-time RGB push updates |

## Deployment

Pushing to `main` triggers the GitHub Actions workflow which:
1. Installs Podman and podman-compose (if needed)
2. Rebuilds and restarts the container via `podman-compose up -d --build`
3. Polls `/api/state` until the service responds (up to 150 s)
4. Prunes all unused images, volumes and build cache
