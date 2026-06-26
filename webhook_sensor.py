#!/usr/bin/env python3.11
"""
UniFi Protect webhook receiver.

Runs a local HTTP server. Point your UniFi webhook at:
  http://<this-machine-ip>:<PORT>/motion

Logs the raw payload on first hit so you can inspect the shape,
then routes motion start/end to the controller.
"""

import asyncio
import json
import os
from aiohttp import web

PORT = int(os.getenv("WEBHOOK_PORT", "8123"))

_first_payload = True  # log raw JSON once so we can inspect the shape


def _is_motion_start(data: dict) -> bool:
    """Return True if this payload represents motion/person detection."""
    # UniFi Protect alarm automation webhook:
    #   { "alarm": { "triggers": [{"key": "person", ...}] }, "timestamp": ... }
    if "alarm" in data:
        return True
    # Raw motion event fallback:
    #   { "type": "motion", "end": null }
    event = data.get("event", data)
    etype = event.get("type", "")
    return "motion" in etype.lower() and event.get("end") is None


def _is_motion_end(data: dict) -> bool:
    # Alarm webhooks don't have end events — timeout handles it.
    if "alarm" in data:
        return False
    event = data.get("event", data)
    etype = event.get("type", "")
    return "motion" in etype.lower() and event.get("end") is not None


def make_app(controller) -> web.Application:
    app = web.Application()

    async def handle(request: web.Request) -> web.Response:
        global _first_payload
        try:
            data = await request.json()
        except Exception:
            text = await request.text()
            print(f"[webhook] Non-JSON payload: {text[:200]}")
            return web.Response(status=400, text="expected JSON")

        if _first_payload:
            print(f"[webhook] First payload (raw):\n{json.dumps(data, indent=2)}\n")
            _first_payload = False

        if _is_motion_start(data):
            asyncio.ensure_future(controller.trigger_motion())
        elif _is_motion_end(data):
            asyncio.ensure_future(controller.clear_motion())
        else:
            print(f"[webhook] Unhandled event type: {data.get('type') or data.get('event', {}).get('type')}")

        return web.Response(text="ok")

    app.router.add_post("/motion", handle)
    return app


async def run(controller) -> None:
    app = make_app(controller)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"[webhook] Listening on http://0.0.0.0:{PORT}/motion")
    print(f"[webhook] Point UniFi Protect webhook → http://<this-mac-ip>:{PORT}/motion\n")
    # Run forever alongside the rest of the event loop
    await asyncio.Event().wait()


# ── Standalone test ────────────────────────────────────────────────────────────

class _MockController:
    async def trigger_motion(self) -> None:
        print("[mock] trigger_motion()")

    async def clear_motion(self) -> None:
        print("[mock] clear_motion()")


if __name__ == "__main__":
    asyncio.run(run(_MockController()))
