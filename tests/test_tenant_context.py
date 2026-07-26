from types import SimpleNamespace

from app.infrastructure.database import apply_rls_context
from app.services.tenant_context import (
    begin_request_scope,
    bind_authenticated_tenant,
    current_access_mode,
    current_public_support_request_id,
    current_tenant_id,
    public_support_request_scope,
    reset_request_scope,
    tenant_scope,
)


class _FakeConnection:
    def __init__(self, dialect_name: str):
        self.dialect = SimpleNamespace(name=dialect_name)
        self.calls: list[dict[str, str]] = []

    def execute(self, _statement, parameters):
        self.calls.append(parameters)


def test_authenticated_tenant_context_is_applied_to_each_postgres_transaction():
    tokens = begin_request_scope(public=False)
    try:
        bind_authenticated_tenant("tenant_uct")
        connection = _FakeConnection("postgresql")
        apply_rls_context(None, None, connection)
    finally:
        reset_request_scope(tokens)

    assert connection.calls == [
        {"tenant_id": "tenant_uct"},
        {"access_mode": "tenant"},
        {"request_id": ""},
    ]


def test_public_request_scope_never_sets_a_tenant_identifier():
    tokens = begin_request_scope(public=True)
    try:
        assert current_tenant_id() is None
        assert current_access_mode() == "public"
        connection = _FakeConnection("postgresql")
        apply_rls_context(None, None, connection)
    finally:
        reset_request_scope(tokens)

    assert connection.calls == [
        {"tenant_id": ""},
        {"access_mode": "public"},
        {"request_id": ""},
    ]


def test_background_tenant_scope_is_restored_after_work_completes():
    prior_tenant_id = current_tenant_id()
    prior_access_mode = current_access_mode()
    with tenant_scope("tenant_uct"):
        assert current_tenant_id() == "tenant_uct"
        assert current_access_mode() == "tenant"
        assert current_public_support_request_id() is None
    assert current_tenant_id() == prior_tenant_id
    assert current_access_mode() == prior_access_mode


def test_public_support_request_scope_is_temporary_and_server_scoped():
    tokens = begin_request_scope(public=True)
    try:
        with public_support_request_scope("support_server_generated"):
            assert current_public_support_request_id() == "support_server_generated"
            connection = _FakeConnection("postgresql")
            apply_rls_context(None, None, connection)
        assert current_public_support_request_id() is None
    finally:
        reset_request_scope(tokens)

    assert connection.calls == [
        {"tenant_id": ""},
        {"access_mode": "public"},
        {"request_id": "support_server_generated"},
    ]
