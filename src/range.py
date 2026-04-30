import asyncio
from bleak import BleakScanner

ADDRESSES = {
    "BE:67:00:1E:01:44": "ELK-BLEDOM",
    "BE:28:8E:00:26:63": "MELK-OA21 63",
    "BE:28:8E:00:23:5C": "MELK-OA21 5C",
    "90:00:00:5E:89:C3": "Smart Light",
}

TX_POWER = -59   # dBm at 1 metre (typical BLE default)
N = 2.5          # path loss exponent (indoor)
METRES_TO_FEET = 3.28084
SCAN_INTERVAL = 3.0  # seconds between updates


def rssi_to_feet(rssi: int) -> float:
    d_m = 10 ** ((TX_POWER - rssi) / (10 * N))
    return d_m * METRES_TO_FEET


async def main():
    print("Scanning... Press Ctrl+C to stop.\n")
    latest: dict[str, int] = {}

    def callback(device, adv):
        if device.address in ADDRESSES:
            latest[device.address] = adv.rssi

    async with BleakScanner(callback):
        while True:
            await asyncio.sleep(SCAN_INTERVAL)
            print("\033[H\033[J", end="")  # clear screen
            print(f"{'Device':<20}  {'RSSI':>7}  {'Est. Distance':>14}")
            print("-" * 46)
            for addr, label in ADDRESSES.items():
                if addr in latest:
                    rssi = latest[addr]
                    ft = rssi_to_feet(rssi)
                    print(f"{label:<20}  {rssi:>4} dBm  {ft:>10.1f} ft")
                else:
                    print(f"{label:<20}  {'--':>4}       {'not detected':>14}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
