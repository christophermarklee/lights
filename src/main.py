import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from bleak import BleakScanner, BleakClient

# ── BLE protocol ─────────────────────────────────────────────────────────────

ELK_WRITE_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"

def elk_rgb(r: int, g: int, b: int) -> bytes:
    return bytes([0x7e, 0x00, 0x05, 0x03, r, g, b, 0x00, 0xef])

ELK_TURN_ON  = bytes([0x7e, 0x00, 0x04, 0xf0, 0x00, 0x00, 0x00, 0x00, 0xef])
ELK_TURN_OFF = bytes([0x7e, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0xff, 0xef])

DEVICES = [
    {"address": "BE:67:00:1E:01:44", "name": "ELK-BLEDOM"},
    {"address": "BE:28:8E:00:26:63", "name": "MELK-OA21 63"},
    {"address": "BE:28:8E:00:23:5C", "name": "MELK-OA21 5C"},
]

# ── Colour sequences ──────────────────────────────────────────────────────────
#
#  Blue   — alertness, focus (avoid late at night)
#  Teal   — blue/green balance
#  Green  — least eye strain, calm focus
#  Purple — creative, relaxed
#  Amber  — melatonin-safe wind-down
#
#  Each tuple: (R, G, B, label, hold_minutes)

_EASTERN = ZoneInfo("America/New_York")

_SEQ_MORNING = [
    (  0,  80, 180, "Blue — focus & alertness",    10),
    (  0, 160, 160, "Teal — focus & calm balance",  10),
    (  0, 160,  60, "Green — calm, easy on eyes",   15),
    ( 90,   0, 140, "Purple — creative / relaxed",  10),
    (200,  55,   0, "Amber — wind-down",             10),
]
_SEQ_AFTERNOON = [
    (  0, 160, 160, "Teal — focus & calm balance",  15),
    (  0, 160,  60, "Green — calm, easy on eyes",   15),
    ( 90,   0, 140, "Purple — creative / relaxed",  15),
    (200,  55,   0, "Amber — wind-down",             10),
]
_SEQ_EVENING = [
    (  0, 160,  60, "Green — calm, easy on eyes",   15),
    ( 90,   0, 140, "Purple — creative / relaxed",  15),
    (200,  55,   0, "Amber — wind-down",             15),
]
_SEQ_NIGHT = [
    ( 90,   0, 140, "Purple — creative / relaxed",  15),
    (200,  55,   0, "Amber — wind-down",             20),
]


def get_sequence() -> tuple[list, str]:
    hour = datetime.now(_EASTERN).hour
    if hour < 12:
        return _SEQ_MORNING,   "Morning (before noon)"
    elif hour < 17:
        return _SEQ_AFTERNOON, "Afternoon (noon-5 pm)"
    elif hour < 20:
        return _SEQ_EVENING,   "Evening (5-8 pm)"
    else:
        return _SEQ_NIGHT,     "Night (after 8 pm)"


# ── Core async helpers ────────────────────────────────────────────────────────

async def _ensure_services(client: BleakClient) -> None:
    """Bleak needs service discovery before UUID-based writes."""
    get_services = getattr(client, "get_services", None)
    if callable(get_services):
        await get_services()
    else:
        _ = client.services


async def connect_devices() -> list[BleakClient]:
    """Scan once for all configured devices, then connect to each found."""
    target_addresses = {e["address"]: e["name"] for e in DEVICES}
    print("Scanning for devices...")
    found = await BleakScanner.discover(timeout=10)
    found_map = {d.address: d for d in found if d.address in target_addresses}

    for addr, name in target_addresses.items():
        if addr not in found_map:
            print(f"  Not found: {name}")

    clients: list[BleakClient] = []
    for addr, device in found_map.items():
        name = target_addresses[addr]
        client = BleakClient(device)
        try:
            await client.connect()
            await _ensure_services(client)
            await client.write_gatt_char(ELK_WRITE_UUID, ELK_TURN_ON, response=False)
            clients.append(client)
            print(f"  Connected: {name}")
        except Exception as exc:
            print(f"  Connect failed: {name} ({exc!r})")
            try:
                await client.disconnect()
            except Exception:
                pass
    return clients


async def set_all(clients: list[BleakClient], r: int, g: int, b: int) -> None:
    """Write an RGB value to all clients, removing any that fail."""
    payload = elk_rgb(r, g, b)
    dead: list[BleakClient] = []
    for c in list(clients):
        try:
            await c.write_gatt_char(ELK_WRITE_UUID, payload, response=False)
        except Exception as exc:
            dead.append(c)
            print(f"Write failed: {c.address} ({exc})")
    for c in dead:
        clients.remove(c)
    if not clients:
        raise RuntimeError("All devices disconnected")


async def fade(
    clients: list[BleakClient],
    from_rgb: tuple[int, int, int],
    to_rgb: tuple[int, int, int],
    steps: int = 60,
    step_delay: float = 0.05,
) -> None:
    """Smoothly interpolate from one RGB colour to another."""
    for i in range(1, steps + 1):
        t = i / steps
        r = round(from_rgb[0] + (to_rgb[0] - from_rgb[0]) * t)
        g = round(from_rgb[1] + (to_rgb[1] - from_rgb[1]) * t)
        b = round(from_rgb[2] + (to_rgb[2] - from_rgb[2]) * t)
        await set_all(clients, r, g, b)
        await asyncio.sleep(step_delay)


async def run_session() -> None:
    """Connect to devices and run the time-of-day colour sequence."""
    clients = await connect_devices()
    if not clients:
        print("No devices connected.")
        return

    sequence, period = get_sequence()
    total_min = sum(m for *_, m in sequence)
    print(f"\n{period} — {len(sequence)} phases, {total_min} min total\n")

    try:
        prev_rgb = sequence[0][:3]
        await set_all(clients, *prev_rgb)

        for idx, (r, g, b, label, hold_minutes) in enumerate(sequence, start=1):
            print(f"Phase {idx}/{len(sequence)}: {label}  ({hold_minutes} min)")
            await fade(clients, prev_rgb, (r, g, b))
            prev_rgb = (r, g, b)
            await asyncio.sleep(hold_minutes * 60)

        print("\nSession complete.")
    finally:
        for c in clients:
            try:
                await c.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(run_session())
    except KeyboardInterrupt:
        print("\nStopped.")
