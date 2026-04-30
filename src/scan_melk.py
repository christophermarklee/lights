import asyncio
from bleak import BleakScanner, BleakClient

async def inspect(address):
    print(f"Scanning {address}...", flush=True)
    d = await BleakScanner.find_device_by_address(address, timeout=10)
    if d is None:
        print("  NOT FOUND", flush=True)
        return
    print(f"  Found: {d.name}", flush=True)
    async with BleakClient(d) as c:
        for s in c.services:
            print(f"  Svc: {s.uuid}")
            for ch in s.characteristics:
                print(f"    {ch.uuid}  {ch.properties}")
    print(flush=True)

async def main():
    for a in ["BE:28:8E:00:26:63", "BE:28:8E:00:23:5C"]:
        await inspect(a)

asyncio.run(main())
