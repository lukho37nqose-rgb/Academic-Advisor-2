import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArrowRight, CheckCircle2, FileSearch, Info, ShieldAlert } from 'lucide-react';
import { fetchSubjectInformation, type SubjectInformationItem } from '../api/client';

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Your information could not be loaded.';
}

function displayValue(value: unknown): string {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (value === null || value === undefined || value === '') return 'Not recorded';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (Array.isArray(value)) return value.map(displayValue).join(', ');
  return 'Recorded value available';
}

function displayDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function sourceAuthorityLabel(value: string) {
  if (value === 'official_system') return 'Official institutional record';
  if (value === 'institutional_working_record') return 'Institutional working record';
  if (value === 'subject_submitted') return 'Information submitted for consideration';
  return 'Governed source record';
}

function statusPresentation(item: SubjectInformationItem) {
  if (item.status === 'accepted') {
    return {
      icon: CheckCircle2,
      className: 'border-emerald-200 bg-emerald-50 text-emerald-900',
      iconClassName: 'text-emerald-700',
    };
  }
  if (item.status === 'conflict') {
    return {
      icon: ShieldAlert,
      className: 'border-amber-200 bg-amber-50 text-amber-900',
      iconClassName: 'text-amber-700',
    };
  }
  return {
    icon: Info,
    className: 'border-slate-200 bg-slate-50 text-slate-800',
    iconClassName: 'text-slate-600',
  };
}

function decisionLabel(decision: SubjectInformationItem['used_in'][number]['decision']) {
  if (decision === 'ELIGIBLE') return 'requirements met';
  if (decision === 'INELIGIBLE') return 'action may be needed';
  return 'needs review';
}

function groupByDomain(items: SubjectInformationItem[]) {
  return items.reduce<Record<string, SubjectInformationItem[]>>((groups, item) => {
    const key = item.domain_name || item.domain_id;
    groups[key] = [...(groups[key] || []), item];
    return groups;
  }, {});
}

function InformationCard({ item, highlighted }: { item: SubjectInformationItem; highlighted: boolean }) {
  const status = statusPresentation(item);
  const StatusIcon = status.icon;
  const sourceDate = displayDate(item.source.as_of || item.source.captured_at);
  const sourceName = item.source.system || sourceAuthorityLabel(item.source.authority);
  return (
    <article
      id={`information-item-${item.information_id}`}
      className={`border p-4 ${highlighted ? 'border-primary ring-2 ring-primary/20' : 'border-border'}`}
    >
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto]">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="font-semibold">{item.label}</h4>
            <span className={`inline-flex items-center gap-1 border px-2 py-0.5 text-xs font-semibold ${status.className}`}>
              <StatusIcon aria-hidden="true" className={`h-3.5 w-3.5 ${status.iconClassName}`} />
              {item.status_label}
            </span>
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted">Cacisa currently understands this as <span className="font-semibold text-primary">{displayValue(item.value)}</span>.</p>
        </div>
        {item.used_in.length > 0 && (
          <a
            href={`?experience=subject&trace=${encodeURIComponent(item.used_in[0].trace_id)}`}
            className="inline-flex h-fit items-center gap-2 border border-border px-3 py-2 text-sm font-semibold hover:bg-accent"
          >
            Open current position <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </a>
        )}
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-semibold underline underline-offset-4">See where this came from</summary>
        <div className="mt-4 grid gap-5 text-sm md:grid-cols-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-normal text-muted">What Cacisa understood</p>
            <p className="mt-1">{displayValue(item.value)}</p>
            <p className="mt-1 text-xs text-muted">{item.governed_person_label || 'person'} information for {item.domain_name}</p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-normal text-muted">Where it came from</p>
            <p className="mt-1">{sourceName}{sourceDate ? `, ${sourceDate}` : ''}</p>
            <p className="mt-1 text-xs text-muted">
              {sourceAuthorityLabel(item.source.authority)}
              {item.source.reference ? `: ${item.source.reference}` : ''}
            </p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-normal text-muted">Status</p>
            <p className="mt-1">{item.status_explanation}</p>
            {item.reviewed_at && <p className="mt-1 text-xs text-muted">Accepted {displayDate(item.reviewed_at)}</p>}
          </div>
        </div>

        <div className="mt-5 border-t border-border pt-4">
          <p className="text-xs font-semibold uppercase tracking-normal text-muted">Why it matters</p>
          {item.used_in.length === 0 ? (
            <p className="mt-2 text-sm text-muted">This information is recorded, but it has not appeared in a saved decision trace yet.</p>
          ) : (
            <ul className="mt-2 grid gap-2">
              {item.used_in.map((use) => (
                <li key={use.trace_id} className="flex flex-wrap items-center justify-between gap-3 border-l-2 border-border pl-3">
                  <span>{use.position_label}: <span className="font-semibold">{decisionLabel(use.decision)}</span> under release {use.release_version}</span>
                  <a href={`?experience=subject&trace=${encodeURIComponent(use.trace_id)}`} className="text-sm font-semibold underline underline-offset-4">View decision</a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </article>
  );
}

export function SubjectInformationView({ highlightInformationId }: { highlightInformationId?: string | null }) {
  const [items, setItems] = useState<SubjectInformationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchSubjectInformation()
      .then((response) => active && setItems(response))
      .catch((requestError) => active && setError(errorMessage(requestError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!highlightInformationId || loading) return;
    const node = document.getElementById(`information-item-${highlightInformationId}`);
    node?.scrollIntoView({ block: 'center' });
  }, [highlightInformationId, loading]);

  const grouped = useMemo(() => groupByDomain(items), [items]);
  const acceptedCount = items.filter((item) => item.status === 'accepted').length;
  const uncertainCount = items.length - acceptedCount;

  return (
    <section aria-labelledby="subject-information-heading">
      <div className="flex items-start gap-3">
        <FileSearch aria-hidden="true" className="mt-1 h-5 w-5 shrink-0 text-muted" />
        <div>
          <h2 id="subject-information-heading" className="text-xl font-semibold">Information Cacisa uses about you</h2>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">This shows the governed information Cacisa currently has, where it came from, whether it has been accepted, and which decisions have used it.</p>
        </div>
      </div>
      {loading && <p className="mt-5 text-sm text-muted">Loading the information Cacisa has recorded...</p>}
      {error && <div role="alert" className="mt-5 flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {!loading && !error && items.length === 0 && <p className="mt-5 border-l-2 border-border pl-4 text-sm leading-relaxed text-muted">No governed information is available in this service yet. That may mean your institution has not connected an accepted record for you here, not that the institution has no record about you.</p>}
      {!loading && !error && items.length > 0 && (
        <>
          <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
            <div className="border border-border p-3"><dt className="font-semibold">Accepted for decisions</dt><dd className="mt-1 text-muted">{acceptedCount} record{acceptedCount === 1 ? '' : 's'}</dd></div>
            <div className="border border-border p-3"><dt className="font-semibold">Needs confirmation or review</dt><dd className="mt-1 text-muted">{uncertainCount} record{uncertainCount === 1 ? '' : 's'}</dd></div>
          </dl>
          <div className="mt-5 grid gap-6">
            {Object.entries(grouped).map(([domainName, domainItems]) => (
              <div key={domainName}>
                <h3 className="text-base font-semibold">{domainName}</h3>
                <div className="mt-3 grid gap-3">
                  {domainItems.map((item) => (
                    <InformationCard key={item.information_id} item={item} highlighted={item.information_id === highlightInformationId} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
      <p className="mt-5 border-l-2 border-border pl-4 text-xs leading-relaxed text-muted">You cannot edit governed records directly here. If a decision using this information looks wrong or incomplete, open that decision and use the review route shown there.</p>
    </section>
  );
}
