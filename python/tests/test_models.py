from mlat.models import CPRFrame, MLATGroup, Observation, PositionFix


def test_observation_from_dict_defaults_hex_key() -> None:
    obs = Observation.from_dict(
        {
            "sensor_id": 870800659,
            "sensor_pk": "pk",
            "lat": 50.12993,
            "lon": -5.5137,
            "alt_m": 56.3,
            "total_nanos": 48332506707868,
            "hex": "8d398602589b84ce7302e35bbd70",
            "df": 17,
        }
    )

    assert obs.sensor_id == 870800659
    assert obs.hex_key == obs.hex


def test_cpr_frame_from_dict_optional_altitude() -> None:
    frame = CPRFrame.from_dict(
        {
            "icao": "398602",
            "parity": 0,
            "lat_cpr": 12345,
            "lon_cpr": 54321,
            "tc": 17,
            "total_nanos": 123456789,
        }
    )
    assert frame.alt_ft is None


def test_mlat_group_from_dict_builds_observations() -> None:
    group = MLATGroup.from_dict(
        {
            "hex": "8d398602589b84ce7302e35bbd70",
            "icao": "398602",
            "reference_sensor": 870800659,
            "observations": [
                {
                    "sensor_id": 870800659,
                    "sensor_pk": "pk",
                    "lat": 50.12993,
                    "lon": -5.5137,
                    "alt_m": 56.3,
                    "total_nanos": 100,
                    "hex": "8d398602589b84ce7302e35bbd70",
                    "df": 17,
                    "hex_key": "8d398602589b84ce7302e35bbd70",
                }
            ],
            "sensor_ecef": [[1.0, 2.0, 3.0]],
            "tdoa_seconds": [0.000001],
        }
    )

    assert group.icao == "398602"
    assert len(group.observations) == 1
    assert isinstance(group.observations[0], Observation)
    assert group.sensor_ecef[0] == (1.0, 2.0, 3.0)


def test_position_fix_from_dict_optional_fields() -> None:
    fix = PositionFix.from_dict(
        {
            "icao": "398602",
            "lat": 51.47234,
            "lon": -0.45123,
            "alt_m": 10973.5,
            "alt_ft": 36000.0,
            "method": "MLAT",
            "timestamp_utc": "2026-04-09T17:42:11.234Z",
        }
    )

    assert fix.gdop is None
    assert fix.sensor_count is None
    assert fix.callsign is None
