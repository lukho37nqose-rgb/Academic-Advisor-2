import { useEffect, useState } from 'react';
import { AlertTriangle, ArrowRight, BookOpenCheck, CalendarCheck, CircleHelp } from 'lucide-react';
import { fetchSubjectCurrentPositions, type SubjectCurrentPosition } from '../api/client';

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Your current positions could not be loaded.';
}

function positionStatus(position: SubjectCurrentPosition) {
  if (position.decision === 'ELIGIBLE') return { label: 'Requirements met', className: 'text-emerald-800' };
  if (position.decision === 'INELIGIBLE') return { label: 'Action may be needed', className: 'text-rose-800' };
  return { label: 'Human consideration', className: 'text-amber-800' };
}

function positionDescription(position: SubjectCurrentPosition) {
  const person = position.governed_person_label?.trim();
  const suffix = person && person.toLowerCase() !== 'person' ? ` as a ${person}` : '';
  if (position.position_type === 'curriculum') return `Your latest evaluated curriculum or progression position${suffix}.`;
  if (position.position_type === 'assessment_eligibility') return `Your latest evaluated assessment eligibility position${suffix}.`;
  if (position.position_type === 'eligibility') return `Your latest evaluated eligibility position${suffix}.`;
  if (position.position_type === 'institutional_standing') return `Your latest evaluated institutional standing${suffix}.`;
  return `Your latest evaluated institutional position${suffix}.`;
}

function recordDescription(position: SubjectCurrentPosition) {
  const date = position.source_as_of ? new Date(position.source_as_of).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }) : null;
  const source = position.source_system || (position.source_authority === 'official_system' ? 'an official institutional system' : 'the records available to this service');
  if (position.record_state === 'provisional') return `Current and provisional, based on ${source}${date ? ` as of ${date}` : ''}.`;
  return `Confirmed from ${source}${date ? ` as of ${date}` : ''}.`;
}

function sourceAuthorityLabel(position: SubjectCurrentPosition) {
  if (position.source_authority === 'official_system') return 'Official institutional record';
  if (position.source_authority === 'institutional_working_record') return 'Institutional working record';
  return 'Information submitted for consideration';
}

function sourceMeaning(position: SubjectCurrentPosition) {
  if (position.record_state === 'provisional') return 'This may change while the responsible department completes its normal process. It is not a final adverse decision.';
  return 'This record has been confirmed by the named institutional source.';
}

function actionLabel(position: SubjectCurrentPosition) {
  if (position.decision === 'NEEDS_MANUAL_REVIEW') return 'See what needs consideration';
  if (position.decision === 'INELIGIBLE') return 'See why and request a review';
  return 'See why this applies';
}

function provisionalCommitment(position: SubjectCurrentPosition) {
  if (position.record_state !== 'provisional') return null;
  const expected = position.source_expected_by ? new Date(position.source_expected_by).toLocaleString() : null;
  const escalation = position.provisional_escalation_by ? new Date(position.provisional_escalation_by).toLocaleString() : null;
  const owner = position.responsible_group || 'the responsible institutional office';
  if (position.source_is_stale) return `The expected source refresh is overdue. ${owner} is responsible for resolving this; escalation is due ${escalation || 'under the published casework commitment'}.`;
  return `Expected source refresh: ${expected || 'not recorded'}. ${owner} is responsible if this remains provisional${escalation ? ` after ${escalation}` : ''}.`;
}

function positionIcon(type: SubjectCurrentPosition['position_type']) {
  if (type === 'curriculum') return BookOpenCheck;
  if (type === 'assessment_eligibility') return CalendarCheck;
  return CircleHelp;
}

export function SubjectTransparencyDashboard() {
  const [positions, setPositions] = useState<SubjectCurrentPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchSubjectCurrentPositions()
      .then((items) => active && setPositions(items))
      .catch((requestError) => active && setError(errorMessage(requestError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  return (
    <section aria-labelledby="current-positions-heading">
      <h2 id="current-positions-heading" className="text-xl font-semibold">Your current positions</h2>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">This brings together the latest positions this service has evaluated for you. Open one to see the rule, policy release, and record that informed it.</p>
      {loading && <p className="mt-5 text-sm text-muted">Loading your current positions...</p>}
      {error && <div role="alert" className="mt-5 flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {!loading && !error && positions.length === 0 && <p className="mt-5 border-l-2 border-border pl-4 text-sm leading-relaxed text-muted">There are no evaluated positions to show yet. Your institution may still be preparing this service, or may use another official system for this information.</p>}
      {!loading && !error && positions.length > 0 && <div className="mt-5 grid gap-4 md:grid-cols-2">
        {positions.map((position) => {
          const status = positionStatus(position);
          const Icon = positionIcon(position.position_type);
          return <article key={position.trace_id} className="border border-border p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3"><Icon aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-muted" /><div><h3 className="font-semibold">{position.position_label}</h3><p className="mt-1 text-sm text-muted">{positionDescription(position)}</p></div></div>
              <span className={`shrink-0 text-sm font-semibold ${status.className}`}>{status.label}</span>
            </div>
            <dl className="mt-4 grid gap-3 border-l-2 border-border pl-3 text-xs leading-relaxed">
              <div><dt className="font-semibold text-primary">Rules used</dt><dd className="mt-0.5 text-muted">Release {position.release_version}</dd></div>
              <div><dt className="font-semibold text-primary">Information used</dt><dd className="mt-0.5 text-muted">{sourceAuthorityLabel(position)}{position.source_system ? `: ${position.source_system}` : ''}</dd></div>
              <div><dt className="font-semibold text-primary">Record status</dt><dd className="mt-0.5 text-muted">{recordDescription(position)} {sourceMeaning(position)}</dd></div>
              {provisionalCommitment(position) && <div><dt className="font-semibold text-primary">What happens next</dt><dd className={`mt-0.5 ${position.source_is_stale ? 'font-medium text-rose-700' : 'text-muted'}`}>{provisionalCommitment(position)}</dd></div>}
            </dl>
            <a href={`?experience=subject&trace=${encodeURIComponent(position.trace_id)}`} className="mt-4 inline-flex items-center gap-2 text-sm font-semibold underline underline-offset-4">{actionLabel(position)} <ArrowRight aria-hidden="true" className="h-4 w-4" /></a>
          </article>;
        })}
      </div>}
      <p className="mt-6 border-l-2 border-border pl-4 text-xs leading-relaxed text-muted">This is an explanation of evaluated policy positions. It does not replace the official system of record or a later authorised institutional decision.</p>
    </section>
  );
}
