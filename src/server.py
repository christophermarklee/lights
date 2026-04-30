import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .main import (
    connect_devices,
    set_all,
    ELK_WRITE_UUID,
    ELK_TURN_ON,
    ELK_TURN_OFF,
)

# ── Scene definitions (science-based circadian lighting) ──────────────────────
#
# Research basis (Harvard Health, Sleep Foundation, PMC6751071, Lockley et al.):
#   • Melanopsin (ipRGC) peaks at ~480 nm — blue/cyan drives alertness &
#     suppresses melatonin. Use in morning, phase out by afternoon.
#   • Blue light suppresses melatonin ~2× longer than green (Harvard study).
#   • Red/long-wave (>600 nm) has minimal melanopsin stimulation — safe at night.
#   • "Use dim red lights for night lights" — Harvard Health Publishing.
#   • Hold times are calibrated so 7 scenes × phases = exactly 24 hours.
#
# 24-hour schedule:
#   05:00 Dawn        (2 h)   — soft warm sunrise ramp
#   07:00 Morning     (5 h)   — peak blue-cyan alertness
#   12:00 Afternoon   (5 h)   — cool greens, sustained focus
#   17:00 Golden Hour (2 h)   — warm gold, blue fades
#   19:00 Evening     (2 h)   — ambers, melatonin window
#   21:00 Night       (2 h)   — dim red, sleep prep
#   23:00 Late Night  (6 h)   — near-dark red, 11 pm–5 am
#
# Phases: {r, g, b, label, hold_minutes}

SCENES = [
    {
        "key": "dawn",
        "name": "Dawn",
        "icon": "🌄",
        "description": "Sunrise simulation — dim warm reds building to golden daylight over 2 hours. Nudges cortisol and core body temperature gently upward.",
        "phases": [
            {"r": 155, "g":  30, "b":   0, "label": "Sunrise Glow — dim warm red",            "hold_minutes": 30},
            {"r": 210, "g":  85, "b":   5, "label": "Warm Orange — brightening sky",           "hold_minutes": 30},
            {"r": 232, "g": 162, "b":  22, "label": "Golden Yellow — full sunrise",             "hold_minutes": 30},
            {"r": 242, "g": 198, "b":  75, "label": "Bright Gold — morning light arrives",      "hold_minutes": 30},
        ],
    },
    {
        "key": "morning",
        "name": "Morning",
        "icon": "🌅",
        "description": "Blue-rich cool light (≈6500 K) that strongly stimulates melanopsin, advances the circadian clock, and peaks cortisol — essential for alertness and mood.",
        "phases": [
            {"r":  55, "g": 150, "b": 248, "label": "Sky Blue — clock advance & cortisol",     "hold_minutes": 60},
            {"r":   0, "g": 172, "b": 212, "label": "Cyan — peak melanopsin activation",        "hold_minutes": 60},
            {"r":  25, "g": 198, "b": 158, "label": "Cool Teal — alert focus",                  "hold_minutes": 60},
            {"r":   0, "g": 192, "b": 108, "label": "Green-Teal — calm productivity",           "hold_minutes": 60},
            {"r":  45, "g": 182, "b": 128, "label": "Seafoam — sustained deep focus",           "hold_minutes": 60},
        ],
    },
    {
        "key": "afternoon",
        "name": "Afternoon",
        "icon": "☀️",
        "description": "Neutral cool-to-warm greens (≈4000–5000 K) — supports sustained focus while gently reducing the strong blue stimulus of morning.",
        "phases": [
            {"r":   0, "g": 182, "b": 142, "label": "Bright Teal — deep focus",                "hold_minutes": 60},
            {"r":  18, "g": 198, "b":  78, "label": "Cool Green — creative calm",               "hold_minutes": 60},
            {"r":   0, "g": 182, "b":  98, "label": "Pure Green — easiest on the eyes",         "hold_minutes": 60},
            {"r":  55, "g": 178, "b":  55, "label": "Bright Green — energised focus",           "hold_minutes": 60},
            {"r": 125, "g": 178, "b":  18, "label": "Warm Green-Gold — gentle warm shift",      "hold_minutes": 60},
        ],
    },
    {
        "key": "golden_hour",
        "name": "Golden Hour",
        "icon": "🌤️",
        "description": "Warm golds and oranges mimicking late-afternoon sun (≈3000–3500 K). Blue light fades — a clear biological cue that evening is approaching.",
        "phases": [
            {"r": 245, "g": 162, "b":  12, "label": "Warm Gold — blue fading out",             "hold_minutes": 40},
            {"r": 245, "g": 122, "b":   6, "label": "Golden Orange — pre-sunset",               "hold_minutes": 40},
            {"r": 235, "g":  88, "b":   2, "label": "Sunset Orange — transition to evening",    "hold_minutes": 40},
        ],
    },
    {
        "key": "evening",
        "name": "Evening",
        "icon": "🌇",
        "description": "Progressive ambers (≈2200–2700 K) with near-zero blue — allows melatonin to begin rising naturally 1–2 hours before bed.",
        "phases": [
            {"r": 218, "g":  72, "b":   0, "label": "Warm Amber — melatonin window opens",     "hold_minutes": 40},
            {"r": 198, "g":  48, "b":   0, "label": "Deep Amber — wind-down deepens",           "hold_minutes": 40},
            {"r": 162, "g":  26, "b":   0, "label": "Dark Amber — strong relaxation cue",       "hold_minutes": 40},
        ],
    },
    {
        "key": "night",
        "name": "Night",
        "icon": "🌙",
        "description": "Dim reds with essentially zero blue or green — minimal melanopsin activation, melatonin rises freely for sleep preparation.",
        "phases": [
            {"r": 128, "g":  13, "b":   0, "label": "Dim Red — zero blue stimulus",            "hold_minutes": 60},
            {"r":  82, "g":   7, "b":   0, "label": "Deep Red — sleep prep",                    "hold_minutes": 60},
        ],
    },
    {
        "key": "late_night",
        "name": "Late Night",
        "icon": "🌑",
        "description": "Near-dark dim red for 11 pm–5 am. Absolute minimum melanopsin impact — for those still awake, this protects sleep biology and melatonin production.",
        "phases": [
            {"r":  48, "g":   4, "b":   0, "label": "Near-Dark Red — ultra-low stimulus",      "hold_minutes": 180},
            {"r":  28, "g":   2, "b":   0, "label": "Very Dim Red — preserve sleep biology",    "hold_minutes": 180},
        ],
    },
]

_SCENES_BY_KEY = {s["key"]: s for s in SCENES}

# ── Professional lighting presets ──────────────────────────────────────────────
# Color-temperature approximations for RGB LED strips.
# Values are practical rather than physically exact — tuned for use as room fill light.
PRO_LIGHTING = [
    {
        "key": "webcam",
        "name": "Webcam / Meeting",
        "icon": "💻",
        "kelvin": 4500,
        "description": "Neutral warm white, flattering on skin tones. Ideal for video calls, meetings, and casual streaming.",
        "r": 255, "g": 210, "b": 155,
    },
    {
        "key": "portrait_warm",
        "name": "Portrait Warm",
        "icon": "🎙️",
        "kelvin": 4000,
        "description": "Soft warm key light. Flattering fill for on-camera interviews, podcasts, and talking-head video.",
        "r": 255, "g": 185, "b": 105,
    },
    {
        "key": "studio_tungsten",
        "name": "Studio Tungsten",
        "icon": "🎬",
        "kelvin": 3200,
        "description": "Classic 3200 K film studio standard. Warm and cinematic — the traditional TV and movie lighting reference.",
        "r": 255, "g": 160, "b": 65,
    },
    {
        "key": "daylight_photo",
        "name": "Daylight / Photography",
        "icon": "📷",
        "kelvin": 5500,
        "description": "Natural 5500 K daylight balance — matches electronic flash and outdoor light for true-colour photography.",
        "r": 255, "g": 238, "b": 210,
    },
    {
        "key": "overcast_reference",
        "name": "Overcast / Reference",
        "icon": "🖥️",
        "kelvin": 6500,
        "description": "Cool 6500 K D65 reference — the NTSC/PAL TV and sRGB/internet standard. Good for colour-accurate work.",
        "r": 205, "g": 220, "b": 255,
    },
    {
        "key": "cinematic_golden",
        "name": "Cinematic Golden",
        "icon": "🌇",
        "kelvin": 2700,
        "description": "Dramatic warm amber at 2700 K. Moody low-key lighting for B-roll, product shots, and creative portraits.",
        "r": 255, "g": 135, "b": 40,
    },
]

FAVORITES_FILE = Path("/data/favorites.json")
STATE_FILE = Path("/data/state.json")


def _load_favorites() -> list[dict]:
    try:
        return json.loads(FAVORITES_FILE.read_text())
    except Exception:
        return []


def _save_favorites(favs: list[dict]) -> None:
    FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAVORITES_FILE.write_text(json.dumps(favs))


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"mode": "continuous", "r": 0, "g": 0, "b": 0}


def _save_state() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({
        "mode": "continuous" if _continuous else "manual",
        "r": _current_rgb[0],
        "g": _current_rgb[1],
        "b": _current_rgb[2],
    }))

# ── State ─────────────────────────────────────────────────────────────────────

_clients: list = []
_current_rgb: tuple[int, int, int] = (0, 0, 0)
_ws_connections: list[WebSocket] = []
_favorites: list[dict] = []

_scene_task: asyncio.Task | None = None
_scene_name: str | None = None
_scene_phase: int | None = None
_continuous: bool = False


async def _play_scene_phases(key: str) -> None:
    """Play all phases of one scene. Propagates CancelledError."""
    global _current_rgb, _scene_name, _scene_phase
    scene = _SCENES_BY_KEY.get(key)
    if not scene:
        return
    _scene_name = key
    for i, phase in enumerate(scene["phases"]):
        _scene_phase = i
        target = (phase["r"], phase["g"], phase["b"])
        from_rgb = _current_rgb
        # 3-second smooth fade (60 steps × 50 ms)
        for j in range(1, 61):
            t = j / 60
            r = round(from_rgb[0] + (target[0] - from_rgb[0]) * t)
            g = round(from_rgb[1] + (target[1] - from_rgb[1]) * t)
            b = round(from_rgb[2] + (target[2] - from_rgb[2]) * t)
            if _clients:
                try:
                    await set_all(_clients, r, g, b)
                except RuntimeError:
                    pass
            _current_rgb = (r, g, b)
            await _broadcast(r, g, b)
            await asyncio.sleep(0.05)
        # Hold — sleep in short slices to stay responsive to cancellation
        hold_s = phase["hold_minutes"] * 60
        slept = 0.0
        while slept < hold_s:
            await asyncio.sleep(min(1.0, hold_s - slept))
            slept += 1.0


async def _run_scene(key: str) -> None:
    """Single-scene background task."""
    global _scene_name, _scene_phase
    try:
        await _play_scene_phases(key)
    except asyncio.CancelledError:
        pass
    finally:
        _scene_name = None
        _scene_phase = None


_NY = ZoneInfo("America/New_York")
_SCENE_SCHEDULE = [
    (23, "late_night"),   # 11 pm – midnight
    (21, "night"),        # 9  pm – 11 pm
    (19, "evening"),      # 7  pm – 9  pm
    (17, "golden_hour"),  # 5  pm – 7  pm
    (12, "afternoon"),    # noon  – 5  pm
    ( 7, "morning"),      # 7  am – noon
    ( 5, "dawn"),         # 5  am – 7  am
    ( 0, "late_night"),   # midnight – 5 am
]


def _scene_for_now() -> str:
    """Return the scene key appropriate for the current NY time."""
    hour = datetime.now(_NY).hour
    for threshold, key in _SCENE_SCHEDULE:
        if hour >= threshold:
            return key
    return "late_night"


def _next_scene_key(current_key: str) -> str:
    """Return the scene that follows the given one (wraps late_night → dawn)."""
    keys = [s["key"] for s in SCENES]  # dawn → morning → afternoon → golden_hour → evening → night → late_night
    idx = keys.index(current_key) if current_key in keys else -1
    return keys[(idx + 1) % len(keys)]


async def _run_continuous() -> None:
    """Play scenes 24/7, starting from the current time-of-day in New York.

    Begins with whichever scene matches the current hour, then advances to
    the next scene chronologically when each one finishes.
    """
    global _continuous, _scene_name, _scene_phase
    _continuous = True
    key = _scene_for_now()
    try:
        while True:
            await _play_scene_phases(key)
            key = _next_scene_key(key)
    except asyncio.CancelledError:
        pass
    finally:
        _continuous = False
        _scene_name = None
        _scene_phase = None


async def _broadcast(r: int, g: int, b: int) -> None:
    dead = []
    for ws in list(_ws_connections):
        try:
            await ws.send_json({"r": r, "g": g, "b": b})
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_connections.remove(ws)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _clients, _favorites, _current_rgb, _scene_task
    _favorites = _load_favorites()
    saved = _load_state()
    _current_rgb = (saved["r"], saved["g"], saved["b"])
    _clients = await connect_devices()
    # Restore last color to devices
    if _clients and any(_current_rgb):
        try:
            await set_all(_clients, *_current_rgb)
        except RuntimeError:
            pass
    # Resume mode: continuous by default, or if that's what was running
    if saved.get("mode", "continuous") == "continuous":
        _scene_task = asyncio.create_task(_run_continuous())
    yield
    for c in _clients:
        try:
            await c.disconnect()
        except Exception:
            pass


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ColorPayload(BaseModel):
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


class FavoritePayload(BaseModel):
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)
    name: str = ""


@app.get("/api/favorites")
async def get_favorites():
    return _favorites


@app.post("/api/favorites")
async def add_favorite(payload: FavoritePayload):
    fav = {"r": payload.r, "g": payload.g, "b": payload.b, "name": payload.name}
    _favorites.append(fav)
    _save_favorites(_favorites)
    return _favorites


@app.delete("/api/favorites/{index}")
async def delete_favorite(index: int):
    if index < 0 or index >= len(_favorites):
        raise HTTPException(status_code=404, detail="Not found")
    _favorites.pop(index)
    _save_favorites(_favorites)
    return _favorites


@app.get("/api/state")
async def get_state():
    r, g, b = _current_rgb
    return {"connected": len(_clients), "r": r, "g": g, "b": b}


@app.post("/api/color")
async def set_color(payload: ColorPayload):
    global _current_rgb
    _current_rgb = (payload.r, payload.g, payload.b)
    if _clients:
        try:
            await set_all(_clients, *_current_rgb)
        except RuntimeError:
            pass
    await _broadcast(*_current_rgb)
    _save_state()
    return {"ok": True}


@app.post("/api/on")
async def turn_on():
    global _current_rgb
    for c in list(_clients):
        try:
            await c.write_gatt_char(ELK_WRITE_UUID, ELK_TURN_ON, response=False)
        except Exception:
            pass
    # restore last known colour
    if _clients:
        try:
            await set_all(_clients, *_current_rgb)
        except RuntimeError:
            pass
    await _broadcast(*_current_rgb)
    _save_state()
    return {"ok": True}


@app.post("/api/off")
async def turn_off():
    global _current_rgb
    _current_rgb = (0, 0, 0)
    for c in list(_clients):
        try:
            await c.write_gatt_char(ELK_WRITE_UUID, ELK_TURN_OFF, response=False)
        except Exception:
            pass
    await _broadcast(0, 0, 0)
    _save_state()
    return {"ok": True}


@app.get("/api/scenes")
async def get_scenes():
    return SCENES


@app.get("/api/pro-lighting")
async def get_pro_lighting():
    return PRO_LIGHTING


@app.get("/api/scenes/status")
async def get_scene_status():
    if _scene_name and _scene_phase is not None:
        scene = _SCENES_BY_KEY[_scene_name]
        label = scene["phases"][_scene_phase]["label"]
    else:
        label = None
    return {"playing": _scene_name, "phase": _scene_phase, "phase_label": label, "continuous": _continuous}


@app.post("/api/scenes/continuous")
async def start_continuous():
    global _scene_task
    if _scene_task and not _scene_task.done():
        _scene_task.cancel()
        try:
            await _scene_task
        except (asyncio.CancelledError, Exception):
            pass
    _scene_task = asyncio.create_task(_run_continuous())
    _save_state()
    return {"ok": True, "continuous": True}


@app.post("/api/scenes/{key}/play")
async def play_scene(key: str):
    global _scene_task
    if key not in _SCENES_BY_KEY:
        raise HTTPException(status_code=404, detail="Scene not found")
    if _scene_task and not _scene_task.done():
        _scene_task.cancel()
        try:
            await _scene_task
        except (asyncio.CancelledError, Exception):
            pass
    _scene_task = asyncio.create_task(_run_scene(key))
    _save_state()
    return {"ok": True, "playing": key}


@app.post("/api/scenes/stop")
async def stop_scene():
    global _scene_task
    if _scene_task and not _scene_task.done():
        _scene_task.cancel()
        try:
            await _scene_task
        except (asyncio.CancelledError, Exception):
            pass
    _save_state()
    return {"ok": True}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_connections.append(ws)
    r, g, b = _current_rgb
    await ws.send_json({"r": r, "g": g, "b": b})
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in _ws_connections:
            _ws_connections.remove(ws)


# Serve built frontend (production)
try:
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="static")
except RuntimeError:
    pass  # frontend not built yet
