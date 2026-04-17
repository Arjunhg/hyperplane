"""Data models shared across ingestion, decoding, and solving layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Observation:
    """Normalized Mode-S observation from the Go ingestion layer."""

    sensor_id: int
    sensor_pk: str
    lat: float
    lon: float
    alt_m: float
    total_nanos: int
    hex: str
    df: int
    hex_key: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Observation":
        """Create an Observation from a JSON-style dictionary."""
        raw_hex = str(d["hex"])
        return cls(
            sensor_id=int(d["sensor_id"]),
            sensor_pk=str(d.get("sensor_pk", "")),
            lat=float(d["lat"]),
            lon=float(d["lon"]),
            alt_m=float(d["alt_m"]),
            total_nanos=int(d["total_nanos"]),
            hex=raw_hex,
            df=int(d["df"]),
            hex_key=str(d.get("hex_key", raw_hex)),
        )


@dataclass
class CPRFrame:
    """Buffered CPR frame for an aircraft ICAO/parity pair."""

    icao: str
    parity: int
    lat_cpr: int
    lon_cpr: int
    tc: int
    total_nanos: int
    alt_ft: Optional[int] = field(default=None)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CPRFrame":
        """Create a CPRFrame from a JSON-style dictionary."""
        alt_ft = d.get("alt_ft")
        return cls(
            icao=str(d["icao"]),
            parity=int(d["parity"]),
            lat_cpr=int(d["lat_cpr"]),
            lon_cpr=int(d["lon_cpr"]),
            tc=int(d["tc"]),
            total_nanos=int(d["total_nanos"]),
            alt_ft=None if alt_ft is None else int(alt_ft),
        )


@dataclass
class MLATGroup:
    """Correlated observations of the same physical transmission."""

    hex: str
    icao: Optional[str] = field(default=None)
    observations: list[Observation] = field(default_factory=list)
    reference_sensor: int = field(default=0)
    sensor_ecef: list[tuple[float, float, float]] = field(default_factory=list)
    tdoa_seconds: list[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MLATGroup":
        """Create an MLATGroup from a JSON-style dictionary."""
        observations: list[Observation] = []
        for obs in d.get("observations", []):
            if isinstance(obs, Observation):
                observations.append(obs)
            else:
                observations.append(Observation.from_dict(obs))

        sensor_ecef = [tuple(float(v) for v in point) for point in d.get("sensor_ecef", [])]

        return cls(
            hex=str(d["hex"]),
            icao=None if d.get("icao") is None else str(d.get("icao")),
            observations=observations,
            reference_sensor=int(d.get("reference_sensor", 0)),
            sensor_ecef=sensor_ecef,
            tdoa_seconds=[float(v) for v in d.get("tdoa_seconds", [])],
        )


@dataclass
class PositionFix:
    """Resolved aircraft position for downstream tracking and visualization."""

    icao: str
    lat: float
    lon: float
    alt_m: float
    alt_ft: float
    method: str
    gdop: Optional[float] = field(default=None)
    sensor_count: Optional[int] = field(default=None)
    timestamp_utc: str = field(default="")
    callsign: Optional[str] = field(default=None)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PositionFix":
        """Create a PositionFix from a JSON-style dictionary."""
        gdop = d.get("gdop")
        sensor_count = d.get("sensor_count")

        return cls(
            icao=str(d["icao"]),
            lat=float(d["lat"]),
            lon=float(d["lon"]),
            alt_m=float(d["alt_m"]),
            alt_ft=float(d["alt_ft"]),
            method=str(d["method"]),
            gdop=None if gdop is None else float(gdop),
            sensor_count=None if sensor_count is None else int(sensor_count),
            timestamp_utc=str(d["timestamp_utc"]),
            callsign=None if d.get("callsign") is None else str(d.get("callsign")),
        )
