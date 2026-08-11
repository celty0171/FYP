"""LLM chart selection for Step 2.

The deterministic recommender (``results/step2_codegen/gpt_recommend_charts.py``) still
produces every eligible chart *and its mapping* — the blind/gold separation and the
Step-2 -> Step-3 field-name contract are untouched. This package only asks an LLM to
**rank those candidates**, pick the one to highlight, give a short English rationale, and
optionally swap a column into an existing mapping role (same dimension only). On any error,
missing key, or invalid answer it falls back to the deterministic pick.
"""

from .llm_chart_selector import select  # noqa: F401
