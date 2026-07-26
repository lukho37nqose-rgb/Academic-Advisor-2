import { type ChangeEvent, type FormEvent, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  FilePenLine,
  History,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import {
  fetchGovernancePermissions,
  submitQuickEdit,
  type GovernancePermissions,
  type QuickEditPayload,
  type QuickEditResponse,
} from '../api/client';

const initialForm: QuickEditPayload = {
  domain_id: 'dom_curr_2026',
  target_type: 'course',
  target_id: '',
  field: 'course_description',
  old_value: '',
  new_value: '',
  reason: '',
  source_reference: '',
};

function capabilityIcon(enabled: boolean) {
  if (enabled) {
    return <CheckCircle2 className="mx-auto h-4 w-4 text-emerald-600" aria-label="Allowed" />;
  }
  return <XCircle className="mx-auto h-4 w-4 text-zinc-300" aria-label="Not allowed" />;
}

function errorMessage(err: unknown) {
  const maybeAxios = err as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : ''))
      .filter(Boolean)
      .join(' ');
  }
  return maybeAxios.message || 'Governance request failed.';
}

export function GovernanceDesk() {
  const [form, setForm] = useState<QuickEditPayload>(initialForm);
  const [permissions, setPermissions] = useState<GovernancePermissions | null>(null);
  const [loadingPolicy, setLoadingPolicy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastApplied, setLastApplied] = useState<QuickEditResponse | null>(null);

  const loadPolicy = async (domainId: string) => {
    const normalizedDomain = domainId.trim();
    if (!normalizedDomain) {
      return;
    }
    setLoadingPolicy(true);
    setError(null);
    try {
      const response = await fetchGovernancePermissions(normalizedDomain);
      const firstTarget = response.metadata_quick_edits[0];
      setPermissions(response);
      if (firstTarget) {
        setForm((current) => ({
          ...current,
          domain_id: normalizedDomain,
          target_type: firstTarget.target_type,
          field: firstTarget.fields[0]?.name || '',
          target_id: '',
        }));
      }
    } catch (err) {
      setPermissions(null);
      setError(errorMessage(err));
    } finally {
      setLoadingPolicy(false);
    }
  };

  useEffect(() => {
    void loadPolicy(initialForm.domain_id);
  }, []);

  const selectedTarget = useMemo(
    () => permissions?.metadata_quick_edits.find((target) => target.target_type === form.target_type),
    [form.target_type, permissions],
  );
  const selectedField = selectedTarget?.fields.find((field) => field.name === form.field);
  const canSubmit =
    Boolean(selectedField) &&
    Boolean(form.target_id.trim()) &&
    Boolean(form.new_value.trim()) &&
    form.reason.trim().length >= 5;

  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = event.target;
    if (name === 'target_type') {
      const target = permissions?.metadata_quick_edits.find((item) => item.target_type === value);
      setForm((current) => ({ ...current, target_type: value, field: target?.fields[0]?.name || '' }));
      return;
    }
    setForm((current) => ({ ...current, [name]: value }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await submitQuickEdit({
        ...form,
        domain_id: form.domain_id.trim(),
        target_id: form.target_id.trim(),
        old_value: form.old_value?.trim() || undefined,
        new_value: form.new_value.trim(),
        reason: form.reason.trim(),
        source_reference: form.source_reference?.trim() || undefined,
      });
      setLastApplied(response);
      setForm((current) => ({
        ...current,
        old_value: response.new_value,
        new_value: '',
        reason: '',
        source_reference: '',
      }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const restrictedFields = [
    ...(permissions?.review_required_changes || []),
    ...(permissions?.formal_governance_changes || []),
  ];

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-8">
      <section className="border-b border-border pb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-normal text-muted">
              <ShieldCheck className="h-4 w-4" />
              Governance Desk
            </div>
            <h2 className="text-2xl font-semibold tracking-normal">Tier 1 metadata</h2>
          </div>
          <div className="flex items-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            Edge-configured fields only
          </div>
        </div>
      </section>

      <section className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="flex items-center gap-2 border-b border-border pb-3">
            <FilePenLine className="h-4 w-4 text-muted" />
            <h3 className="text-base font-semibold">Quick edit</h3>
          </div>

          <div className="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="space-y-2 text-sm font-medium">
              Domain ID
              <input
                name="domain_id"
                value={form.domain_id}
                onChange={handleChange}
                className="w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary"
              />
            </label>
            <button
              type="button"
              onClick={() => void loadPolicy(form.domain_id)}
              disabled={loadingPolicy}
              className="inline-flex h-9 items-center gap-2 rounded border border-border px-3 text-sm font-medium disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loadingPolicy ? 'animate-spin' : ''}`} />
              Load
            </button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-sm font-medium">
              Resource type
              <select
                name="target_type"
                value={form.target_type}
                onChange={handleChange}
                disabled={!permissions}
                className="w-full rounded border border-border bg-white px-3 py-2 text-sm outline-none focus:border-primary disabled:bg-zinc-50"
              >
                {(permissions?.metadata_quick_edits || []).map((target) => (
                  <option key={target.target_type} value={target.target_type}>
                    {target.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm font-medium">
              {selectedTarget?.identifier_label || 'Resource ID'}
              <input
                name="target_id"
                value={form.target_id}
                onChange={handleChange}
                className="w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary"
              />
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-sm font-medium">
              Field
              <select
                name="field"
                value={form.field}
                onChange={handleChange}
                disabled={!selectedTarget}
                className="w-full rounded border border-border bg-white px-3 py-2 text-sm outline-none focus:border-primary disabled:bg-zinc-50"
              >
                {(selectedTarget?.fields || []).map((field) => (
                  <option key={field.name} value={field.name}>
                    {field.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm font-medium">
              Current value
              <input
                name="old_value"
                value={form.old_value}
                onChange={handleChange}
                className="w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary"
              />
            </label>
          </div>

          <label className="block space-y-2 text-sm font-medium">
            New value
            <textarea
              name="new_value"
              value={form.new_value}
              onChange={handleChange}
              rows={4}
              className="w-full resize-y rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-sm font-medium">
              Reason
              <input
                name="reason"
                value={form.reason}
                onChange={handleChange}
                className="w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary"
              />
            </label>
            <label className="space-y-2 text-sm font-medium">
              Source reference
              <input
                name="source_reference"
                value={form.source_reference}
                onChange={handleChange}
                className="w-full rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary"
              />
            </label>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {lastApplied && (
            <div className="flex items-start gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
              <History className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                Applied {selectedField?.label || lastApplied.field} to {lastApplied.target_id} under change{' '}
                {lastApplied.change_id}.
              </span>
            </div>
          )}

          <button
            type="submit"
            disabled={!canSubmit || submitting}
            className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <FilePenLine className="h-4 w-4" />
            {submitting ? 'Applying...' : 'Apply quick edit'}
          </button>
        </form>

        <aside className="space-y-6">
          <div className="border-b border-border pb-4">
            <div className="mb-3 flex items-center gap-2">
              <ClipboardList className="h-4 w-4 text-muted" />
              <h3 className="text-base font-semibold">Escalation boundary</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              {restrictedFields.map((field) => (
                <span key={field} className="rounded border border-border px-2 py-1 text-xs text-muted">
                  {field}
                </span>
              ))}
            </div>
          </div>

          <div>
            <h3 className="mb-3 text-base font-semibold">Allowed fields</h3>
            <div className="space-y-2">
              {(selectedTarget?.fields || []).map((field) => (
                <div key={field.name} className="border-b border-border py-2 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span>{field.label}</span>
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{field.notes}</p>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </section>

      <section className="overflow-hidden">
        <div className="mb-3 flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-muted" />
          <h3 className="text-base font-semibold">Role matrix</h3>
        </div>
        <div className="overflow-x-auto border border-border">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead className="bg-accent text-left text-xs uppercase tracking-normal text-muted">
              <tr>
                <th className="px-4 py-3 font-semibold">Role</th>
                <th className="px-4 py-3 text-center font-semibold">Quick edit</th>
                <th className="px-4 py-3 text-center font-semibold">Draft policy</th>
                <th className="px-4 py-3 text-center font-semibold">Approve</th>
                <th className="px-4 py-3 text-center font-semibold">Audit</th>
                <th className="px-4 py-3 font-semibold">Scope</th>
              </tr>
            </thead>
            <tbody>
              {(permissions?.matrix || []).map((row) => (
                <tr key={row.role} className="border-t border-border">
                  <td className="px-4 py-3 font-medium">{row.label}</td>
                  <td className="px-4 py-3 text-center">{capabilityIcon(row.can_quick_edit)}</td>
                  <td className="px-4 py-3 text-center">{capabilityIcon(row.can_author_structured_drafts)}</td>
                  <td className="px-4 py-3 text-center">{capabilityIcon(row.can_approve_releases)}</td>
                  <td className="px-4 py-3 text-center">{capabilityIcon(row.can_replay_audits)}</td>
                  <td className="px-4 py-3 text-muted">{row.scope}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
