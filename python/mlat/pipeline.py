"""Pipeline entry point and message flow orchestration."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
from queue import Queue
from typing import Awaitable, Callable, Iterable, Literal, Optional

from .correlation import CorrelationBuffer
from .cpr import CPRDecoder
from .models import MLATGroup, Observation, PositionFix
from .router import MessageClass, classify_message, extract_icao, extract_type_code
from .tracker import AircraftTracker

logger = logging.getLogger(__name__)


def _load_shared_fix_queue() -> Optional[asyncio.Queue[PositionFix]]:
    """Load the shared FastAPI queue when running full-stack from repo root."""
    try:
        from api.state import fix_queue as shared_fix_queue
    except Exception:
        return None
    return shared_fix_queue


class Pipeline:
    """Pipeline entry point for processing incoming observations."""

    def __init__(
        self,
        source: Literal["stdin", "redpanda"] = "stdin",
        fix_callback: Optional[Callable[[PositionFix], None | Awaitable[None]]] = None,
        fix_queue: Optional[Queue[PositionFix] | asyncio.Queue[PositionFix]] = None,
        mlat_group_callback: Optional[Callable[[MLATGroup], None]] = None,
        min_sensors: int = 4,
    ) -> None:
        self.source = source
        self.cpr_decoder = CPRDecoder()
        self.correlation_buffer = CorrelationBuffer(min_sensors=min_sensors)
        self.aircraft_tracker = AircraftTracker()

        self.fix_callback = fix_callback
        self.fix_queue = fix_queue if fix_queue is not None else _load_shared_fix_queue()
        self.mlat_group_callback = mlat_group_callback
        self._async_queue_loop: Optional[asyncio.AbstractEventLoop] = None
        if isinstance(self.fix_queue, asyncio.Queue):
            try:
                self._async_queue_loop = asyncio.get_running_loop()
            except RuntimeError:
                self._async_queue_loop = None

        self.emitted_fixes: list[PositionFix] = []
        self.emitted_mlat_groups: list[MLATGroup] = []

        self.default_ref_lat = 50.1
        self.default_ref_lon = -5.6

    def process_observation(self, obs: Observation) -> None:
        """Route and process a single observation."""
        message_class = classify_message(obs)
        icao = extract_icao(obs.hex, obs.df)

        if message_class in {MessageClass.ADSB_AIRBORNE_POSITION, MessageClass.ADSB_SURFACE_POSITION}:
            if icao is None:
                return

            tc = extract_type_code(obs.hex)
            if tc is None:
                return

            self.cpr_decoder.store_cpr_frame(icao, obs, tc)
            ref_lat, ref_lon = self.aircraft_tracker.get_reference(icao, self.default_ref_lat, self.default_ref_lon)
            fix = self.cpr_decoder.try_decode_position(icao, ref_lat, ref_lon)

            if fix is not None:
                self.aircraft_tracker.update(fix)
                self._emit_fix(fix)
            return

        if message_class == MessageClass.NON_ADSB:
            mlat_group = self.correlation_buffer.add(obs)
            if mlat_group is not None:
                self._emit_mlat_group(mlat_group)
            return

        # ADSB_OTHER / ADSB_VELOCITY / ADSB_IDENTIFICATION are metadata-only at this stage.
        return

    def process_observations(self, observations: Iterable[Observation]) -> None:
        """Process an iterable of observations in order."""
        for obs in observations:
            try:
                self.process_observation(obs)
            except Exception:
                logger.exception("Observation processing failed in sync path; skipping observation")

    async def process_observation_async(self, obs: Observation) -> None:
        """Async variant of process_observation for asyncio queue producers."""
        message_class = classify_message(obs)
        icao = extract_icao(obs.hex, obs.df)

        if message_class in {MessageClass.ADSB_AIRBORNE_POSITION, MessageClass.ADSB_SURFACE_POSITION}:
            if icao is None:
                return

            tc = extract_type_code(obs.hex)
            if tc is None:
                return

            self.cpr_decoder.store_cpr_frame(icao, obs, tc)
            ref_lat, ref_lon = self.aircraft_tracker.get_reference(icao, self.default_ref_lat, self.default_ref_lon)
            fix = self.cpr_decoder.try_decode_position(icao, ref_lat, ref_lon)

            if fix is not None:
                self.aircraft_tracker.update(fix)
                await self._emit_fix_async(fix)
            return

        if message_class == MessageClass.NON_ADSB:
            mlat_group = self.correlation_buffer.add(obs)
            if mlat_group is not None:
                self._emit_mlat_group(mlat_group)
            return

        return

    async def process_observations_async(self, observations: Iterable[Observation]) -> None:
        """Process observations asynchronously (for await fix_queue.put usage)."""
        for obs in observations:
            try:
                await self.process_observation_async(obs)
            except Exception:
                logger.exception("Observation processing failed in async path; skipping observation")

    def run(
        self,
        kafka_bootstrap: str = "localhost:9092",
        kafka_topic: str = "modes-observations",
        source: Optional[Literal["stdin", "redpanda"]] = None,
    ) -> None:
        """Run the pipeline loop using stdin or Redpanda as the source."""
        stream_source = source or self.source

        if stream_source == "stdin":
            observations = self._read_observations_from_stdin()
        elif stream_source == "redpanda":
            observations = self._read_observations_from_redpanda(kafka_bootstrap, kafka_topic)
        else:
            raise ValueError(f"Unsupported source: {stream_source}")

        self.process_observations(observations)

    def _read_observations_from_stdin(self) -> Iterable[Observation]:
        """Yield observations from stdin as JSONL, with optional JSON-array fallback."""
        mode: Literal["jsonl", "json_array", "unknown"] = "unknown"
        array_buffer: list[str] = []
        line_no = 0

        for line in sys.stdin:
            line_no += 1
            raw = line.strip()
            if not raw:
                continue

            if mode == "unknown":
                if raw.startswith("["):
                    mode = "json_array"
                    array_buffer.append(line)
                    continue
                mode = "jsonl"

            if mode == "json_array":
                array_buffer.append(line)
                continue

            # JSONL mode:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSON on stdin line %d", line_no)
                continue

            if isinstance(parsed, list):
                for idx, item in enumerate(parsed):
                    try:
                        yield Observation.from_dict(item)
                    except Exception:
                        logger.warning(
                            "Skipping malformed observation in JSON array on line %d (index %d)",
                            line_no,
                            idx,
                        )
                continue

            try:
                yield Observation.from_dict(parsed)
            except Exception:
                logger.warning("Skipping malformed observation object on stdin line %d", line_no)

        if mode == "json_array" and array_buffer:
            payload = "".join(array_buffer)
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSON array from stdin")
                return

            if not isinstance(parsed, list):
                try:
                    yield Observation.from_dict(parsed)
                except Exception:
                    logger.warning("Skipping malformed observation object from stdin JSON payload")
                return

            for idx, item in enumerate(parsed):
                try:
                    yield Observation.from_dict(item)
                except Exception:
                    logger.warning("Skipping malformed observation in stdin JSON array (index %d)", idx)

    def _read_observations_from_redpanda(self, bootstrap: str, topic: str) -> Iterable[Observation]:
        """Yield observations from a Redpanda/Kafka topic."""
        from kafka import KafkaConsumer

        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=[bootstrap],
            auto_offset_reset="latest",
            enable_auto_commit=True,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )

        for message in consumer:
            yield Observation.from_dict(message.value)

    def _emit_fix(self, fix: PositionFix) -> None:
        """Emit a PositionFix through callbacks/queue and retain a local copy."""
        self.emitted_fixes.append(fix)

        if self.fix_queue is not None:
            if isinstance(self.fix_queue, asyncio.Queue):
                if self._async_queue_loop is not None and self._async_queue_loop.is_running():
                    self._async_queue_loop.call_soon_threadsafe(self.fix_queue.put_nowait, fix)
                else:
                    self.fix_queue.put_nowait(fix)
            else:
                self.fix_queue.put(fix)

        if self.fix_callback is not None:
            callback_result = self.fix_callback(fix)
            if inspect.isawaitable(callback_result):
                raise RuntimeError("Async callback provided to sync process_observation path")

    async def _emit_fix_async(self, fix: PositionFix) -> None:
        """Emit a PositionFix and await async queue/callback paths when needed."""
        self.emitted_fixes.append(fix)

        if self.fix_queue is not None:
            if isinstance(self.fix_queue, asyncio.Queue):
                await self.fix_queue.put(fix)
            else:
                self.fix_queue.put(fix)

        if self.fix_callback is not None:
            callback_result = self.fix_callback(fix)
            if inspect.isawaitable(callback_result):
                await callback_result

    def _emit_mlat_group(self, group: MLATGroup) -> None:
        """Emit an MLATGroup through callback and retain a local copy."""
        self.emitted_mlat_groups.append(group)

        if self.mlat_group_callback is not None:
            self.mlat_group_callback(group)
