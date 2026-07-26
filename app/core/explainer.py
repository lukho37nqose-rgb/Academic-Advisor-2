"""
Explanation Layer.

Turns an already-computed, already-cited ReasoningGraph into human-readable,
citation-bound prose. This module runs strictly AFTER the deterministic
decision exists (see engine.py) and must never be able to change it -- it
translates a decision, it does not make one.
"""

import json
from app.core.models import ReasoningGraph
from app.services.llm_gateway import call_explanation_generation

EXPLANATION_SYSTEM_PROMPT = """You are drafting the explanation shown to someone
after a decision about them has already been made by a separate, deterministic
rules engine. That decision is final and is provided to you as a trace.

Hard rules:
- Never contradict the trace's overall decision. Your job is to explain it,
  not to re-decide it or hedge on it.
- Only reference facts, rule labels, and source citations that literally
  appear in the trace JSON below. Never invent a rule, a citation, a number,
  or a fact that is not present in the trace.
- If a node's status is NEEDS_MANUAL_REVIEW, say so plainly and explain what
  made it ambiguous -- do not resolve the ambiguity yourself.
- Write for the person the decision is about: plain language, no jargon,
  cite the specific rule that drove each part of the outcome.
- Keep it to a short paragraph. This is a decision explanation, not a report.
"""


async def format_explanation(graph: ReasoningGraph) -> str:
    """Generates a human-readable explanation of the reasoning graph."""
    trace_json = json.dumps(graph.model_dump(mode="json"))
    return await call_explanation_generation(trace_json, EXPLANATION_SYSTEM_PROMPT)
