import asyncio
import io
import json
import sys
from pathlib import Path

import pytest

from mlat.models import Observation
from mlat.pipeline import Pipeline


def test_stdin_reader_skips_malformed_json_and_keeps_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = "\n".join(
        [
            "not-json-at-all",
            json.dumps(
                {
                    "sensor_id": 870800659,
                    "sensor_pk": "pk",
                    "lat": 50.12993,
                    "lon": -5.5137,
                    "alt_m": 56.3,
                    "total_nanos": 48332506707868,
                    "hex": "8d398602589b84ce7302e35bbd70",
                    "df": 17,
                    "hex_key": "8d398602589b84ce7302e35bbd70",
                }
            ),
        ]
    )

    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    pipeline = Pipeline(source="stdin")

    observations = list(pipeline._read_observations_from_stdin())
    assert len(observations) == 1
    assert observations[0].sensor_id == 870800659


@pytest.mark.anyio
async def test_threaded_pipeline_can_emit_to_asyncio_queue_without_dropping_updates() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "sample_observations.json"
    rows = json.loads(fixture_path.read_text(encoding="utf-8"))
    observations = [Observation.from_dict(row) for row in rows]

    fix_queue: asyncio.Queue = asyncio.Queue()
    pipeline = Pipeline(source="stdin", fix_queue=fix_queue)

    await asyncio.to_thread(pipeline.process_observations, observations)

    fix = await asyncio.wait_for(fix_queue.get(), timeout=2.0)
    assert fix.method == "CPR"
    assert isinstance(fix.icao, str)
    assert fix.icao != ""

