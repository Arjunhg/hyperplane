"""Generate a realistic multi-aircraft fixture with distinct positions.

Each aircraft gets a unique ICAO, a unique lat/lon, and a valid even+odd
CPR frame pair so the pipeline can decode them.  We use pyModeS encoding
helpers to build genuine ADS-B airborne-position messages (DF17, TC=11).

Usage:
    cd python
    uv run python tests/fixtures/generate_multi_aircraft.py > tests/fixtures/sample_observations.json
"""

from __future__ import annotations

import json
import math
from typing import cast

import pyModeS as pms
from pyModeS import common as pms_common

# 20 aircraft spread across Western Europe / North Atlantic
AIRCRAFT = [
    {"icao": "40621D", "lat": 52.2658, "lon": 3.9389, "alt_ft": 38000},    # North Sea
    {"icao": "40621E", "lat": 51.4700, "lon": -0.4543, "alt_ft": 36000},   # London
    {"icao": "40621F", "lat": 48.8566, "lon": 2.3522, "alt_ft": 35000},    # Paris
    {"icao": "406220", "lat": 50.0379, "lon": 4.9000, "alt_ft": 37000},    # West Germany
    {"icao": "406221", "lat": 52.3105, "lon": 4.7683, "alt_ft": 33000},    # Amsterdam
    {"icao": "406222", "lat": 46.6034, "lon": 1.8883, "alt_ft": 39000},    # Central France
    {"icao": "406223", "lat": 45.7640, "lon": 4.8357, "alt_ft": 34000},    # Lyon
    {"icao": "406224", "lat": 47.2184, "lon": -1.5536, "alt_ft": 31000},   # Nantes
    {"icao": "406225", "lat": 48.3904, "lon": -4.4861, "alt_ft": 36000},   # Brest
    {"icao": "406226", "lat": 49.1829, "lon": -0.3707, "alt_ft": 40000},   # Caen
    {"icao": "406227", "lat": 50.6292, "lon": 3.0573, "alt_ft": 32000},    # Lille
    {"icao": "406228", "lat": 53.4808, "lon": -2.2426, "alt_ft": 35000},   # Manchester
    {"icao": "406229", "lat": 55.9533, "lon": -3.1883, "alt_ft": 28000},   # Edinburgh
    {"icao": "40622A", "lat": 57.1497, "lon": -2.0943, "alt_ft": 30000},   # Aberdeen
    {"icao": "40622B", "lat": 58.9847, "lon": -2.9598, "alt_ft": 25000},   # Orkney
    {"icao": "40622C", "lat": 54.5973, "lon": -5.9301, "alt_ft": 41000},   # Belfast
    {"icao": "40622D", "lat": 51.8985, "lon": -8.4756, "alt_ft": 38000},   # Cork
    {"icao": "40622E", "lat": 53.3498, "lon": -6.2603, "alt_ft": 27000},   # Dublin
    {"icao": "40622F", "lat": 49.4544, "lon": -2.5295, "alt_ft": 36000},   # Channel Islands
    {"icao": "406230", "lat": 50.1109, "lon": -5.5275, "alt_ft": 34000},   # Cornwall
]


def _encode_cpr_pair(
    icao_hex: str,
    lat: float,
    lon: float,
    alt_ft: int,
) -> tuple[str, str]:
    """Encode an even/odd CPR airborne-position pair.

    Some pyModeS builds do not ship an encoder module, so we try it when
    present and otherwise fall back to our local manual encoder.
    """
    encoder = getattr(pms, "encoder", None)
    if encoder is not None:
        airborne_position = getattr(encoder, "airborne_position", None)
        if callable(airborne_position):
            even_msg = cast(str, airborne_position(icao_hex, lat, lon, alt_ft, 11, 0))
            odd_msg = cast(str, airborne_position(icao_hex, lat, lon, alt_ft, 11, 1))
            return even_msg, odd_msg

    return _build_cpr_manually(icao_hex, lat, lon, alt_ft)


def _build_cpr_manually(
    icao_hex: str,
    lat: float,
    lon: float,
    alt_ft: int,
) -> tuple[str, str]:
    """Manual CPR encoding as fallback when pyModeS encoder isn't available."""

    def _nl(lat_deg: float) -> int:
        return int(pms_common.cprNL(lat_deg))

    def _encode_alt(alt_ft: int) -> int:
        """Encode altitude in 25-ft increments (Q-bit encoding)."""
        n = round((alt_ft + 1000) / 25)
        # 12-bit altitude code with Q-bit at position 4 (bit index from right)
        top7 = (n >> 4) & 0x7F
        bot4 = n & 0x0F
        return (top7 << 5) | (1 << 4) | bot4

    def _cpr_encode(lat: float, lon: float, parity: int) -> tuple[int, int]:
        dlat = 360.0 / (60 - parity)
        yz = math.floor((2**17) * ((lat % dlat) / dlat))
        rlat = dlat * (math.floor(lat / dlat) + (yz / 2**17))
        nl_val = _nl(rlat)
        ni = max(nl_val - parity, 1)
        dlon = 360.0 / ni
        xz = math.floor((2**17) * ((lon % dlon) / dlon))
        return yz, xz

    def _build_msg(icao_hex: str, alt_ft: int, parity: int, lat: float, lon: float) -> str:
        # DF=17 (5 bits) + CA=5 (3 bits) = 0x8D
        df_ca = 0x8D

        icao_int = int(icao_hex, 16)

        # Type Code=11 (5 bits) + SS=0 (2 bits) + SAF/NICsb=0 (1 bit) = first byte of ME
        tc = 11
        alt_code = _encode_alt(alt_ft)  # 12 bits
        yz, xz = _cpr_encode(lat, lon, parity)

        # ME field (56 bits = 7 bytes):
        # TC(5) SS(2) SAF(1) | ALT(12) | T(1) F(1=parity) CPR_LAT(17) CPR_LON(17)
        me = 0
        me |= (tc & 0x1F) << 51
        # SS=0, SAF=0 → next 3 bits are 0
        me |= (alt_code & 0xFFF) << 36
        # T=0 (UTC sync) at bit 35, F (odd/even) at bit 34.
        me |= (parity & 0x1) << 34
        me |= (yz & 0x1FFFF) << 17
        me |= (xz & 0x1FFFF)

        # Assemble without CRC first (88 bits)
        msg_no_crc = (df_ca << 80) | (icao_int << 56) | me

        # Calculate CRC-24 (using pyModeS or manual)
        msg_hex_no_crc = f"{msg_no_crc:022x}"
        try:
            crc = pms_common.crc(msg_hex_no_crc + "000000", encode=True)
            crc_int = int(crc, 16) if isinstance(crc, str) else crc
        except Exception:
            crc_int = 0

        full_msg = (msg_no_crc << 24) | (crc_int & 0xFFFFFF)
        return f"{full_msg:028x}"

    even_msg = _build_msg(icao_hex, alt_ft, 0, lat, lon)
    odd_msg  = _build_msg(icao_hex, alt_ft, 1, lat, lon)
    return even_msg, odd_msg


def main() -> None:
    observations: list[dict] = []
    base_nanos = 100_000_000_000  # 100 seconds past midnight

    for i, ac in enumerate(AIRCRAFT):
        t_even = base_nanos + i * 10_000_000_000  # 10s apart per aircraft
        t_odd  = t_even + 4_000_000_000           # odd frame 4s after even

        even_hex, odd_hex = _encode_cpr_pair(ac["icao"], ac["lat"], ac["lon"], ac["alt_ft"])

        observations.append({
            "sensor_id": 1,
            "sensor_pk": "",
            "lat": 50.12993,
            "lon": -5.5137,
            "alt_m": 56.3,
            "total_nanos": t_even,
            "hex": even_hex,
            "df": 17,
            "hex_key": even_hex,
        })
        observations.append({
            "sensor_id": 2,
            "sensor_pk": "",
            "lat": 50.09916,
            "lon": -5.55674,
            "alt_m": 153.8,
            "total_nanos": t_odd,
            "hex": odd_hex,
            "df": 17,
            "hex_key": odd_hex,
        })

    print(json.dumps(observations, indent=2))


if __name__ == "__main__":
    main()
