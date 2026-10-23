"""Generated scripts must match their requested runtime and image density."""
from stickman.scriptx.schema import validate_pacing
from stickman.pipeline import _check_generated_voice_duration
import json
import pytest


def script(words_per_concept: int, concepts: int) -> dict:
    chunks = [" ".join(["word"] * words_per_concept) for _ in range(concepts)]
    return {"scenes": [{"voiceover": " ".join(chunks),
                        "concepts": [{"id": f"c{i}", "narration_span": chunk}
                                     for i, chunk in enumerate(chunks)]}]}


def test_six_minute_script_requires_enough_words_and_images():
    assert validate_pacing(script(24, 33), 6) == []
    assert any("Narration" in error for error in validate_pacing(script(25, 8), 6))
    assert any("images" in error for error in validate_pacing(script(50, 18), 6))
    assert any("narration_span" in error for error in validate_pacing(script(50, 18), 6))


def test_measured_voice_must_fill_target_before_images(tmp_path):
    voice = tmp_path / "voice"
    voice.mkdir()
    (voice / "meta.json").write_text(json.dumps({"s01": {"duration_s": 270}}))
    cfg = {"project": {"target_minutes": 6}, "script": {"provider": "codex-oauth"}}
    with pytest.raises(RuntimeError, match="Measured narration"):
        _check_generated_voice_duration(tmp_path, cfg)
    (voice / "meta.json").write_text(json.dumps({"s01": {"duration_s": 360}}))
    _check_generated_voice_duration(tmp_path, cfg)
