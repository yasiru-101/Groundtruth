"""LLM adapter: exactly three named prompts, cached by input hash.

The system is deterministic everywhere except three hops — intake
decomposition, delivery code generation, and report prose. Each hop is a
closed registry entry; calling with an unregistered name fails. Responses
flow through the record/replay envelope, so the request hash (model +
prompt name + variables) is the cache key: RECORD persists each response to
fixtures, REPLAY serves it without a network call.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

import httpx

from groundtruth.adapters.base import Envelope, RequestSpec
from groundtruth.config import RunMode, Settings


class LLMError(Exception):
    pass


class PromptName(str, Enum):
    INTAKE_DECOMPOSE = "intake_decompose"
    DELIVER_CODE = "deliver_code"
    REPORT_PROSE = "report_prose"


PROMPTS: dict[PromptName, str] = {
    PromptName.INTAKE_DECOMPOSE: (
        "You convert raw meeting notes into structured backlog tickets. "
        "For each distinct piece of work, emit a JSON object with fields: "
        "summary (one line), given/when/then acceptance criteria (each a "
        "complete sentence), story points (1,2,3,5,8), and components. "
        "Output only a JSON array, no prose. If a note is too vague to "
        "form a criterion, set it aside into a 'rejected' array with the "
        "reason."
    ),
    PromptName.DELIVER_CODE: (
        "You implement or repair code for one ticket. You receive the "
        "ticket summary, its Given-When-Then acceptance criteria, the "
        "current failing test output, and the relevant source files. "
        "Produce the minimal diff that makes the acceptance tests pass "
        "without weakening any assertion. Never delete or weaken a "
        "failing assertion to achieve green. Output only code."
    ),
    PromptName.REPORT_PROSE: (
        "You write short narrative sections for a project-truthfulness "
        "report. You receive itemised findings, each with evidence "
        "references. Describe what the evidence shows; never invent "
        "numbers, dates, or ticket keys not present in the input. Keep "
        "each section under 120 words, plain language."
    ),
}


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        envelope: Envelope,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._envelope = envelope

        if envelope.mode is not RunMode.REPLAY:
            missing = [
                name
                for name, value in [
                    ("LLM_API_KEY", settings.llm_api_key),
                    ("LLM_MODEL", settings.llm_model),
                    ("LLM_BASE_URL", settings.llm_base_url),
                ]
                if not value
            ]
            if missing:
                raise LLMError(
                    f"LLM adapter in {envelope.mode.value} mode requires: "
                    f"{', '.join(missing)} (set in .env)"
                )

        self._client = client or httpx.Client(
            base_url=settings.llm_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=120.0,
        )

    def close(self) -> None:
        self._client.close()

    def complete(self, name: PromptName, variables: dict[str, Any]) -> str:
        """Run one named prompt over ``variables``; returns the response text."""
        try:
            system_prompt = PROMPTS[name]
        except KeyError:
            known = ", ".join(p.value for p in PromptName)
            raise LLMError(
                f"Unknown prompt {name!r}. The registry is closed: {known}"
            ) from None

        user_content = json.dumps(variables, sort_keys=True, ensure_ascii=False)
        body: dict[str, Any] = {
            "model": self._settings.llm_model,
            "prompt_name": name.value,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        spec = RequestSpec(method="POST", url="/chat/completions", body=body)

        def live() -> str:
            response = self._client.post("/chat/completions", json=body)
            if response.status_code >= 400:
                raise LLMError(
                    f"LLM request failed: HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )
            payload = response.json()
            try:
                return payload["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMError(
                    f"Unexpected LLM response shape: {json.dumps(payload)[:500]}"
                ) from exc

        return self._envelope.call(spec, live)
