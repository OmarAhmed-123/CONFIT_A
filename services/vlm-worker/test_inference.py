"""Offline unit tests for the VLM worker's pure, model-free logic.

Run:  python -m pytest test_inference.py -q   (no GPU / torch required)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from inference import OutputInvalidError, parse_vision_json


def test_parse_plain_object():
    assert parse_vision_json('{"primary_category":"tops","sleeve_length":"short"}') == {
        "primary_category": "tops",
        "sleeve_length": "short",
    }


def test_parse_wrapped_in_code_fence():
    raw = 'Here is the analysis:\n```json\n{"color":"black"}\n```\nThanks.'
    assert parse_vision_json(raw) == {"color": "black"}


def test_parse_with_surrounding_prose():
    raw = 'Sure! {"primary_category":"outerwear","material":"cotton"} hope that helps.'
    assert parse_vision_json(raw)["material"] == "cotton"


def test_parse_escaped_newlines_in_array():
    # qwen-vl-utils encodes literal newlines in prompt text as \n; the model
    # echoes them back, so JSON must still parse.
    raw = '{"prompt_note":"line one\\nline two","color":"red"}'
    assert parse_vision_json(raw) == {"prompt_note": "line one\nline two", "color": "red"}


def test_parse_rejects_non_object_json():
    with pytest.raises(OutputInvalidError):
        parse_vision_json("[1,2,3]")


def test_parse_rejects_empty_or_garbage():
    with pytest.raises(OutputInvalidError):
        parse_vision_json("   ")
    with pytest.raises(OutputInvalidError):
        parse_vision_json("no json here at all")
    with pytest.raises(OutputInvalidError):
        parse_vision_json("{not valid json}x")


def test_parse_rejects_empty_string():
    with pytest.raises(OutputInvalidError):
        parse_vision_json("")


def test_model_spec_pins_apache7b_not_research3b():
    from model_spec import LICENSE, MODEL_REPO_ID, MODEL_REVISION, REQUIRED_FILES

    # The selected model must be the Apache-2.0 7B, NOT the non-commercial 3B.
    assert "7B" in MODEL_REPO_ID
    assert "3B" not in MODEL_REPO_ID
    assert LICENSE == "apache-2.0"  # Apache-2.0 is the HF model-card tag (verified separately)
    assert MODEL_REVISION  # must be pinned (never 'main'/None)
    assert len(REQUIRED_FILES) >= 14
    # The HF repo ships NO LICENSE file; REQUIRED_FILES is exactly what
    # from_pretrained + the processor need (the license is the model-card tag).
    assert "LICENSE" not in REQUIRED_FILES
    assert "model-00001-of-00005.safetensors" in REQUIRED_FILES
    assert "model.safetensors.index.json" in REQUIRED_FILES
