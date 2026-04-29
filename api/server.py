"""FastAPI WebSocket server for live aircraft track streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.state import fix_queue

if TYPE_CHECKING:
    from mlat.models import PositionFix

STALE_AIRCRAFT_SECONDS = float(os.getenv("MLAT_STALE_AIRCRAFT_SECONDS", "120"))
STALE_SWEEP_INTERVAL_SECONDS = float(os.getenv("MLAT_STALE_SWEEP_INTERVAL_SECONDS", "5"))
FIX_RATE_WINDOW_SECONDS = 60.0
SEND_TIMEOUT_SECONDS = 1.0

active_aircraft: dict[str, "PositionFix"] = {}
last_seen_monotonic: dict[str, float] = {}
recent_fix_times: deque[float] = deque()
websocket_clients: set[WebSocket] = set()
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"
logger = logging.getLogger("api.server")


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def _stdin_pipeline_ingestor() -> None:
    """Optionally ingest observations from stdin in-process for local validation."""
    from mlat.pipeline import Pipeline

    pipeline = Pipeline(source="stdin", fix_queue=fix_queue)

    logger.info("MLAT stdin ingest enabled (MLAT_READ_STDIN=1)")
    try:
        await asyncio.to_thread(pipeline.run)
        logger.warning(
            "MLAT stdin ingest stopped (EOF reached). fixes_emitted=%d",
            len(pipeline.emitted_fixes),
        )
    except Exception:
        logger.exception("MLAT stdin ingest crashed")
        raise


def _trim_fix_rate_window(now_monotonic: float) -> None:
    cutoff = now_monotonic - FIX_RATE_WINDOW_SECONDS
    while recent_fix_times and recent_fix_times[0] < cutoff:
        recent_fix_times.popleft()


def _parse_timestamp_to_unix_ms(timestamp_utc: str) -> int:
    if not timestamp_utc:
        return int(time.time() * 1000)

    try:
        parsed = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
    except ValueError:
        return int(time.time() * 1000)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _serialize_fix(fix: "PositionFix") -> dict[str, Any]:
    return {
        "icao": fix.icao,
        "callsign": fix.callsign,
        "lat": fix.lat,
        "lon": fix.lon,
        "alt_ft": fix.alt_ft,
        "method": fix.method,
        "gdop": fix.gdop,
        "sensor_count": fix.sensor_count,
        "ts": _parse_timestamp_to_unix_ms(fix.timestamp_utc),
    }


async def _send_message(client: WebSocket, message_json: str) -> None:
    await asyncio.wait_for(client.send_text(message_json), timeout=SEND_TIMEOUT_SECONDS)


async def broadcast(message: dict[str, Any]) -> None:
    if not websocket_clients:
        return

    clients = list(websocket_clients)
    payload = json.dumps(message)

    results = await asyncio.gather(
        *[_send_message(client, payload) for client in clients],
        return_exceptions=True,
    )

    for client, result in zip(clients, results):
        if isinstance(result, Exception):
            websocket_clients.discard(client)
            try:
                await client.close()
            except Exception:
                pass


async def process_and_broadcast(fix: "PositionFix") -> None:
    now = time.monotonic()
    icao = fix.icao.upper()

    active_aircraft[icao] = fix
    last_seen_monotonic[icao] = now
    recent_fix_times.append(now)
    _trim_fix_rate_window(now)

    await broadcast({"type": "fix", "data": _serialize_fix(fix)})


async def fix_consumer() -> None:
    while True:
        fix = await fix_queue.get()
        try:
            await process_and_broadcast(fix)
        except Exception:
            logger.exception("Failed to process and broadcast fix; continuing")


async def stale_aircraft_reaper() -> None:
    while True:
        await asyncio.sleep(STALE_SWEEP_INTERVAL_SECONDS)
        now = time.monotonic()

        stale_icaos = [
            icao
            for icao, last_seen in last_seen_monotonic.items()
            if now - last_seen > STALE_AIRCRAFT_SECONDS
        ]

        for icao in stale_icaos:
            active_aircraft.pop(icao, None)
            last_seen_monotonic.pop(icao, None)
            await broadcast({"type": "remove", "data": {"icao": icao}})


@asynccontextmanager
async def lifespan(_: FastAPI):
    consumer_task = asyncio.create_task(fix_consumer())
    reaper_task = asyncio.create_task(stale_aircraft_reaper())
    stdin_ingestor_task: asyncio.Task[None] | None = None

    if _read_bool_env("MLAT_READ_STDIN", default=False):
        stdin_ingestor_task = asyncio.create_task(_stdin_pipeline_ingestor())

    try:
        yield
    finally:
        consumer_task.cancel()
        reaper_task.cancel()
        shutdown_tasks: list[asyncio.Task[None]] = [consumer_task, reaper_task]
        if stdin_ingestor_task is not None:
            stdin_ingestor_task.cancel()
            shutdown_tasks.append(stdin_ingestor_task)
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Development only; lock down for production frontend origin.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws/tracks")
async def ws_tracks(websocket: WebSocket) -> None:
    await websocket.accept()
    websocket_clients.add(websocket)

    snapshot = [_serialize_fix(fix) for fix in active_aircraft.values()]
    await websocket.send_json({"type": "snapshot", "data": snapshot})

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_clients.discard(websocket)
    except Exception:
        websocket_clients.discard(websocket)
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/health")
async def health() -> dict[str, Any]:
    now = time.monotonic()
    _trim_fix_rate_window(now)

    return {
        "status": "ok",
        "active_aircraft": len(active_aircraft),
        "fixes_per_minute": len(recent_fix_times),
    }


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="0.0.0.0", port=8000)
