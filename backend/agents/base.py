"""Base agent — thin wrapper around emergentintegrations.LlmChat that:

  1. picks the right provider/model from Settings,
  2. asks the LLM for a strict JSON payload,
  3. validates the payload against a Pydantic model,
  4. on validation failure, retries with the error fed back to the LLM
     so it can self-correct,
  5. lets sub-classes override the system prompt.

Every agent inherits this and just implements `_build_prompt(state)` +
`response_model`. Keeps agent code very small and makes the whole
workflow robust to LLM variation across providers and models.
"""

from __future__ import annotations

import json
import re
from typing import Any, Generic, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from backend.core.config import get_settings
from backend.core.exceptions import LLMError
from backend.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_VALIDATION_RETRIES = 2  # total attempts = 1 + this many retries


class BaseAgent(Generic[T]):
    name: str = "base_agent"
    response_model: Type[T]

    def __init__(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt

    async def _chat_json(self, user_prompt: str, *, temperature: float = 0.1) -> dict:
        """Call the LLM and return the parsed JSON payload.

        We keep this method deliberately robust: LLMs occasionally wrap JSON
        in fenced blocks or add prose. We strip those before parsing.

        When there's an active `stream_id` in the ambient context (set by
        `graph._track()` via `progress.bind_stream_id`), we use
        `stream_message` so token deltas can be published to the UI as
        `kind="token"` progress events. Otherwise we fall back to the
        classic `send_message` path.
        """
        settings = get_settings()
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage  # local import
        except Exception as e:
            raise LLMError(f"emergentintegrations not available: {e}")

        chat = LlmChat(
            api_key=settings.active_llm_key(),
            session_id=f"aipp:{self.name}",
            system_message=self.system_prompt
            + "\n\nReturn ONLY a valid JSON object matching the schema. "
            "No prose. No markdown fences.",
        ).with_model(settings.llm_provider, settings.llm_model)

        # Decide streaming vs. one-shot based on the ambient stream_id.
        text = await self._invoke_llm(chat, UserMessage, user_prompt)

        # Record usage (estimated — see backend/services/llm_usage.py).
        try:
            from backend.services.llm_usage import tracker
            tracker().record(
                agent=self.name,
                provider=settings.llm_provider,
                model=settings.llm_model,
                prompt_chars=len(self.system_prompt) + len(user_prompt),
                completion_chars=len(text),
            )
        except Exception:                                       # noqa: BLE001
            logger.debug("llm_usage: failed to record call", exc_info=True)

        # Iteration-27: attach prompt + rough token/cost estimates to the
        # currently-active agent trace (if any). We deliberately reuse the
        # `llm_usage.tracker()` estimator so a single source of truth is
        # used both for the top-badge and the per-agent trace panel.
        try:
            from backend.services import agent_trace as _at
            collector = _at.current()
            if collector is not None:
                # Rough token estimates — same 4-chars-per-token heuristic
                # `llm_usage` uses. This is intentional: consistency with
                # the top-of-page usage badge trumps precise vendor counts.
                p_toks = max(1, (len(self.system_prompt) + len(user_prompt)) // 4)
                c_toks = max(1, len(text) // 4)
                # Cost estimator is provider-specific; look up the same
                # rate table.
                try:
                    from backend.services.llm_usage import estimate_cost_usd
                    cost = estimate_cost_usd(
                        provider=settings.llm_provider,
                        model=settings.llm_model,
                        prompt_tokens=p_toks,
                        completion_tokens=c_toks,
                    )
                except Exception:                                  # noqa: BLE001
                    cost = 0.0
                collector.record_llm(
                    provider=settings.llm_provider,
                    model=settings.llm_model,
                    prompt=user_prompt,
                    prompt_tokens=p_toks,
                    completion_tokens=c_toks,
                    cost_usd=cost,
                )
        except Exception:                                       # noqa: BLE001
            logger.debug("agent_trace: failed to attach llm call", exc_info=True)

        json_text = _extract_json(text)
        try:
            return json.loads(json_text)
        except json.JSONDecodeError as e:
            # Self-healing JSON repair fallback (strip trailing commas, clean unescaped newlines)
            repaired = _repair_json(json_text)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                logger.error("agent=%s bad JSON: %s", self.name, text[:400])
                raise LLMError(f"Agent {self.name} returned invalid JSON: {e}")

    async def _invoke_llm(self, chat: Any, UserMessage: Any, user_prompt: str) -> str:
        """Call the LLM. Uses streaming iff there's an active stream_id.

        Returns the concatenated assistant response text either way.
        """
        from backend.orchestrator import progress
        sid = progress.current_stream_id()

        if not sid:
            # No live UI listener — cheap one-shot path.
            try:
                reply = await chat.send_message(UserMessage(text=user_prompt))
            except Exception as e:
                raise LLMError(f"LLM call failed for agent {self.name}: {e}")
            return reply if isinstance(reply, str) else str(reply)

        # Streaming path — publish per-delta token events to the SSE bus.
        buffer: list[str] = []
        try:
            stream = chat.stream_message(UserMessage(text=user_prompt))
            async for event in stream:
                # emergentintegrations yields TextDelta / ToolCallStart /
                # StreamDone dataclasses. We only care about content deltas
                # here (AIPP does not use tool-calls in the planning path).
                delta = getattr(event, "content", None)
                if delta:
                    buffer.append(delta)
                    # Debounce: publish every ~24 chars OR at word boundary
                    # to avoid flooding the SSE queue with 1-char frames.
                    if len(delta) >= 4 or delta.endswith((" ", "\n", ".", ",", ":", ";")):
                        await progress.publish(
                            sid, agent=self.name, status="running",
                            detail=delta[:200], kind="token",
                        )
        except Exception as e:
            raise LLMError(
                f"LLM streaming call failed for agent {self.name}: {e}"
            )
        return "".join(buffer)

    async def run(self, **inputs: Any) -> T:
        """Run the agent with self-healing validation retries.

        1. Build the user prompt from inputs.
        2. Call the LLM, parse JSON, validate against the response model.
        3. If validation fails, append the error to the prompt and ask the
           LLM to correct itself. Repeat up to MAX_VALIDATION_RETRIES times.
        4. If all retries fail, raise LLMError with the last error.
        """
        prompt = self._build_prompt(**inputs)
        last_error: Optional[ValidationError] = None
        last_payload: Any = None

        for attempt in range(1 + MAX_VALIDATION_RETRIES):
            if attempt == 0:
                current_prompt = prompt
            else:
                # feed the previous payload + validation error back so the
                # model can correct itself
                current_prompt = (
                    f"{prompt}\n\n"
                    f"---\n"
                    f"Your previous response was rejected by the JSON schema "
                    f"validator with these errors:\n"
                    f"{_format_validation_error(last_error)}\n"
                    f"\nPrevious response was:\n"
                    f"{json.dumps(last_payload, indent=2)[:1500]}\n"
                    f"\nReturn a corrected JSON object that follows the "
                    f"schema exactly. Use only the allowed enum values."
                )

            payload = await self._chat_json(current_prompt)
            try:
                return self.response_model.model_validate(payload)
            except ValidationError as e:
                last_error = e
                last_payload = payload
                logger.warning(
                    "agent=%s validation failed on attempt %d/%d: %s",
                    self.name, attempt + 1, 1 + MAX_VALIDATION_RETRIES,
                    _format_validation_error(e)[:400],
                )

        logger.error(
            "agent=%s all %d attempts failed schema validation",
            self.name, 1 + MAX_VALIDATION_RETRIES,
        )
        raise LLMError(
            f"Agent {self.name} response failed schema validation after "
            f"{1 + MAX_VALIDATION_RETRIES} attempts: {last_error}"
        )

    def _build_prompt(self, **inputs: Any) -> str:  # noqa: D401
        raise NotImplementedError


def _format_validation_error(err: Optional[ValidationError]) -> str:
    """Compact human-readable representation of a Pydantic ValidationError."""
    if err is None:
        return "(none)"
    lines = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e.get("loc", []))
        msg = e.get("msg", "")
        input_value = e.get("input", "")
        lines.append(f"  - field '{loc}': {msg} (got: {input_value!r})")
    return "\n".join(lines) if lines else str(err)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> str:
    """Strip Markdown fences / prose; return the FIRST complete JSON blob.

    Streaming LLM responses occasionally emit two JSON objects back-to-back
    (a "reasoning" object followed by the actual answer, or an accidental
    duplication of the payload). Naively taking ``text[first{:last}]``
    would then produce concatenated JSON and blow up ``json.loads`` with
    ``Extra data: line NN column N``. We instead brace-count from the first
    ``{`` and stop at the matching close — giving a single valid object.
    """
    text = text.strip()
    m = _FENCE_RE.search(text)
    if m:
        # Inside a fenced block: still run the brace-balance in case there
        # are multiple objects in the fence.
        text = m.group(1).strip()

    if "{" not in text:
        return text

    start = text.index("{")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                # Balanced — return exactly one complete JSON object.
                return text[start : i + 1]
    # Unbalanced (LLM was cut off) — return best-effort slice; the caller
    # will raise a clear "invalid JSON" error including the raw text.
    return text[start:]


def _repair_json(text: str) -> str:
    """Clean common LLM JSON syntax flaws (trailing commas, unescaped newlines)."""
    # 1. Remove trailing commas before closing braces or brackets
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # 2. Fix unescaped control characters inside JSON strings
    text = re.sub(r'(?<=: ")(.*?)(?=",\s*\n|"\s*})', lambda m: m.group(1).replace('\n', '\\n').replace('\t', '\\t'), text, flags=re.DOTALL)
    return text

