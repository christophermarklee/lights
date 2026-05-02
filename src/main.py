import asyncio

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
