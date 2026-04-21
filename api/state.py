"""Shared API state used by pipeline producer and FastAPI consumer."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mlat.models import PositionFix

# Shared ingestion queue:
# - Producer side: await fix_queue.put(fix)
# - Consumer side: fix = await fix_queue.get()
fix_queue: asyncio.Queue["PositionFix"] = asyncio.Queue()
