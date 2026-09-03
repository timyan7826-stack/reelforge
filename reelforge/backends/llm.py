"""LLM backends.

ReelForge treats the "brain" as a swappable component. Two backends ship in
the box:

* ``openai``   — any OpenAI-compatible chat-completions endpoint
                 (OpenAI, DeepSeek, Moonshot, Ollama's OpenAI bridge, ...).
* ``template`` — deterministic, no-API generator used for offline demo runs.

Add your own backend by subclassing :class:`LLMBackend` and registering it in
``create_backend``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass

from reelforge.utils.cost import Usage, estimate_cost


class LLMError(RuntimeError):
    """Raised when an LLM call fails."""


@dataclass
class LLMResult:
    text: str
    usage: Usage


class LLMBackend(ABC):
    """Interface every LLM backend implements."""

    name = "base"

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 2048, temperature: float = 0.7,
                 seed: int | None = None) -> LLMResult:
        """Return the completion text plus usage accounting."""


class OpenAIBackend(LLMBackend):
    """Calls any OpenAI-compatible ``/chat/completions`` endpoint via urllib."""

    name = "openai"

    def __init__(self, model: str, base_url: str | None = None,
                 api_key: str | None = None, *, timeout: int = 120) -> None:
        self.model = model
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY") or ""
        self.timeout = timeout
        if not self.api_key:
            raise LLMError(
                f"backend 'openai' needs an API key. Set OPENAI_API_KEY "
                f"(or LLM_API_KEY) or switch backend to 'template'."
            )

    def complete(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 2048, temperature: float = 0.7,
                 seed: int | None = None) -> LLMResult:
        payload: dict = {
            "model": self.model,
            "messages": [],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append({"role": "user", "content": prompt})
        if seed is not None:
            payload["seed"] = seed

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise LLMError(f"LLM HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"LLM connection error: {exc.reason}") from exc

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"unexpected LLM response shape: {str(data)[:300]}") from exc

        usage_raw = data.get("usage") or {}
        pt = int(usage_raw.get("prompt_tokens", 0))
        ct = int(usage_raw.get("completion_tokens", 0))
        return LLMResult(
            text=text.strip(),
            usage=Usage(
                calls=1,
                prompt_tokens=pt,
                completion_tokens=ct,
                cost_usd=estimate_cost(self.model, pt, ct),
            ),
        )


class TemplateBackend(LLMBackend):
    """Deterministic, offline stand-in for an LLM.

    It understands ReelForge's two structured call protocols — script
    generation (prompt embeds ``{"topic": ...}``) and storyboarding (prompt
    embeds ``{"script": ...}``) — and returns the same JSON shape a real model
    would. Used when no API key is configured so that `reelforge run` still
    produces a real pipeline output for demos, CI, and reviewers.
    """

    name = "template"

    def complete(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 2048, temperature: float = 0.7,
                 seed: int | None = None) -> LLMResult:
        data = _try_json(prompt)
        if isinstance(data, dict) and isinstance(data.get("script"), dict):
            return self._storyboard(data["script"])
        if isinstance(data, dict) and "topic" in data:
            return self._script(str(data["topic"]))
        return self._script(_extract_topic(prompt, system or ""))

    def _script(self, topic: str) -> LLMResult:
        lines = [
            f"{topic}——你真的了解吗？",
            f"先说结论：{topic}，远比你想象中影响更大。",
            f"很多人不知道，{topic}背后的原理并不复杂。",
            f"第一点，先看它最核心的部分，抓住关键就够了。",
            f"第二点，把它放到真实场景里，问题立刻变得具体。",
            f"第三点，记住这条实用建议，今天就能用上。",
            "最后总结一句：理解它，就是掌握主动权。",
        ]
        payload = {"title": topic, "lines": [{"text": line} for line in lines]}
        return LLMResult(text=json.dumps(payload, ensure_ascii=False), usage=Usage(calls=1))

    def _storyboard(self, script: dict) -> LLMResult:
        scenes = []
        for item in script.get("lines", []):
            text = str(item.get("text", "")).strip()
            scenes.append({
                "text": text,
                "visual": f"Clean, well-lit cinematic composition illustrating: {text[:40]}",
            })
        payload = {"scenes": scenes}
        return LLMResult(text=json.dumps(payload, ensure_ascii=False), usage=Usage(calls=1))


def _try_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_topic(prompt: str, system: str) -> str:
    # ReelForge prompts embed the topic as JSON: {"topic": "..."}
    try:
        for line in prompt.splitlines():
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line).get("topic", "这个话题")
    except json.JSONDecodeError:
        pass
    if system:
        # system prompt usually contains: Topic: ...
        for line in system.splitlines():
            if line.lower().startswith("topic:"):
                return line.split(":", 1)[1].strip()
    return "这个话题"


_BACKENDS: dict[str, type[LLMBackend]] = {
    "openai": OpenAIBackend,
    "template": TemplateBackend,
}


def create_backend(cfg: dict) -> LLMBackend:
    """Factory: build an LLM backend from a config block."""
    kind = (cfg.get("backend") or "openai").lower()
    if kind not in _BACKENDS:
        raise LLMError(f"unknown LLM backend '{kind}'. Known: {sorted(_BACKENDS)}")
    cls = _BACKENDS[kind]
    if kind == "openai":
        return cls(
            model=cfg.get("model", "gpt-4o-mini"),
            base_url=cfg.get("base_url"),
            api_key=cfg.get("api_key"),
        )
    return cls()
