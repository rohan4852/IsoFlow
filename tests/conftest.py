"""Shared test fixtures: deterministic fake Gemini models.

No test in this suite makes a live Gemini call.  The fake models return
pre-authored JSON payloads keyed by control id, so the real validation
and adjudication code paths are exercised end to end.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModel:
    """Returns a canned JSON payload per control id.

    ``payloads`` maps control id -> dict (single-control prompt) or, for
    batch prompts, the same mapping is used to build a JSON array in the
    order the control ids appear in the prompt.
    """

    def __init__(self, payloads, fail_on=None, rate_limit_on_first=False):
        self.payloads = payloads
        self.fail_on = set(fail_on or [])
        self.rate_limit_on_first = rate_limit_on_first
        self.calls = 0
        self._rate_limited_once = set()

    def generate_content(self, prompt, generation_config=None):
        self.calls += 1
        is_batch = "BATCH CONTROLS" in prompt
        ids = re.findall(r"CONTROL:\s*([A-Z]+-\d+)", prompt)
        if not ids:
            ids = re.findall(r"\bid:\s*([A-Z]+-\d+)", prompt)
        if not ids:
            raise ValueError("FakeModel could not find a control id in the prompt")
        if any(i in self.fail_on for i in ids):
            raise RuntimeError("Simulated API failure for " + ",".join(ids))
        if self.rate_limit_on_first and ids[0] not in self._rate_limited_once:
            self._rate_limited_once.add(ids[0])
            raise RuntimeError("429 ResourceExhausted: quota exceeded")
        if is_batch:
            # Batch endpoint always expects a JSON array, even for one control.
            return FakeResponse(json.dumps([self.payloads[i] for i in ids]))
        if len(ids) == 1:
            payload = self.payloads[ids[0]]
            return FakeResponse(json.dumps(payload))
        return FakeResponse(
            json.dumps([self.payloads[i] for i in ids])
        )


class FakeModelText:
    """Returns a fixed raw text response regardless of the prompt."""

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def generate_content(self, prompt, generation_config=None):
        self.calls += 1
        return FakeResponse(self.text)
