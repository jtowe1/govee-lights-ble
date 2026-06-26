#!/usr/bin/env python3.11
"""
Motion-activated light controller.

  Motion detected  → save scene state, turn on white
  No motion N mins → restore scene state, turn off

Run modes:
  python motion_controller.py           → mock sensor (press Enter to trigger)
  python motion_controller.py webhook   → HTTP webhook receiver (UniFi pushes to us)
"""

import asyncio
import sys
from govee import GoveeLight, _ts

NO_MOTION_TIMEOUT = 3 * 60
WHITE_BRIGHTNESS  = 100


class MotionController:
    def __init__(self):
        self.light  = GoveeLight()
        self._saved = None
        self._active = False
        self._timer = None
        self._lock  = asyncio.Lock()

    async def trigger_motion(self) -> None:
        if self._lock.locked():
            print(f"[{_ts()}] [motion] BLE operation in progress — skipping duplicate trigger")
            return

        try:
            async with self._lock:
                if self._timer:
                    self._timer.cancel()
                    self._timer = None

                if not self._active:
                    print(f"[{_ts()}] [motion] Detected — saving scene state")
                    self._saved = await self.light.get_state()
                    print(f"[{_ts()}] [motion] Saved: color_mode={self._saved.color_response[2]:#04x}, "
                          f"brightness={self._saved.brightness}%")
                    print(f"[{_ts()}] [motion] Turning on white")
                    await self.light.set_white(WHITE_BRIGHTNESS)
                    self._active = True
                else:
                    print(f"[{_ts()}] [motion] Still active — resetting timeout")
        except Exception as e:
            print(f"[{_ts()}] [motion] ERROR in trigger_motion: {e}")
            self._active = False
            self._saved = None
            return

        loop = asyncio.get_event_loop()
        self._timer = loop.call_later(
            NO_MOTION_TIMEOUT,
            lambda: asyncio.ensure_future(self._on_timeout())
        )

    async def clear_motion(self) -> None:
        if self._timer:
            self._timer.cancel()
        await self._on_timeout()

    async def _on_timeout(self) -> None:
        if not self._active:
            return
        print(f"[{_ts()}] [motion] No motion — restoring scene")
        self._active = False
        self._timer = None
        if self._saved:
            try:
                await self.light.restore_state(self._saved)
            except Exception as e:
                print(f"[{_ts()}] [motion] ERROR restoring state: {e}")
            finally:
                self._saved = None


# ── Mock driver ────────────────────────────────────────────────────────────────

async def mock_sensor(controller: MotionController) -> None:
    print("Mock motion sensor ready.")
    print(f"  Enter  → trigger motion (restores after {NO_MOTION_TIMEOUT}s)")
    print("  Ctrl+C → quit\n")
    loop = asyncio.get_event_loop()
    while True:
        await loop.run_in_executor(None, input, ">> press Enter to trigger motion ")
        await controller.trigger_motion()


async def main() -> None:
    controller = MotionController()
    mode = sys.argv[1] if len(sys.argv) > 1 else "mock"
    try:
        if mode == "webhook":
            from webhook_sensor import run as run_webhook
            await run_webhook(controller)
        else:
            await mock_sensor(controller)
    except (KeyboardInterrupt, EOFError):
        print("\nExiting.")


if __name__ == "__main__":
    asyncio.run(main())
