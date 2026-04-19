import json
from pathlib import Path

from mlat.models import Observation
from mlat.pipeline import Pipeline


def test_pipeline_integration_produces_cpr_fix_and_mlat_group() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "sample_observations.json"
    rows = json.loads(fixture_path.read_text(encoding="utf-8"))

    observations = [Observation.from_dict(row) for row in rows]

    pipeline = Pipeline(source="stdin")
    pipeline.process_observations(observations)

    assert any(fix.method == "CPR" for fix in pipeline.emitted_fixes)
    assert len(pipeline.emitted_mlat_groups) >= 1
    assert len(pipeline.emitted_mlat_groups[0].observations) >= 4
