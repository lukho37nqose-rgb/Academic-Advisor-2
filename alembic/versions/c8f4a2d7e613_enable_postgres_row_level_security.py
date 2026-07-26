"""Enforce PostgreSQL tenant row-level security for serving credentials.

Revision ID: c8f4a2d7e613
Revises: b7c1d8e4f529
Create Date: 2026-07-26 02:30:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8f4a2d7e613"
down_revision: Union[str, Sequence[str], None] = "b7c1d8e4f529"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = (
    "tenants",
    "domains",
    "policy_drafts",
    "policy_ambiguities",
    "policy_ambiguity_events",
    "handbook_uploads",
    "handbook_upload_sessions",
    "handbook_pages",
    "handbook_ocr_reviews",
    "handbook_ocr_review_events",
    "metadata_overrides",
    "metadata_quick_edits",
    "releases",
    "rule_graphs",
    "evidence",
    "claims",
    "facts",
    "support_requests",
    "support_request_events",
    "decision_review_cases",
    "decision_review_case_events",
    "reasoning_graphs",
)


def _enable_and_force_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")


def _tenant_domain_policy(table_name: str) -> None:
    op.execute(f"""
        CREATE POLICY tenant_isolation_{table_name}
        ON {table_name}
        FOR ALL
        USING (
            tenant_id = ire.current_tenant_id()
            AND ire.tenant_owns_domain(tenant_id, domain_id)
        )
        WITH CHECK (
            tenant_id = ire.current_tenant_id()
            AND ire.tenant_owns_domain(tenant_id, domain_id)
        )
    """)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("CREATE SCHEMA IF NOT EXISTS ire")
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.current_tenant_id()
        RETURNS text
        LANGUAGE sql
        STABLE
        AS $$ SELECT NULLIF(current_setting('ire.tenant_id', true), '') $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.is_public_request()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$ SELECT current_setting('ire.access_mode', true) = 'public' $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.current_public_support_request_id()
        RETURNS text
        LANGUAGE sql
        STABLE
        AS $$ SELECT NULLIF(current_setting('ire.public_support_request_id', true), '') $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.is_public_policy_domain(schema_document jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT COALESCE(schema_document -> 'access' ->> 'public_policy_guide', 'false') = 'true'
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.is_public_assistance_domain(schema_document jsonb)
        RETURNS boolean
        LANGUAGE sql
        IMMUTABLE
        AS $$
            SELECT COALESCE(schema_document -> 'access' ->> 'assistance_requests_enabled', 'false') = 'true'
        $$
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION ire.tenant_owns_domain(row_tenant_id text, row_domain_id text)
        RETURNS boolean
        LANGUAGE sql
        STABLE
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.domains
                WHERE public.domains.id = row_domain_id
                AND public.domains.tenant_id = row_tenant_id
            )
        $$
    """)

    for table_name in _TABLES:
        _enable_and_force_rls(table_name)

    op.execute("""
        CREATE POLICY tenant_isolation_tenants
        ON tenants
        FOR ALL
        USING (id = ire.current_tenant_id())
        WITH CHECK (id = ire.current_tenant_id())
    """)
    op.execute("""
        CREATE POLICY tenant_or_public_policy_domains
        ON domains
        FOR SELECT
        USING (
            tenant_id = ire.current_tenant_id()
            OR (
                ire.is_public_request()
                AND ire.is_public_policy_domain(schema_definition)
            )
        )
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_domains
        ON domains
        FOR ALL
        USING (tenant_id = ire.current_tenant_id())
        WITH CHECK (tenant_id = ire.current_tenant_id())
    """)

    for table_name in (
        "policy_drafts",
        "policy_ambiguities",
        "policy_ambiguity_events",
        "handbook_uploads",
        "handbook_upload_sessions",
        "metadata_overrides",
        "metadata_quick_edits",
        "evidence",
        "claims",
        "facts",
        "decision_review_cases",
        "decision_review_case_events",
        "reasoning_graphs",
    ):
        _tenant_domain_policy(table_name)

    op.execute("""
        CREATE POLICY tenant_isolation_handbook_ocr_reviews
        ON handbook_ocr_reviews
        FOR ALL
        USING (
            tenant_id = ire.current_tenant_id()
            AND EXISTS (
                SELECT 1 FROM handbook_uploads
                WHERE handbook_uploads.id = handbook_ocr_reviews.handbook_id
                AND handbook_uploads.tenant_id = handbook_ocr_reviews.tenant_id
            )
        )
        WITH CHECK (
            tenant_id = ire.current_tenant_id()
            AND EXISTS (
                SELECT 1 FROM handbook_uploads
                WHERE handbook_uploads.id = handbook_ocr_reviews.handbook_id
                AND handbook_uploads.tenant_id = handbook_ocr_reviews.tenant_id
            )
        )
    """)

    op.execute("""
        CREATE POLICY tenant_or_public_policy_releases
        ON releases
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM domains
                WHERE domains.id = releases.domain_id
            )
        )
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_releases
        ON releases
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM domains
                WHERE domains.id = releases.domain_id
                AND domains.tenant_id = ire.current_tenant_id()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM domains
                WHERE domains.id = releases.domain_id
                AND domains.tenant_id = ire.current_tenant_id()
            )
        )
    """)
    op.execute("""
        CREATE POLICY tenant_or_public_policy_rule_graphs
        ON rule_graphs
        FOR SELECT
        USING (
            EXISTS (
                SELECT 1 FROM releases
                WHERE releases.id = rule_graphs.release_id
            )
        )
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_rule_graphs
        ON rule_graphs
        FOR ALL
        USING (
            EXISTS (
                SELECT 1
                FROM releases
                JOIN domains ON domains.id = releases.domain_id
                WHERE releases.id = rule_graphs.release_id
                AND domains.tenant_id = ire.current_tenant_id()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM releases
                JOIN domains ON domains.id = releases.domain_id
                WHERE releases.id = rule_graphs.release_id
                AND domains.tenant_id = ire.current_tenant_id()
            )
        )
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_handbook_pages
        ON handbook_pages
        FOR ALL
        USING (
            EXISTS (
                SELECT 1 FROM handbook_uploads
                WHERE handbook_uploads.id = handbook_pages.handbook_id
                AND handbook_uploads.tenant_id = ire.current_tenant_id()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM handbook_uploads
                WHERE handbook_uploads.id = handbook_pages.handbook_id
                AND handbook_uploads.tenant_id = ire.current_tenant_id()
            )
        )
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_handbook_ocr_review_events
        ON handbook_ocr_review_events
        FOR ALL
        USING (
            EXISTS (
                SELECT 1
                FROM handbook_ocr_reviews
                JOIN handbook_uploads ON handbook_uploads.id = handbook_ocr_reviews.handbook_id
                WHERE handbook_ocr_reviews.id = handbook_ocr_review_events.ocr_review_id
                AND handbook_uploads.tenant_id = ire.current_tenant_id()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1
                FROM handbook_ocr_reviews
                JOIN handbook_uploads ON handbook_uploads.id = handbook_ocr_reviews.handbook_id
                WHERE handbook_ocr_reviews.id = handbook_ocr_review_events.ocr_review_id
                AND handbook_uploads.tenant_id = ire.current_tenant_id()
            )
        )
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_support_requests
        ON support_requests
        FOR ALL
        USING (
            tenant_id = ire.current_tenant_id()
            AND ire.tenant_owns_domain(tenant_id, domain_id)
        )
        WITH CHECK (
            tenant_id = ire.current_tenant_id()
            AND ire.tenant_owns_domain(tenant_id, domain_id)
        )
    """)
    op.execute("""
        CREATE POLICY public_support_request_insert
        ON support_requests
        FOR INSERT
        WITH CHECK (
            ire.is_public_request()
            AND status = 'OPEN'
            AND id = ire.current_public_support_request_id()
            AND tenant_id = (
                SELECT domains.tenant_id FROM domains
                WHERE domains.id = support_requests.domain_id
                AND ire.is_public_policy_domain(domains.schema_definition)
                AND ire.is_public_assistance_domain(domains.schema_definition)
            )
        )
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_support_request_events
        ON support_request_events
        FOR ALL
        USING (
            tenant_id = ire.current_tenant_id()
            AND ire.tenant_owns_domain(tenant_id, domain_id)
        )
        WITH CHECK (
            tenant_id = ire.current_tenant_id()
            AND ire.tenant_owns_domain(tenant_id, domain_id)
        )
    """)
    op.execute("""
        CREATE POLICY public_support_request_event_insert
        ON support_request_events
        FOR INSERT
        WITH CHECK (
            ire.is_public_request()
            AND actor_id = 'public_submission'
            AND status = 'OPEN'
            AND sequence = 1
            AND support_request_id = ire.current_public_support_request_id()
            AND tenant_id = (
                SELECT domains.tenant_id FROM domains
                WHERE domains.id = support_request_events.domain_id
                AND ire.is_public_policy_domain(domains.schema_definition)
                AND ire.is_public_assistance_domain(domains.schema_definition)
            )
        )
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    policy_names = (
        "tenant_isolation_tenants",
        "tenant_or_public_policy_domains",
        "tenant_isolation_domains",
        "tenant_or_public_policy_releases",
        "tenant_isolation_releases",
        "tenant_or_public_policy_rule_graphs",
        "tenant_isolation_rule_graphs",
        "tenant_isolation_handbook_pages",
        "tenant_isolation_handbook_ocr_review_events",
        "tenant_isolation_support_requests",
        "public_support_request_insert",
        "tenant_isolation_support_request_events",
        "public_support_request_event_insert",
        *(f"tenant_isolation_{table_name}" for table_name in (
            "policy_drafts", "policy_ambiguities", "policy_ambiguity_events",
            "handbook_uploads", "handbook_upload_sessions", "handbook_ocr_reviews",
            "metadata_overrides", "metadata_quick_edits", "evidence", "claims",
            "facts", "decision_review_cases", "decision_review_case_events", "reasoning_graphs",
        )),
    )
    for policy_name in policy_names:
        for table_name in _TABLES:
            op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name}")
    for table_name in _TABLES:
        op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP FUNCTION IF EXISTS ire.is_public_assistance_domain(jsonb)")
    op.execute("DROP FUNCTION IF EXISTS ire.is_public_policy_domain(jsonb)")
    op.execute("DROP FUNCTION IF EXISTS ire.tenant_owns_domain(text, text)")
    op.execute("DROP FUNCTION IF EXISTS ire.current_public_support_request_id()")
    op.execute("DROP FUNCTION IF EXISTS ire.is_public_request()")
    op.execute("DROP FUNCTION IF EXISTS ire.current_tenant_id()")
