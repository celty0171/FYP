"""Thin OpenAI-compatible client for Alibaba Cloud Bailian / DashScope.

Bailian exposes an OpenAI-compatible endpoint, so we reuse the ``openai`` SDK exactly as
``qwen3_test.py`` does for the self-hosted Qwen models — only the base_url, key and model
differ (read from ``.env`` via ``config.load_config``).
"""

from __future__ import annotations

import json
from typing import Any


class BailianClient:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        if not api_key:
            raise RuntimeError(
                "DASHSCOPE_API_KEY is not set in .env — cannot call Bailian."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "The Bailian client needs the openai SDK "
                "(pip install -r schemavislm/requirements.txt)"
            ) from exc
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def chat_json(self, system: str, user: str, temperature: float = 0.0) -> dict[str, Any]:
        """Ask for a JSON object and return it parsed. Raises on unparseable output."""
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = (resp.choices[0].message.content or "").strip()
        return _extract_json(content)


def _extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating ```json fences or surrounding prose."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if 0 <= start < end:
            return json.loads(s[start : end + 1])
        raise


def from_config(config: Any) -> BailianClient:
    return BailianClient(
        api_key=config.dashscope_api_key,
        base_url=config.dashscope_base_url,
        model=config.nl_model,
    )
