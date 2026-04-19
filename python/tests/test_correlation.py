import time

from mlat.correlation import CorrelationBuffer, TIME_WINDOW_NS
from mlat.models import Observation


def _obs(sensor_id: int, total_nanos: int, payload_hex: str = "20000000000000") -> Observation:
    return Observation(
        sensor_id=sensor_id,
        sensor_pk="",
        lat=50.0 + sensor_id * 0.001,
        lon=-5.0 - sensor_id * 0.001,
        alt_m=100.0,
        total_nanos=total_nanos,
        hex=payload_hex,
        df=4,
        hex_key=payload_hex,
    )


def test_correlation_returns_group_for_four_sensors_within_window() -> None:
    buf = CorrelationBuffer(min_sensors=4)

    base = 1_000_000_000_000
    assert buf.add(_obs(1, base + 0)) is None
    assert buf.add(_obs(2, base + 100_000)) is None
    assert buf.add(_obs(3, base + 200_000)) is None

    group = buf.add(_obs(4, base + 300_000))
    assert group is not None
    assert len(group.observations) == 4
    assert [obs.sensor_id for obs in group.observations] == [1, 2, 3, 4]
    assert group.reference_sensor == 1


def test_correlation_rejects_out_of_window_observation() -> None:
    buf = CorrelationBuffer(min_sensors=4)

    base = 2_000_000_000_000
    assert buf.add(_obs(1, base + 0)) is None
    assert buf.add(_obs(2, base + 100_000)) is None
    assert buf.add(_obs(3, base + 200_000)) is None

    # More than 2 seconds from earliest -> rejected.
    assert buf.add(_obs(4, base + TIME_WINDOW_NS + 1)) is None

    # A valid in-window 4th sensor should still complete the group.
    group = buf.add(_obs(4, base + 300_000))
    assert group is not None
    assert len(group.observations) == 4


def test_correlation_deduplicates_by_sensor_and_keeps_earlier() -> None:
    buf = CorrelationBuffer(min_sensors=4)

    base = 3_000_000_000_000
    assert buf.add(_obs(1, base + 100)) is None
    assert buf.add(_obs(1, base + 200)) is None  # duplicate sensor, later -> ignored
    assert buf.add(_obs(2, base + 300)) is None
    assert buf.add(_obs(3, base + 400)) is None

    group = buf.add(_obs(4, base + 500))
    assert group is not None

    sensor1_obs = [obs for obs in group.observations if obs.sensor_id == 1]
    assert len(sensor1_obs) == 1
    assert sensor1_obs[0].total_nanos == base + 100


def test_correlation_periodic_cleanup_purges_stale_groups() -> None:
    buf = CorrelationBuffer(min_sensors=4)

    base_old = 4_000_000_000_000
    assert buf.add(_obs(1, base_old + 0, payload_hex="aaaaaaaaaaaaaa")) is None

    # Force cleanup trigger and add a very new observation on a different hex.
    buf._last_cleanup_monotonic = time.monotonic() - 10.0
    _ = buf.add(_obs(2, base_old + (4 * TIME_WINDOW_NS), payload_hex="bbbbbbbbbbbbbb"))

    assert "aaaaaaaaaaaaaa" not in buf._groups
