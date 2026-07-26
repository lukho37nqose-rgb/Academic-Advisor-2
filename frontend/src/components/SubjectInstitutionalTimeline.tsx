import { useEffect, useState } from 'react';
import { AlertTriangle, Landmark, ShieldCheck } from 'lucide-react';
import {
  fetchSubjectInstitutionalTimeline,
  type InstitutionalContextEvent,
  type InstitutionalContextTimelineState,
} from '../api/client';

const stateLabels: Record<InstitutionalContextTimelineState, string> = {
  SUBMITTED: 'Awaiting verification',
  CERTIFIED: 'Certified record',
  REJECTED: 'Not adopted',
  ACTIVE: 'Active',
  SUPERSEDED: 'Superseded by a later decision',
  REVOKED: 'Concluded by a later decision',
  EXPIRED: 'No longer active',
};

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Your institutional timeline could not be loaded.';
}

function formatDate(value: string) {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString(undefined, {
    year: 'numeric', month: 'long', day: 'numeric', timeZone: 'UTC',
  });
}

function TimelineEvent({ event }: { event: InstitutionalContextEvent }) {
  return (
    <article className="relative border-l-2 border-border pl-5 pb-8 last:pb-0">
      <span aria-hidden="true" className="absolute -left-[5px] top-1 h-2 w-2 rounded-full bg-primary" />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-muted">{formatDate(event.event_date)}</p>
          <h3 className="mt-1 text-base font-semibold">{event.title}</h3>
        </div>
        <span className="text-sm font-medium text-primary">{stateLabels[event.timeline_state]}</span>
      </div>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">{event.student_summary}</p>
      <dl className="mt-4 grid gap-3 border-l-2 border-border pl-4 text-sm sm:grid-cols-2">
        <div><dt className="font-medium">Institutional effect</dt><dd className="mt-1 text-muted">{event.institutional_effect}</dd></div>
        <div><dt className="font-medium">Authority</dt><dd className="mt-1 text-muted">{event.authority_name}</dd></div>
        {event.policy_release_version && <div><dt className="font-medium">Related policy release</dt><dd className="mt-1 text-muted">{event.policy_release_version}</dd></div>}
        {event.policy_citation && <div><dt className="font-medium">Policy source</dt><dd className="mt-1 text-muted">{event.policy_citation}</dd></div>}
      </dl>
    </article>
  );
}

export function SubjectInstitutionalTimeline() {
  const [events, setEvents] = useState<InstitutionalContextEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchSubjectInstitutionalTimeline()
      .then((items) => active && setEvents(items))
      .catch((requestError) => active && setError(errorMessage(requestError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  return (
    <section aria-labelledby="institutional-timeline-heading" className="border-t border-border pt-8">
      <div className="flex items-center gap-2"><Landmark aria-hidden="true" className="h-5 w-5 text-muted" /><h2 id="institutional-timeline-heading" className="text-xl font-semibold">Your institutional timeline</h2></div>
      <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">This shows certified institutional decisions and policy context that help explain how your current position developed. It does not replace your academic transcript or change a policy.</p>
      {loading && <p className="mt-5 text-sm text-muted">Loading institutional timeline...</p>}
      {error && <div role="alert" className="mt-5 flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {!loading && !error && events.length === 0 && <p className="mt-5 border-l-2 border-border pl-4 text-sm leading-relaxed text-muted">No certified institutional context events are available for your record.</p>}
      {!loading && !error && events.length > 0 && <div className="mt-7 space-y-0">{events.map((event) => <TimelineEvent key={event.event_id} event={event} />)}</div>}
      <p className="mt-7 flex items-start gap-2 border-t border-border pt-5 text-xs leading-relaxed text-muted"><ShieldCheck aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />Only independently certified, subject-safe institutional records appear here. Supporting evidence and internal handling notes are not displayed.</p>
    </section>
  );
}
