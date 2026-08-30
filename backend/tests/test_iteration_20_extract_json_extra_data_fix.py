"""Iteration-20 hotfix — `_extract_json` must return exactly ONE JSON blob.

Bug repro:
    LLM error: Agent technology_detection_agent returned invalid JSON:
    Extra data: line 13 column 2 (char 388)

Root cause: the streaming path sometimes concatenates a "reasoning" JSON
block with the actual answer JSON. The old extractor took
`text[first{ : last}]` and produced malformed concatenated JSON. The new
extractor brace-counts and stops at the first balanced close.
"""

from __future__ import annotations

import json

import pytest

from backend.agents.base import _extract_json


class TestExtractJsonReturnsFirstCompleteObject:
    def test_single_object_unchanged(self):
        out = _extract_json('{"a": 1, "b": "hello"}')
        assert json.loads(out) == {"a": 1, "b": "hello"}

    def test_two_objects_back_to_back_returns_first(self):
        # Simulates the bug: two JSON objects concatenated with a newline.
        text = (
            '{"language": "python", "framework": "fastapi"}\n'
            '{"language": "javascript", "framework": "react"}'
        )
        out = _extract_json(text)
        assert json.loads(out) == {"language": "python", "framework": "fastapi"}

    def test_prose_wrapping_stripped(self):
        text = (
            "Here is my answer:\n"
            '{"tool": "terraform", "cloud": "aws"}\n'
            "Hope that helps!"
        )
        out = _extract_json(text)
        assert json.loads(out) == {"tool": "terraform", "cloud": "aws"}

    def test_markdown_fence_still_works(self):
        text = '```json\n{"stage": "plan"}\n```'
        out = _extract_json(text)
        assert json.loads(out) == {"stage": "plan"}

    def test_markdown_fence_containing_two_objects_returns_first(self):
        text = (
            "```json\n"
            '{"first": true}\n'
            '{"second": true}\n'
            "```"
        )
        out = _extract_json(text)
        assert json.loads(out) == {"first": True}

    def test_nested_objects_are_preserved(self):
        text = '{"a": {"b": {"c": 1}}, "d": [1,2,3]}\n{"tail": true}'
        out = _extract_json(text)
        assert json.loads(out) == {"a": {"b": {"c": 1}}, "d": [1, 2, 3]}

    def test_strings_containing_braces_are_ignored(self):
        # A `}` inside a string literal must NOT close the top-level object.
        text = '{"message": "hi { there } friend", "n": 7}\n{"extra": 1}'
        out = _extract_json(text)
        loaded = json.loads(out)
        assert loaded == {"message": "hi { there } friend", "n": 7}

    def test_escaped_quotes_inside_string_do_not_confuse_the_walker(self):
        text = r'{"quote": "he said \"hi\" and left"}' + "\n" + '{"tail": 1}'
        out = _extract_json(text)
        assert json.loads(out) == {"quote": 'he said "hi" and left'}

    def test_no_json_returns_original_text(self):
        # If there's no `{`, we return the input as-is and let the caller
        # surface a clear JSONDecodeError.
        assert _extract_json("this is plain text") == "this is plain text"

    def test_truncated_object_returns_best_effort(self):
        # LLM was cut off mid-response. We return the partial JSON — the
        # caller (base.py) will raise the usual "invalid JSON" error which
        # is more informative than crashing here.
        text = '{"a": 1, "b": "unfinished'
        out = _extract_json(text)
        # Best effort — starts at the `{`. Not valid JSON but not crashed.
        assert out.startswith("{")
