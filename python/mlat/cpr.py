"""CPR frame buffering and decoding utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pyModeS as pms

from .models import CPRFrame, Observation, PositionFix

MAX_FRAME_AGE_NS = 10_000_000_000


@dataclass
class _StoredFrame:
    """CPR frame with source message payload for decoding."""

    frame: CPRFrame
    message_hex: str


class CPRDecoder:
    """Buffer even/odd CPR frames and decode positions when possible."""

    def __init__(self, coverage_bounds: tuple[float, float, float, float] = (45.0, 62.0, -15.0, 5.0)) -> None:
        self._coverage_bounds = coverage_bounds
        self._buffer: dict[str, dict[int, _StoredFrame]] = {}

    def store_cpr_frame(self, icao: str, obs: Observation, tc: int) -> None:
        """Store the latest CPR frame for ICAO/parity."""
        payload = (obs.hex or "").strip().lower()
        if not icao or not payload:
            return

        try:
            parity = int(pms.adsb.oe_flag(payload))
        except Exception:
            return

        lat_cpr, lon_cpr = _extract_cpr_lat_lon(payload)
        alt_ft_raw = _safe_altitude(payload)

        stored = _StoredFrame(
            frame=CPRFrame(
                icao=icao.lower(),
                parity=parity,
                lat_cpr=lat_cpr,
                lon_cpr=lon_cpr,
                tc=tc,
                total_nanos=obs.total_nanos,
                alt_ft=alt_ft_raw,
            ),
            message_hex=payload,
        )

        aircraft_frames = self._buffer.setdefault(icao.lower(), {})
        aircraft_frames[parity] = stored

    def try_decode_position(self, icao: str, ref_lat: float, ref_lon: float) -> Optional[PositionFix]:
        """Try decoding a CPR position if recent even/odd frames are available."""
        frames = self._buffer.get(icao.lower())
        if not frames:
            return None

        even = frames.get(0)
        odd = frames.get(1)
        if even is None or odd is None:
            return None

        dt_ns = abs(even.frame.total_nanos - odd.frame.total_nanos)
        if dt_ns > MAX_FRAME_AGE_NS:
            return None

        even_surface = 5 <= even.frame.tc <= 8
        odd_surface = 5 <= odd.frame.tc <= 8
        even_airborne = 9 <= even.frame.tc <= 18 or 20 <= even.frame.tc <= 22
        odd_airborne = 9 <= odd.frame.tc <= 18 or 20 <= odd.frame.tc <= 22

        if even_surface and odd_surface:
            latest = even if even.frame.total_nanos >= odd.frame.total_nanos else odd
            try:
                lat_lon = pms.adsb.position_with_ref(latest.message_hex, ref_lat, ref_lon)
            except Exception:
                return None
        elif even_airborne and odd_airborne:
            t_even = even.frame.total_nanos / 1_000_000_000.0
            t_odd = odd.frame.total_nanos / 1_000_000_000.0
            try:
                lat_lon = pms.adsb.position(even.message_hex, odd.message_hex, t_even, t_odd, ref_lat, ref_lon)
            except Exception:
                return None
        else:
            return None

        if lat_lon is None:
            return None

        lat, lon = lat_lon
        if lat is None or lon is None:
            return None

        if not self._is_plausible(lat, lon):
            return None

        altitude_ft_raw = _safe_altitude(even.message_hex)
        if altitude_ft_raw is None:
            altitude_ft_raw = _safe_altitude(odd.message_hex)

        altitude_ft = float(altitude_ft_raw) if altitude_ft_raw is not None else 0.0
        altitude_m = altitude_ft * 0.3048
        latest_nanos = max(even.frame.total_nanos, odd.frame.total_nanos)

        return PositionFix(
            icao=icao.lower(),
            lat=float(lat),
            lon=float(lon),
            alt_m=float(altitude_m),
            alt_ft=float(altitude_ft),
            method="CPR",
            gdop=None,
            sensor_count=None,
            timestamp_utc=_to_utc_iso_from_midnight_nanos(latest_nanos),
            callsign=None,
        )

    def _is_plausible(self, lat: float, lon: float) -> bool:
        min_lat, max_lat, min_lon, max_lon = self._coverage_bounds
        return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def _safe_altitude(message_hex: str) -> Optional[int]:
    try:
        alt = pms.adsb.altitude(message_hex)
    except Exception:
        return None

    if alt is None:
        return None

    try:
        return int(alt)
    except (TypeError, ValueError):
        return None


def _extract_cpr_lat_lon(message_hex: str) -> tuple[int, int]:
    """Extract raw 17-bit CPR latitude/longitude fields from a DF17 payload."""
    bits = len(message_hex) * 4
    value = int(message_hex, 16)

    lat = _extract_bits(value, bits, 54, 70)
    lon = _extract_bits(value, bits, 71, 87)
    return lat, lon


def _extract_bits(value: int, total_bits: int, start_bit: int, end_bit: int) -> int:
    """Extract inclusive bit range using 1-based bit indexing from MSB."""
    width = end_bit - start_bit + 1
    shift = total_bits - end_bit
    mask = (1 << width) - 1
    return (value >> shift) & mask


def _to_utc_iso_from_midnight_nanos(total_nanos: int) -> str:
    """Convert nanoseconds since UTC midnight to an ISO-8601 timestamp."""
    utc_now = datetime.now(timezone.utc)
    midnight = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
    ts = midnight + timedelta(seconds=total_nanos / 1_000_000_000.0)
    return ts.isoformat().replace("+00:00", "Z")


_default_decoder = CPRDecoder()


def store_cpr_frame(icao: str, obs: Observation, tc: int) -> None:
    """Store a CPR frame in the module-level decoder buffer."""
    _default_decoder.store_cpr_frame(icao, obs, tc)


def try_decode_position(icao: str, ref_lat: float, ref_lon: float) -> Optional[PositionFix]:
    """Try decoding a CPR position using the module-level decoder buffer."""
    return _default_decoder.try_decode_position(icao, ref_lat, ref_lon)
