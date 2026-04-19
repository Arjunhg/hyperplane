"""Phase 3 pipeline entry point and message flow orchestration."""

from __future__ import annotations

import json
import sys
from queue import Queue
from typing import Callable, Iterable, Literal, Optional

from .cpr import CPRDecoder
from .models import MLATGroup, Observation, PositionFix
from .router import MessageClass, classify_message, extract_icao, extract_type_code


class AircraftTracker:
    """Lightweight per-aircraft state used for reference positions."""

    def __init__(self) -> None:
        self._latest_fix: dict[str, PositionFix] = {}

    def update(self, fix: PositionFix) -> None:
        """Store the latest fix for an aircraft."""
        self._latest_fix[fix.icao.lower()] = fix

    def get_reference(self, icao: str, fallback_lat: float, fallback_lon: float) -> tuple[float, float]:
        """Get decode reference lat/lon for an ICAO, or fallback if unknown."""
        latest = self._latest_fix.get(icao.lower())
        if latest is None:
            return fallback_lat, fallback_lon
        return latest.lat, latest.lon


class CorrelationBuffer:
    """Simple correlation buffer used until full Phase 4 correlation is implemented."""

    def __init__(self, min_sensors: int = 4, time_window_ns: int = 2_000_000_000) -> None:
        self.min_sensors = min_sensors
        self.time_window_ns = time_window_ns
        self._groups: dict[str, list[Observation]] = {}

    def add(self, obs: Observation) -> Optional[MLATGroup]:
        """Add observation and return a completed group when enough sensors are present."""
        group = self._groups.setdefault(obs.hex, [])

        if group:
            earliest = min(o.total_nanos for o in group)
            if abs(obs.total_nanos - earliest) > self.time_window_ns:
                self._groups[obs.hex] = [obs]
                return None

        # Deduplicate by sensor_id + hex, keep the earlier one.
        replaced = False
        for idx, existing in enumerate(group):
            if existing.sensor_id == obs.sensor_id and existing.hex == obs.hex:
                if obs.total_nanos < existing.total_nanos:
                    group[idx] = obs
                replaced = True
                break

        if not replaced:
            group.append(obs)

        unique_sensors = {o.sensor_id for o in group}
        if len(unique_sensors) < self.min_sensors:
            return None

        ordered = sorted(group, key=lambda item: item.total_nanos)
        reference = ordered[0]
        tdoa = [
            (item.total_nanos - reference.total_nanos) / 1_000_000_000.0
            for item in ordered[1:]
        ]

        icao = None
        for item in ordered:
            maybe_icao = extract_icao(item.hex, item.df)
            if maybe_icao is not None:
                icao = maybe_icao
                break

        completed = MLATGroup(
            hex=obs.hex,
            icao=icao,
            observations=ordered,
            reference_sensor=reference.sensor_id,
            sensor_ecef=[],
            tdoa_seconds=tdoa,
        )

        del self._groups[obs.hex]
        return completed


class Pipeline:
    """Pipeline entry point for processing incoming observations."""

    def __init__(
        self,
        source: Literal["stdin", "redpanda"] = "stdin",
        fix_callback: Optional[Callable[[PositionFix], None]] = None,
        fix_queue: Optional[Queue] = None,
        mlat_group_callback: Optional[Callable[[MLATGroup], None]] = None,
    ) -> None:
        self.source = source
        self.cpr_decoder = CPRDecoder()
        self.correlation_buffer = CorrelationBuffer()
        self.aircraft_tracker = AircraftTracker()

        self.fix_callback = fix_callback
        self.fix_queue = fix_queue
        self.mlat_group_callback = mlat_group_callback

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
            self.process_observation(obs)

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
        """Yield observations from newline-delimited JSON on stdin."""
        for line in sys.stdin:
            raw = line.strip()
            if not raw:
                continue
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    yield Observation.from_dict(item)
            else:
                yield Observation.from_dict(data)

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
            self.fix_queue.put(fix)

        if self.fix_callback is not None:
            self.fix_callback(fix)

    def _emit_mlat_group(self, group: MLATGroup) -> None:
        """Emit an MLATGroup through callback and retain a local copy."""
        self.emitted_mlat_groups.append(group)

        if self.mlat_group_callback is not None:
            self.mlat_group_callback(group)
