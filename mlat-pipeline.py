#!/usr/bin/env python3
"""

mlat-pipeline.py — remains in repo root. It's your working prototype. When you implement Phase 3, the clean version goes into python/mlat/pipeline.py.
mlat_pipeline.py — Reads Mode-S observations from the Go buyer (via stdin pipe
or a log file tail), correlates messages seen by multiple sensors, and runs
the MLAT solver to estimate aircraft positions.

Usage on EC2:
  # Pipe buyer output directly into this script:
  sudo journalctl -u mlat-buyer -f | python3 mlat_pipeline.py

  # Or run both together:
  ./main_app --port=61336 --mode=peer --buyer-or-seller=buyer \
    --list-of-sellers-source=env --envFile=.buyer-env 2>&1 | python3 mlat_pipeline.py
"""

import sys
import re
import json
import time
import math
import numpy as np
from collections import defaultdict
from scipy.optimize import least_squares
from datetime import datetime

# ── Constants ────────────────────────────────────────────────────────────────
C = 299_792_458.0          # Speed of light (m/s)
TIME_WINDOW_NS = 2_000_000_000  # 2 seconds — max spread between same-message receipts
MIN_SENSORS = 3            # Minimum sensors to attempt MLAT (3 for 2D+alt, 4 for full 3D)
MAX_GDOP = 15.0            # Reject solutions with poor geometry
EARTH_A = 6_378_137.0      # WGS-84 semi-major axis (m)
EARTH_E2 = 0.00669437999014  # WGS-84 eccentricity squared

# ── pyModeS (optional but recommended) ──────────────────────────────────────
try:
    import pyModeS as pms
    HAS_PYMODES = True
    print("[INFO] pyModeS loaded — will decode ICAO addresses and message types")
except ImportError:
    HAS_PYMODES = False
    print("[WARN] pyModeS not installed. Run: pip install pyModeS")
    print("[WARN] Continuing without message decoding — correlation by hex only")

# ── Location overrides (load from file) ──────────────────────────────────────
def load_location_overrides(path="location-override.json"):
    """
    Load the true sensor positions from the override file.
    Returns a dict keyed by public_key (str) → (lat, lon, alt).
    Note: The Go buyer uses sensorID (int64). We key by both here
    and match by the sensor position lat/lon as a fallback.
    """
    try:
        with open(path) as f:
            data = json.load(f)
        overrides = {}
        for entry in data:
            overrides[entry["public_key"]] = (
                entry["lat"], entry["lon"], entry["alt"]
            )
        print(f"[INFO] Loaded {len(overrides)} location overrides")
        return overrides
    except FileNotFoundError:
        print(f"[WARN] {path} not found — using raw sensor positions (less accurate)")
        return {}

# ── Coordinate conversions ────────────────────────────────────────────────────
def geodetic_to_ecef(lat_deg, lon_deg, alt_m):
    """Convert geodetic (lat/lon/alt) to ECEF Cartesian (x, y, z) in meters."""
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    N = EARTH_A / math.sqrt(1 - EARTH_E2 * math.sin(lat) ** 2)
    x = (N + alt_m) * math.cos(lat) * math.cos(lon)
    y = (N + alt_m) * math.cos(lat) * math.sin(lon)
    z = (N * (1 - EARTH_E2) + alt_m) * math.sin(lat)
    return np.array([x, y, z])

def ecef_to_geodetic(x, y, z):
    """Convert ECEF (x, y, z) back to geodetic (lat_deg, lon_deg, alt_m)."""
    lon = math.degrees(math.atan2(y, x))
    p = math.sqrt(x**2 + y**2)
    lat = math.atan2(z, p * (1 - EARTH_E2))
    for _ in range(5):  # Bowring iteration
        N = EARTH_A / math.sqrt(1 - EARTH_E2 * math.sin(lat) ** 2)
        lat = math.atan2(z + EARTH_E2 * N * math.sin(lat), p)
    N = EARTH_A / math.sqrt(1 - EARTH_E2 * math.sin(lat) ** 2)
    alt = p / math.cos(lat) - N if abs(math.cos(lat)) > 1e-10 else abs(z) - EARTH_A * math.sqrt(1 - EARTH_E2)
    return math.degrees(lat), lon, alt

# ── GDOP computation ──────────────────────────────────────────────────────────
def compute_gdop(aircraft_ecef, sensor_ecef_list):
    """Geometric Dilution of Precision. Lower = better. >15 = unreliable."""
    ref = sensor_ecef_list[0]
    rows = []
    for s in sensor_ecef_list[1:]:
        d_ref = np.linalg.norm(aircraft_ecef - ref)
        d_s   = np.linalg.norm(aircraft_ecef - s)
        if d_ref < 1 or d_s < 1:
            return float('inf')
        rows.append((aircraft_ecef - s) / d_s - (aircraft_ecef - ref) / d_ref)
    G = np.array(rows)
    try:
        return float(np.sqrt(np.trace(np.linalg.inv(G.T @ G))))
    except np.linalg.LinAlgError:
        return float('inf')

# ── MLAT solver ───────────────────────────────────────────────────────────────
def solve_mlat(sensor_positions_ecef, tdoa_seconds, initial_guess_ecef):
    """
    Solve for aircraft position using Levenberg-Marquardt on TDOA residuals.
    Returns (lat, lon, alt_m) or None if solution quality is poor.
    """
    sensors = [np.array(s) for s in sensor_positions_ecef]
    measured = np.array(tdoa_seconds)
    ref = sensors[0]

    def residuals(pos):
        R0 = np.linalg.norm(pos - ref)
        res = []
        for s, meas in zip(sensors[1:], measured):
            Ri = np.linalg.norm(pos - s)
            res.append((Ri - R0) / C - meas)
        return np.array(res)

    try:
        result = least_squares(
            residuals,
            x0=np.array(initial_guess_ecef, dtype=float),
            method='lm',
            max_nfev=200,
            ftol=1e-12,
            xtol=1e-12,
        )
    except Exception as e:
        return None

    # Reject poor solutions
    if result.cost > 1e-4:
        return None

    aircraft_ecef = result.x
    gdop = compute_gdop(aircraft_ecef, sensors)
    if gdop > MAX_GDOP:
        return None

    lat, lon, alt = ecef_to_geodetic(*aircraft_ecef)

    # Sanity check: altitude must be reasonable (0 to 45,000m = ~150,000ft)
    if not (-500 < alt < 45_000):
        return None

    # Sanity check: position must be near the UK (sensors are in Cornwall)
    if not (45 < lat < 62 and -15 < lon < 5):
        return None

    return lat, lon, alt, gdop

# ── Message parser ─────────────────────────────────────────────────────────────
class MessageParser:
    """Parses the formatted output from the Go buyer's main.go."""

    # Regex patterns matching the Go buyer's print format
    RE_SENSOR_ID  = re.compile(r'Sensor ID:\s*(\d+)')
    RE_POSITION   = re.compile(r'Sensor Position: Lat=([\d.\-]+), Lon=([\d.\-]+), Alt=([\d.\-]+)')
    RE_TIMESTAMP  = re.compile(r'Timestamp: SecondsSinceMidnight=(\d+), Nanoseconds=(\d+)')
    RE_RAW_HEX    = re.compile(r'Raw ModeS \(hex\):\s*([0-9a-fA-F]+)')

    def __init__(self):
        self.current = {}

    def feed_line(self, line):
        """
        Feed one line of buyer output. Returns a complete Observation dict
        when a full message block has been parsed, otherwise None.
        """
        line = line.strip()

        if '=== ModeS Message' in line:
            self.current = {}
            return None

        m = self.RE_SENSOR_ID.search(line)
        if m:
            self.current['sensor_id'] = int(m.group(1))
            return None

        m = self.RE_POSITION.search(line)
        if m:
            self.current['lat'] = float(m.group(1))
            self.current['lon'] = float(m.group(2))
            self.current['alt'] = float(m.group(3))
            return None

        m = self.RE_TIMESTAMP.search(line)
        if m:
            secs = int(m.group(1))
            nanos = int(m.group(2))
            self.current['total_nanos'] = secs * 1_000_000_000 + nanos
            return None

        m = self.RE_RAW_HEX.search(line)
        if m:
            self.current['hex'] = m.group(1).lower()
            # Complete observation — return it
            obs = dict(self.current)
            self.current = {}

            # Decode with pyModeS if available
            if HAS_PYMODES and len(obs.get('hex', '')) >= 14:
                try:
                    obs['icao'] = pms.icao(obs['hex'])
                    obs['df'] = pms.df(obs['hex'])
                    # Extract altitude if available (DF17 TC9-18, DF4, DF20)
                    df = obs['df']
                    if df == 17:
                        tc = pms.adsb.typecode(obs['hex'])
                        obs['typecode'] = tc
                        if 9 <= tc <= 18:
                            obs['alt_ft'] = pms.adsb.altitude(obs['hex'])
                    elif df in (4, 20):
                        obs['alt_ft'] = pms.common.altcode(obs['hex'])
                except Exception:
                    pass
            elif len(obs.get('hex', '')) >= 6:
                # Even without pyModeS, extract ICAO from first 3 bytes (DF17 only)
                # DF17 starts with 8D, first byte high nibble = DF
                first_byte = int(obs['hex'][:2], 16)
                df = (first_byte >> 3) & 0x1F
                obs['df'] = df
                if df == 17 and len(obs['hex']) >= 8:
                    obs['icao'] = obs['hex'][2:8]

            if 'sensor_id' in obs and 'total_nanos' in obs and 'hex' in obs:
                return obs

        return None

# ── Correlation buffer ────────────────────────────────────────────────────────
class CorrelationBuffer:
    """Groups observations of the same Mode-S message from multiple sensors."""

    def __init__(self):
        # hex_key → list of observations
        self.groups = defaultdict(list)
        self.last_cleanup = time.time()

    def add(self, obs):
        """Add observation. Returns a MLAT-ready group if one is complete."""
        key = obs['hex']
        group = self.groups[key]
        group.append(obs)

        # Periodic cleanup of stale groups
        now = time.time()
        if now - self.last_cleanup > 5.0:
            self._cleanup()
            self.last_cleanup = now

        # Check if group is ready
        if len(group) >= MIN_SENSORS:
            timestamps = [o['total_nanos'] for o in group]
            if max(timestamps) - min(timestamps) < TIME_WINDOW_NS:
                ready = list(group)
                del self.groups[key]
                return ready

        return None

    def _cleanup(self):
        """Remove groups older than TIME_WINDOW_NS to prevent memory leak."""
        now_ns = int(time.time() * 1e9)
        stale = [
            k for k, g in self.groups.items()
            if g and now_ns - g[0]['total_nanos'] > TIME_WINDOW_NS * 2
        ]
        for k in stale:
            del self.groups[k]

# ── Aircraft state tracker ─────────────────────────────────────────────────────
class AircraftTracker:
    """Keeps the most recent position for each ICAO address (for initial guesses)."""

    def __init__(self):
        self.tracks = {}  # icao → {'lat', 'lon', 'alt', 'last_seen'}
        # Default initial guess: centroid of the sensor network (Cornwall area)
        # at a typical cruise altitude of 10,000m
        self.default_ecef = geodetic_to_ecef(50.1, -5.6, 10_000)

    def get_initial_guess(self, icao=None):
        if icao and icao in self.tracks:
            t = self.tracks[icao]
            return geodetic_to_ecef(t['lat'], t['lon'], t['alt'])
        return self.default_ecef.copy()

    def update(self, icao, lat, lon, alt):
        self.tracks[icao] = {'lat': lat, 'lon': lon, 'alt': alt, 'last_seen': time.time()}

# ── Main pipeline ──────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  MLAT Pipeline — Cornwall/Penzance Sensor Network")
    print("=" * 60)
    print(f"  Min sensors for MLAT : {MIN_SENSORS}")
    print(f"  Time window          : {TIME_WINDOW_NS/1e9:.1f}s")
    print(f"  Max GDOP             : {MAX_GDOP}")
    print()

    overrides = load_location_overrides("location-override.json")
    parser = MessageParser()
    buffer = CorrelationBuffer()
    tracker = AircraftTracker()

    # Stats
    obs_count = 0
    group_count = 0
    solve_count = 0
    fail_count = 0
    start_time = time.time()

    print("[INFO] Reading from stdin (pipe the Go buyer output here)...")
    print("[INFO] Waiting for messages...\n")

    try:
        for line in sys.stdin:
            obs = parser.feed_line(line)
            if obs is None:
                continue

            obs_count += 1

            # Apply location override based on nearest known sensor
            # (matching by approximate lat/lon since we don't have public_key directly)
            # The Go buyer outputs the masked position — we detect by proximity
            # For a production system you'd pass public_key through the stream
            # For now, snap to nearest override within 5km
            raw_lat = obs.get('lat', 0)
            raw_lon = obs.get('lon', 0)
            best_match = None
            best_dist = float('inf')
            for pk, (true_lat, true_lon, true_alt) in overrides.items():
                dist = math.hypot(true_lat - raw_lat, true_lon - raw_lon)
                if dist < best_dist:
                    best_dist = dist
                    best_match = (true_lat, true_lon, true_alt)

            if best_match and best_dist < 0.1:  # Within ~7km
                obs['lat'], obs['lon'], obs['alt'] = best_match

            # Try to correlate
            group = buffer.add(obs)
            if group is None:
                continue

            group_count += 1
            icao = None

            # Get ICAO from any observation in the group that has it
            for o in group:
                if o.get('icao'):
                    icao = o['icao']
                    break

            # Sort by timestamp — earliest is reference sensor
            group.sort(key=lambda o: o['total_nanos'])
            ref = group[0]

            # Build sensor positions in ECEF
            sensor_positions_ecef = [
                geodetic_to_ecef(o['lat'], o['lon'], o['alt'])
                for o in group
            ]

            # Build TDOA measurements (seconds)
            tdoa_seconds = [
                (o['total_nanos'] - ref['total_nanos']) * 1e-9
                for o in group[1:]
            ]

            # Get initial guess
            initial_guess = tracker.get_initial_guess(icao)

            # Solve
            result = solve_mlat(sensor_positions_ecef, tdoa_seconds, initial_guess)

            if result is None:
                fail_count += 1
                continue

            lat, lon, alt_m, gdop = result
            solve_count += 1

            # Update tracker for future initial guesses
            if icao:
                tracker.update(icao, lat, lon, alt_m)

            # Get altitude in feet if we have it from the message
            alt_ft_from_msg = group[0].get('alt_ft', '')
            alt_ft_mlat = alt_m * 3.28084

            # ── Print result ──────────────────────────────────────────────
            elapsed = time.time() - start_time
            print(f"✈  MLAT FIX  [{datetime.utcnow().strftime('%H:%M:%S')} UTC]")
            print(f"   ICAO    : {icao or 'unknown'}")
            print(f"   Lat/Lon : {lat:.5f}, {lon:.5f}")
            print(f"   Alt     : {alt_ft_mlat:,.0f} ft (MLAT)"
                  + (f"  |  {alt_ft_from_msg:,} ft (Mode-S)" if alt_ft_from_msg else ""))
            print(f"   GDOP    : {gdop:.2f}  |  Sensors: {len(group)}")
            print(f"   Stats   : {solve_count} fixes / {group_count} groups / {obs_count} obs  [{elapsed:.0f}s]")
            print()

    except KeyboardInterrupt:
        print(f"\n[INFO] Stopped. Total: {obs_count} obs, {group_count} groups, "
              f"{solve_count} MLAT fixes, {fail_count} failed solves")

if __name__ == "__main__":
    main()