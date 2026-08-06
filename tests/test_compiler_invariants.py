"""Compiler invariants that keep a signed policy trace unambiguous."""

import pytest

from app.core.compiler import compile_release_to_graph


def test_compiler_rejects_empty_not_group() -> None:
    payload = {"root": {"id": "root", "operator": "NOT", "children": [], "label": "No"}}
    with pytest.raises(ValueError, match="must have children"):
        compile_release_to_graph("rel_1", payload)


def test_compiler_rejects_not_group_with_multiple_children() -> None:
    payload = {"root": {"id": "root", "operator": "NOT", "label": "No", "children": [
        {"id": "one", "target": "a", "condition": "==", "value": 1, "label": "A"},
        {"id": "two", "target": "b", "condition": "==", "value": 1, "label": "B"},
    ]}}
    with pytest.raises(ValueError, match="exactly one child"):
        compile_release_to_graph("rel_1", payload)


def test_compiler_rejects_duplicate_rule_node_ids() -> None:
    payload = {"root": {"id": "same", "operator": "AND", "label": "All", "children": [
        {"id": "same", "target": "a", "condition": "==", "value": 1, "label": "A"},
    ]}}
    with pytest.raises(ValueError, match="duplicated"):
        compile_release_to_graph("rel_1", payload)
