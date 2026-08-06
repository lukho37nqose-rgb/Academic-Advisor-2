import { useEffect, useState } from 'react';
import { useAuth } from 'react-oidc-context';
import { Activity, Building2, ShieldCheck } from 'lucide-react';
import { fetchProviderSession, fetchProviderTenants, type ProviderTenantControl } from './api/client';
import { isOidcConfigured } from './authConfig';

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Provider operations could not be loaded.';
}

export function ProviderApp() {
  const auth = useAuth();
  const [tenants, setTenants] = useState<ProviderTenantControl[]>([]);
  const [role, setRole] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOidcConfigured) return;
    if (!auth.isAuthenticated) return;
    let active = true;
    Promise.all([fetchProviderSession(), fetchProviderTenants()])
      .then(([session, items]) => {
        if (!active) return;
        setRole(session.role);
        setTenants(items);
      })
      .catch((requestError) => active && setError(errorMessage(requestError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [auth.isAuthenticated]);

  if (!isOidcConfigured) {
    return <main className="min-h-screen bg-white px-6 py-10"><div role="alert" className="border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">Provider sign-in is not configured. Set the approved provider OIDC authority and client identifier before using this workspace.</div></main>;
  }

  if (auth.isLoading) return <main className="min-h-screen bg-white px-6 py-10"><p className="text-sm text-muted">Checking provider access...</p></main>;
  if (!auth.isAuthenticated) return <main className="flex min-h-screen items-center justify-center bg-white px-6"><section className="max-w-md text-center"><ShieldCheck className="mx-auto h-8 w-8 text-muted" /><h1 className="mt-4 text-2xl font-semibold">Provider operations</h1><p className="mt-3 text-sm leading-relaxed text-muted">This workspace is for platform operations only. It does not provide access to institutional records or policy decisions.</p><button type="button" onClick={() => void auth.signinRedirect()} className="mt-6 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90">Sign in</button></section></main>;

  return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><div className="mx-auto max-w-6xl">
    <header className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-6"><div><div className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-muted" /><p className="text-sm font-medium text-muted">Provider control plane</p></div><h1 className="mt-2 text-2xl font-semibold">Platform operations</h1><p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">Tenant lifecycle and integration health only. Subject records, evidence, policy content, and decisions are intentionally unavailable here.</p></div><p className="text-sm text-muted">{role.replaceAll('_', ' ')}</p></header>
    {loading && <p className="py-8 text-sm text-muted">Loading operational metadata...</p>}
    {error && <div role="alert" className="mt-6 border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{error}</div>}
    {!loading && !error && <section aria-labelledby="provider-tenants-heading" className="pt-8"><div className="flex items-center gap-2"><Building2 className="h-5 w-5 text-muted" /><h2 id="provider-tenants-heading" className="text-xl font-semibold">Tenants</h2></div><p className="mt-2 text-sm text-muted">A tenant record indicates platform provisioning state, not activity within that institution.</p>{tenants.length === 0 ? <p className="mt-6 border-l-2 border-border pl-4 text-sm text-muted">No tenants have been provisioned.</p> : <div className="mt-6 divide-y divide-border border-y border-border">{tenants.map((tenant) => <article key={tenant.tenant_id} className="grid gap-3 py-5 md:grid-cols-[minmax(0,1fr)_180px_180px]"><div><h3 className="font-semibold">{tenant.tenant_name}</h3><p className="mt-1 text-sm text-muted">{tenant.tenant_id}</p></div><div><p className="text-xs font-medium uppercase text-muted">Lifecycle</p><p className="mt-1 text-sm font-medium">{tenant.lifecycle_state}</p></div><div><p className="flex items-center gap-2 text-xs font-medium uppercase text-muted"><Activity className="h-3.5 w-3.5" />Integration</p><p className="mt-1 text-sm font-medium">{tenant.integration_status.replaceAll('_', ' ')}</p></div></article>)}</div>}</section>}
  </div></main>;
}
