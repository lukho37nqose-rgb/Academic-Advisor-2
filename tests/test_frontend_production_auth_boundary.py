from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_frontend_runtime_does_not_fall_back_to_placeholder_oidc_values() -> None:
    production_sources = [
        REPO_ROOT / "frontend" / "src" / "authConfig.ts",
        REPO_ROOT / "frontend" / "src" / "api" / "client.ts",
    ]

    for source in production_sources:
        text = source.read_text(encoding="utf-8")
        assert "your-tenant.auth0.com" not in text
        assert "your-client-id" not in text


def test_synthetic_oidc_values_are_limited_to_the_e2e_runner() -> None:
    e2e_runner = (REPO_ROOT / "frontend" / "scripts" / "run-e2e.mjs").read_text(encoding="utf-8")

    assert "VITE_OIDC_AUTHORITY" in e2e_runner
    assert "https://your-tenant.auth0.com" in e2e_runner
    assert "VITE_OIDC_CLIENT_ID" in e2e_runner
    assert "your-client-id" in e2e_runner


def test_frontend_does_not_default_production_api_calls_to_localhost() -> None:
    client_source = (REPO_ROOT / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    assert "import.meta.env.DEV ? 'http://localhost:8000/api/v1' : '/api/v1'" in client_source
