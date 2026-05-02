"""Tests for the FastAPI HTTP endpoints in src/server.py.

BLE I/O and filesystem access are patched out so the suite runs without
Bluetooth hardware and without the /data/ volume.

Note: httpx.ASGITransport does not trigger the ASGI lifespan, so the module-
level globals (_favorites, _clients, etc.) are reset manually in the fixture
rather than relying on the lifespan to reinitialise them.
"""
from unittest.mock import AsyncMock, patch

import pytest
import src.server as _srv
from httpx import ASGITransport, AsyncClient
from src.server import app

# ── Shared mock state ─────────────────────────────────────────────────────────

_CLEAN_STATE = {"r": 0, "g": 0, "b": 0, "step_seconds": 0.0, "mode": "manual"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    """Yield an httpx AsyncClient wired to the FastAPI app.

    Module-level globals are reset to a clean state before each test so that
    tests are isolated even though ASGITransport skips the ASGI lifespan.
    BLE calls and file-I/O are patched out entirely.
    """
    # Reset mutable module globals so tests don't bleed into each other
    _srv._favorites = []
    _srv._clients = []
    _srv._current_rgb = (0, 0, 0)
    _srv._ws_connections = []
    _srv._scene_name = None
    _srv._scene_phase = None
    _srv._continuous = False
    _srv._step_seconds = 0.0

    with (
        patch("src.server.connect_devices", new_callable=AsyncMock, return_value=[]),
        patch("src.server._load_favorites", return_value=[]),
        patch("src.server._load_state", return_value=_CLEAN_STATE),
        patch("src.server._save_state"),
        patch("src.server._save_favorites"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


# ── /api/state ────────────────────────────────────────────────────────────────

async def test_get_state_returns_200(client):
    resp = await client.get("/api/state")
    assert resp.status_code == 200


async def test_get_state_shape(client):
    data = (await client.get("/api/state")).json()
    assert "connected" in data
    assert "r" in data and "g" in data and "b" in data


async def test_get_state_rgb_from_saved_state(client):
    """State should reflect the values returned by _load_state."""
    data = (await client.get("/api/state")).json()
    assert data["r"] == _CLEAN_STATE["r"]
    assert data["g"] == _CLEAN_STATE["g"]
    assert data["b"] == _CLEAN_STATE["b"]


# ── /api/devices ──────────────────────────────────────────────────────────────

async def test_get_devices_returns_200(client):
    assert (await client.get("/api/devices")).status_code == 200


async def test_get_devices_returns_list(client):
    data = (await client.get("/api/devices")).json()
    assert isinstance(data, list)


async def test_get_devices_count_matches_config(client):
    """Should return one entry per device in DEVICES."""
    from src.main import DEVICES
    data = (await client.get("/api/devices")).json()
    assert len(data) == len(DEVICES)


async def test_get_devices_shape(client):
    for device in (await client.get("/api/devices")).json():
        assert "name" in device
        assert "address" in device
        assert "connected" in device


async def test_get_devices_all_disconnected_without_ble(client):
    """No real BLE clients → all devices should be disconnected."""
    for device in (await client.get("/api/devices")).json():
        assert device["connected"] is False


# ── /api/on and /api/off ──────────────────────────────────────────────────────

async def test_post_on_returns_ok(client):
    resp = await client.post("/api/on")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_post_off_returns_ok(client):
    resp = await client.post("/api/off")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_post_off_zeroes_rgb(client):
    """After /api/off, /api/state should report (0, 0, 0)."""
    await client.post("/api/off")
    data = (await client.get("/api/state")).json()
    assert data["r"] == 0 and data["g"] == 0 and data["b"] == 0


# ── /api/color ────────────────────────────────────────────────────────────────

async def test_post_color_returns_ok(client):
    resp = await client.post("/api/color", json={"r": 100, "g": 150, "b": 200})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


async def test_post_color_updates_state(client):
    await client.post("/api/color", json={"r": 10, "g": 20, "b": 30})
    data = (await client.get("/api/state")).json()
    assert data["r"] == 10 and data["g"] == 20 and data["b"] == 30


async def test_post_color_rejects_out_of_range(client):
    resp = await client.post("/api/color", json={"r": 300, "g": 0, "b": 0})
    assert resp.status_code == 422


async def test_post_color_rejects_negative(client):
    resp = await client.post("/api/color", json={"r": -1, "g": 0, "b": 0})
    assert resp.status_code == 422


# ── /api/scenes ───────────────────────────────────────────────────────────────

async def test_get_scenes_returns_200(client):
    assert (await client.get("/api/scenes")).status_code == 200


async def test_get_scenes_returns_list(client):
    data = (await client.get("/api/scenes")).json()
    assert isinstance(data, list)
    assert len(data) > 0


async def test_get_scenes_shape(client):
    for scene in (await client.get("/api/scenes")).json():
        assert "key" in scene
        assert "name" in scene
        assert "phases" in scene
        assert isinstance(scene["phases"], list)


async def test_get_scenes_phases_have_rgb(client):
    for scene in (await client.get("/api/scenes")).json():
        for phase in scene["phases"]:
            assert "r" in phase and "g" in phase and "b" in phase


# ── /api/scenes/status ────────────────────────────────────────────────────────

async def test_get_scenes_status_returns_200(client):
    assert (await client.get("/api/scenes/status")).status_code == 200


async def test_get_scenes_status_shape(client):
    data = (await client.get("/api/scenes/status")).json()
    assert "playing" in data
    assert "phase" in data
    assert "continuous" in data
    assert "step_seconds" in data


async def test_get_scenes_status_idle_by_default(client):
    data = (await client.get("/api/scenes/status")).json()
    assert data["playing"] is None
    assert data["continuous"] is False


# ── /api/pro-lighting ─────────────────────────────────────────────────────────

async def test_get_pro_lighting_returns_200(client):
    assert (await client.get("/api/pro-lighting")).status_code == 200


async def test_get_pro_lighting_returns_list(client):
    data = (await client.get("/api/pro-lighting")).json()
    assert isinstance(data, list)
    assert len(data) > 0


async def test_get_pro_lighting_shape(client):
    for preset in (await client.get("/api/pro-lighting")).json():
        assert "key" in preset
        assert "r" in preset and "g" in preset and "b" in preset


# ── /api/favorites ────────────────────────────────────────────────────────────

async def test_get_favorites_initially_empty(client):
    data = (await client.get("/api/favorites")).json()
    assert data == []


async def test_post_favorite_adds_entry(client):
    resp = await client.post(
        "/api/favorites", json={"r": 255, "g": 128, "b": 0, "name": "Orange"}
    )
    assert resp.status_code == 200
    favs = resp.json()
    assert len(favs) == 1
    assert favs[0] == {"r": 255, "g": 128, "b": 0, "name": "Orange"}


async def test_post_favorite_name_optional(client):
    resp = await client.post("/api/favorites", json={"r": 0, "g": 255, "b": 0})
    assert resp.status_code == 200


async def test_post_favorite_rejects_out_of_range(client):
    resp = await client.post("/api/favorites", json={"r": 256, "g": 0, "b": 0})
    assert resp.status_code == 422


async def test_delete_favorite_removes_entry(client):
    await client.post("/api/favorites", json={"r": 255, "g": 0, "b": 0, "name": "Red"})
    resp = await client.delete("/api/favorites/0")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_delete_favorite_out_of_range_returns_404(client):
    resp = await client.delete("/api/favorites/99")
    assert resp.status_code == 404


async def test_favorites_full_crud(client):
    """Add two favorites, delete the first, verify only the second remains."""
    await client.post("/api/favorites", json={"r": 255, "g": 0, "b": 0, "name": "Red"})
    await client.post("/api/favorites", json={"r": 0, "g": 0, "b": 255, "name": "Blue"})

    favs = (await client.get("/api/favorites")).json()
    assert len(favs) == 2

    await client.delete("/api/favorites/0")
    favs = (await client.get("/api/favorites")).json()
    assert len(favs) == 1
    assert favs[0]["name"] == "Blue"
