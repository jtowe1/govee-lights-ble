#!/usr/bin/env python3.11
"""Govee BLE light controller with state save/restore."""

import asyncio
from dataclasses import dataclass
from bleak import BleakScanner, BleakClient

CONTROL_CHAR = "00010203-0405-0607-0809-0a0b0c0d2b11"
NOTIFY_CHAR  = "00010203-0405-0607-0809-0a0b0c0d2b10"

QUERY_POWER      = bytes([0xAA, 0x01] + [0x00]*17 + [0xAB])
QUERY_BRIGHTNESS = bytes([0xAA, 0x04] + [0x00]*17 + [0xAE])
QUERY_COLOR      = bytes([0xAA, 0x05] + [0x00]*17 + [0xAF])


def _packet(*payload: int) -> bytes:
    """Build a 20-byte write packet with XOR checksum."""
    data = list(payload) + [0] * (19 - len(payload))
    checksum = 0
    for b in data:
        checksum ^= b
    return bytes(data + [checksum])


def _query_to_write(response: bytes) -> bytes:
    """Convert a query response (0xAA prefix) into a write command (0x33 prefix)."""
    payload = [0x33] + list(response[1:19])
    checksum = 0
    for b in payload:
        checksum ^= b
    return bytes(payload + [checksum])


@dataclass
class LightState:
    power: bool
    brightness: int      # 0–100
    color_response: bytes  # raw query response, used to restore color mode


class GoveeLight:
    def __init__(self, name: str = "Govee_H705B", address: str | None = None):
        self.name = name
        self._address: str | None = address

    async def _resolve(self) -> str:
        if self._address:
            return self._address
        print(f"Scanning for {self.name} (up to 60s)...")
        found: asyncio.Future[str] = asyncio.get_event_loop().create_future()

        def on_detect(device, _adv) -> None:
            if self.name in (device.name or "") and not found.done():
                found.set_result(device.address)

        async with BleakScanner(detection_callback=on_detect):
            try:
                self._address = await asyncio.wait_for(found, timeout=60.0)
            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Device '{self.name}' not found — is it plugged in and advertising?"
                )

        print(f"Found: {self.name} @ {self._address}")
        return self._address

    async def _query(self, client: BleakClient, pkt: bytes) -> bytes:
        """Send a query packet and return the first notification response."""
        result: asyncio.Future[bytes] = asyncio.get_event_loop().create_future()

        def handler(_handle, data: bytearray) -> None:
            if not result.done():
                result.set_result(bytes(data))

        await client.start_notify(NOTIFY_CHAR, handler)
        await client.write_gatt_char(CONTROL_CHAR, pkt, response=True)
        response = await asyncio.wait_for(result, timeout=5.0)
        await client.stop_notify(NOTIFY_CHAR)
        return response

    async def get_state(self) -> LightState:
        client = await self._connect()
        try:
            power_resp      = await self._query(client, QUERY_POWER)
            brightness_resp = await self._query(client, QUERY_BRIGHTNESS)
            color_resp      = await self._query(client, QUERY_COLOR)
        finally:
            await client.disconnect()
        power      = power_resp[2] == 0x01
        brightness = brightness_resp[2]
        return LightState(power=power, brightness=brightness, color_response=color_resp)

    async def _connect(self) -> BleakClient:
        """Return a connected BleakClient, re-scanning if the cached address is stale."""
        from bleak.exc import BleakDeviceNotFoundError
        address = await self._resolve()
        try:
            client = BleakClient(address, timeout=20.0)
            await client.connect()
            return client
        except BleakDeviceNotFoundError:
            print("Address stale, re-scanning...")
            self._address = None
            address = await self._resolve()
            client = BleakClient(address, timeout=20.0)
            await client.connect()
            return client

    async def _send(self, pkt: bytes) -> None:
        client = await self._connect()
        try:
            await client.write_gatt_char(CONTROL_CHAR, pkt, response=True)
        finally:
            await client.disconnect()

    async def turn_on(self) -> None:
        await self._send(_packet(0x33, 0x01, 0x01))

    async def turn_off(self) -> None:
        await self._send(_packet(0x33, 0x01, 0x00))

    async def set_brightness(self, pct: int) -> None:
        await self._send(_packet(0x33, 0x04, max(0, min(100, pct))))

    async def set_white(self, brightness: int = 100) -> None:
        """Set to white (mode 0x15) and turn on — batched in one connection."""
        client = await self._connect()
        try:
            await client.write_gatt_char(CONTROL_CHAR, _packet(0x33, 0x05, 0x15), response=True)
            await asyncio.sleep(0.2)
            await client.write_gatt_char(CONTROL_CHAR, _packet(0x33, 0x04, brightness), response=True)
            await asyncio.sleep(0.2)
            await client.write_gatt_char(CONTROL_CHAR, _packet(0x33, 0x01, 0x01), response=True)
        finally:
            await client.disconnect()

    async def restore_state(self, state: LightState) -> None:
        """Restore a previously saved state without turning the light on."""
        client = await self._connect()
        try:
            color_cmd = _query_to_write(state.color_response)
            await client.write_gatt_char(CONTROL_CHAR, color_cmd, response=True)
            await asyncio.sleep(0.2)
            await client.write_gatt_char(CONTROL_CHAR, _packet(0x33, 0x04, state.brightness), response=True)
            await asyncio.sleep(0.2)
            power_cmd = _packet(0x33, 0x01, 0x01 if state.power else 0x00)
            await client.write_gatt_char(CONTROL_CHAR, power_cmd, response=True)
        finally:
            await client.disconnect()
        print(f"Restored: power={'on' if state.power else 'off'}, brightness={state.brightness}%, "
              f"color_mode={state.color_response[2]:#04x}")
