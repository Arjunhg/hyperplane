"""Message routing for ADS-B and non-ADS-B observations."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from .models import Observation


class MessageClass(Enum):
    """Top-level message categories used by the pipeline."""

    ADSB_AIRBORNE_POSITION = "ADSB_AIRBORNE_POSITION"
    ADSB_SURFACE_POSITION = "ADSB_SURFACE_POSITION"
    ADSB_VELOCITY = "ADSB_VELOCITY"
    ADSB_IDENTIFICATION = "ADSB_IDENTIFICATION"
    ADSB_OTHER = "ADSB_OTHER"
    NON_ADSB = "NON_ADSB"


def extract_type_code(hex_str: str) -> Optional[int]:
    """Extract ADS-B type code from a DF17 hex payload."""
    payload = (hex_str or "").strip().lower()
    if len(payload) < 10:
        return None

    try:
        return (int(payload[8:10], 16) >> 3) & 0x1F
    except ValueError:
        return None


def classify_message(obs: Observation) -> MessageClass:
    """Classify an observation according to the Phase 3 decision tree."""
    if obs.df != 17:
        return MessageClass.NON_ADSB

    tc = extract_type_code(obs.hex)
    if tc is None:
        return MessageClass.ADSB_OTHER

    if 9 <= tc <= 18:
        return MessageClass.ADSB_AIRBORNE_POSITION
    if 5 <= tc <= 8:
        return MessageClass.ADSB_SURFACE_POSITION
    if tc == 19:
        return MessageClass.ADSB_VELOCITY
    if 1 <= tc <= 4:
        return MessageClass.ADSB_IDENTIFICATION
    return MessageClass.ADSB_OTHER


def extract_icao(hex_str: str, df: int) -> Optional[str]:
    """Extract ICAO (6-hex chars) for DFs that carry an address."""
    if df not in {11, 17, 18, 20, 21}:
        return None

    payload = (hex_str or "").strip().lower()
    if len(payload) < 8:
        return None

    icao = payload[2:8]
    if len(icao) != 6:
        return None
    return icao
