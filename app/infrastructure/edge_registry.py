"""
Loads tenant and domain configuration from the Edge layer.

The filesystem registry is the reference deployment implementation. A hosted
deployment can replace it with a database or configuration service while
retaining the same domain-neutral governance contract.
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.services.governance import DomainGovernancePolicy


class DomainConfigurationError(ValueError):
    pass


def _default_edge_root() -> Path:
    return Path(__file__).resolve().parents[2] / "edge"


class EdgeRegistry:
    def __init__(self, root: Path | None = None):
        configured_root = os.environ.get("IRE_EDGE_ROOT")
        self.root = root or (Path(configured_root) if configured_root else _default_edge_root())

    @lru_cache(maxsize=256)
    def _load_domains(self) -> dict[tuple[str, str], dict[str, Any]]:
        domains: dict[tuple[str, str], dict[str, Any]] = {}
        if not self.root.exists():
            raise DomainConfigurationError(f"Edge root does not exist: {self.root}")

        for path in self.root.glob("tenants/*/domains/*/domain.json"):
            try:
                definition = json.loads(path.read_text(encoding="utf-8"))
                key = (definition["tenant_id"], definition["id"])
            except (OSError, json.JSONDecodeError, KeyError) as exc:
                raise DomainConfigurationError(f"Invalid domain definition at {path}: {exc}") from exc
            if key in domains:
                raise DomainConfigurationError(
                    f"Duplicate Edge domain for tenant={key[0]} domain={key[1]}"
                )
            domains[key] = definition
        return domains

    def get_domain(self, tenant_id: str, domain_id: str) -> dict[str, Any]:
        definition = self._load_domains().get((tenant_id, domain_id))
        if definition is None:
            raise DomainConfigurationError(
                f"No Edge configuration for tenant={tenant_id} domain={domain_id}"
            )
        return definition

    def get_governance_policy(
        self,
        tenant_id: str,
        domain_id: str,
    ) -> DomainGovernancePolicy:
        definition = self.get_domain(tenant_id, domain_id)
        try:
            return DomainGovernancePolicy.model_validate(definition.get("governance", {}))
        except ValidationError as exc:
            raise DomainConfigurationError(
                f"Invalid governance configuration for tenant={tenant_id} domain={domain_id}: {exc}"
            ) from exc


edge_registry = EdgeRegistry()


def get_edge_registry() -> EdgeRegistry:
    return edge_registry
