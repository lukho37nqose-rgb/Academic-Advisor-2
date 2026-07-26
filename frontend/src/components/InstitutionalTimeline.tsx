import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Landmark,
  Plus,
  Send,
  ShieldCheck,
  X,
} from 'lucide-react';
import {
  attestInstitutionalContextEvent,
  createInstitutionalContextEvent,
  fetchAdminDomains,
  fetchCalibrationReleases,
  fetchStaffInstitutionalTimeline,
  type CalibrationRelease,
  type InstitutionalContextEvent,
  type InstitutionalContextEventInput,
  type InstitutionalContextEventType,
} from '../api/client';

const eventTypeLabels: Record<InstitutionalContextEventType, string> = {
  CONCESSION: 'Concession or authorised exception',
  CURRICULUM_APPLICABILITY: 'Curriculum applicability',
  ASSESSMENT_ACCOMMODATION: 'Assessment accommodation',
  APPEAL_OUTCOME: 'Appeal outcome',
  REGISTRATION_POSITION: 'Registration position',
  PROGRESSION_POSITION: 'Progression position',
  GRADUATION_POSITION: 'Graduation position',
  OTHER: 'Other institutional context',
};

function today() {
  return new Date().toISOString().slice(0, 10);
}

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'The institutional timeline request could not be completed.';
}

function timelineStateLabel(event: InstitutionalContextEvent) {
  return event.timeline_state.replaceAll('_', ' ');
}

function emptyDraft(domainId: string, subjectId: string): InstitutionalContextEventInput {
  return {
    domain_id: domainId,
    subject_id: subjectId,
    event_type: 'CONCESSION',
    title: '',
    student_summary: '',
    institutional_effect: '',
    authority_name: '',
    authority_reference: '',
    source_reference: '',
    event_date: today(),
    effective_from: today(),
    visibility: 'SUBJECT',
  };
}

export function InstitutionalTimeline({
  canRecord,
  canAttest,
}: {
  canRecord: boolean;
  canAttest: boolean;
}) {
  const [domains, setDomains] = useState<Array<{ domain_id: string; domain_name: string }>>([]);
  const [domainId, setDomainId] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [events, setEvents] = useState<InstitutionalContextEvent[]>([]);
  const [releases, setReleases] = useState<CalibrationRelease[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingTimeline, setLoadingTimeline] = useState(false);
  const [showRecord, setShowRecord] = useState(false);
  const [draft, setDraft] = useState<InstitutionalContextEventInput>(emptyDraft('', ''));
  const [submitting, setSubmitting] = useState(false);
  const [attestingId, setAttestingId] = useState<string | null>(null);
  const [attestationNotes, setAttestationNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchAdminDomains()
      .then((items) => {
        if (!active) return;
        setDomains(items);
        setDomainId(items[0]?.domain_id || '');
      })
      .catch((requestError) => active && setError(errorMessage(requestError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!domainId) {
      setReleases([]);
      return;
    }
    let active = true;
    void fetchCalibrationReleases(domainId)
      .then((items) => active && setReleases(items.filter((item) => item.calibration_ready)))
      .catch((requestError) => active && setError(errorMessage(requestError)));
    return () => { active = false; };
  }, [domainId]);

  const loadTimeline = async () => {
    if (!domainId || !subjectId.trim()) return;
    setLoadingTimeline(true);
    setError(null);
    try {
      setEvents(await fetchStaffInstitutionalTimeline(domainId, subjectId.trim()));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoadingTimeline(false);
    }
  };

  const openRecord = () => {
    setDraft(emptyDraft(domainId, subjectId.trim()));
    setShowRecord((current) => !current);
  };

  const submitRecord = async () => {
    if (!canRecord || !domainId || !subjectId.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createInstitutionalContextEvent({
        ...draft,
        domain_id: domainId,
        subject_id: subjectId.trim(),
        title: draft.title.trim(),
        student_summary: draft.student_summary.trim(),
        institutional_effect: draft.institutional_effect.trim(),
        authority_name: draft.authority_name.trim(),
        authority_reference: draft.authority_reference.trim(),
        source_reference: draft.source_reference.trim(),
        effective_until: draft.effective_until?.trim() || undefined,
        policy_release_id: draft.policy_release_id || undefined,
        policy_citation: draft.policy_citation?.trim() || undefined,
        predecessor_event_id: draft.predecessor_event_id || undefined,
        predecessor_relationship: draft.predecessor_event_id ? draft.predecessor_relationship : undefined,
      });
      setEvents((current) => [created, ...current]);
      setShowRecord(false);
      setDraft(emptyDraft(domainId, subjectId.trim()));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  const attest = async (event: InstitutionalContextEvent, action: 'CERTIFY' | 'REJECT') => {
    const note = attestationNotes[event.event_id]?.trim() || '';
    if (!canAttest || note.length < 10) return;
    setAttestingId(event.event_id);
    setError(null);
    try {
      const updated = await attestInstitutionalContextEvent(event.event_id, event.domain_id, action, note);
      setEvents((current) => current.map((item) => item.event_id === updated.event_id ? updated : item));
      setAttestationNotes((current) => ({ ...current, [event.event_id]: '' }));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setAttestingId(null);
    }
  };

  const canSubmit = canRecord
    && draft.title.trim().length >= 5
    && draft.student_summary.trim().length >= 10
    && draft.institutional_effect.trim().length >= 10
    && draft.authority_name.trim().length >= 3
    && draft.authority_reference.trim().length >= 3
    && draft.source_reference.trim().length >= 3;
  const eligiblePredecessors = events.filter((event) => event.status === 'CERTIFIED' && event.timeline_state === 'ACTIVE');

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-7 py-4">
      <section className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div className="flex items-start gap-3"><Landmark aria-hidden="true" className="mt-0.5 h-5 w-5 text-muted" /><div><h2 className="text-2xl font-semibold">Institutional timeline</h2><p className="mt-1 max-w-3xl text-sm text-muted">Certified institutional context that explains how a subject's position developed over time.</p></div></div>
        {canRecord && <button type="button" onClick={openRecord} disabled={!domainId || !subjectId.trim()} className="inline-flex items-center gap-2 rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40"><Plus className="h-4 w-4" />Record existing decision</button>}
      </section>

      <section className="flex flex-wrap items-end gap-4 border-b border-border pb-5">
        <label className="grid gap-2 text-sm font-medium">Decision domain<select value={domainId} onChange={(event) => { setDomainId(event.target.value); setEvents([]); }} className="min-w-60 rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">Select domain</option>{domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}</select></label>
        <label className="grid gap-2 text-sm font-medium">Subject institutional identifier<input value={subjectId} onChange={(event) => { setSubjectId(event.target.value); setEvents([]); }} className="min-w-72 rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
        <button type="button" onClick={() => void loadTimeline()} disabled={!domainId || !subjectId.trim() || loadingTimeline} className="inline-flex h-10 items-center gap-2 rounded bg-primary px-4 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><ChevronDown className="h-4 w-4" />{loadingTimeline ? 'Loading...' : 'Load timeline'}</button>
      </section>

      {showRecord && <section aria-labelledby="record-context-heading" className="border-y border-border py-6"><div className="flex items-center justify-between gap-4"><h3 id="record-context-heading" className="text-lg font-semibold">Record an existing institutional decision</h3><button type="button" onClick={() => setShowRecord(false)} className="rounded p-1 text-muted hover:bg-accent hover:text-primary" aria-label="Close record form"><X className="h-4 w-4" /></button></div><p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">This record does not grant a concession or change a subject's institutional position. It documents an already-authorised decision for independent certification.</p><div className="mt-6 grid max-w-4xl gap-5"><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-sm font-medium">Context type<select value={draft.event_type} onChange={(event) => setDraft((current) => ({ ...current, event_type: event.target.value as InstitutionalContextEventType }))} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">{Object.entries(eventTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="grid gap-2 text-sm font-medium">Student visibility<select value={draft.visibility} onChange={(event) => setDraft((current) => ({ ...current, visibility: event.target.value as 'SUBJECT' | 'STAFF_ONLY' }))} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="SUBJECT">Subject-safe explanation</option><option value="STAFF_ONLY">Staff only</option></select></label></div><label className="grid gap-2 text-sm font-medium">Timeline title<input value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} maxLength={240} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Subject-safe explanation<textarea value={draft.student_summary} onChange={(event) => setDraft((current) => ({ ...current, student_summary: event.target.value }))} minLength={10} maxLength={4000} rows={3} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Institutional effect<textarea value={draft.institutional_effect} onChange={(event) => setDraft((current) => ({ ...current, institutional_effect: event.target.value }))} minLength={10} maxLength={4000} rows={3} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-sm font-medium">Decision authority<input value={draft.authority_name} onChange={(event) => setDraft((current) => ({ ...current, authority_name: event.target.value }))} maxLength={240} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Authority reference<input value={draft.authority_reference} onChange={(event) => setDraft((current) => ({ ...current, authority_reference: event.target.value }))} maxLength={500} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label></div><label className="grid gap-2 text-sm font-medium">Source decision reference<input value={draft.source_reference} onChange={(event) => setDraft((current) => ({ ...current, source_reference: event.target.value }))} maxLength={1000} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><div className="grid gap-4 sm:grid-cols-3"><label className="grid gap-2 text-sm font-medium">Decision date<input type="date" value={draft.event_date} onChange={(event) => setDraft((current) => ({ ...current, event_date: event.target.value }))} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Effective from<input type="date" value={draft.effective_from} onChange={(event) => setDraft((current) => ({ ...current, effective_from: event.target.value }))} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Effective until <span className="font-normal text-muted">Optional</span><input type="date" value={draft.effective_until || ''} onChange={(event) => setDraft((current) => ({ ...current, effective_until: event.target.value || undefined }))} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label></div><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-sm font-medium">Related signed policy release <span className="font-normal text-muted">Optional</span><select value={draft.policy_release_id || ''} onChange={(event) => setDraft((current) => ({ ...current, policy_release_id: event.target.value || undefined }))} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">No linked release</option>{releases.map((release) => <option key={release.release_id} value={release.release_id}>Release {release.version}</option>)}</select></label><label className="grid gap-2 text-sm font-medium">Policy citation <span className="font-normal text-muted">Optional</span><input value={draft.policy_citation || ''} onChange={(event) => setDraft((current) => ({ ...current, policy_citation: event.target.value || undefined }))} maxLength={2000} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label></div>{eligiblePredecessors.length > 0 && <div className="grid gap-4 border-t border-border pt-5 sm:grid-cols-2"><label className="grid gap-2 text-sm font-medium">Earlier active event <span className="font-normal text-muted">Optional</span><select value={draft.predecessor_event_id || ''} onChange={(event) => setDraft((current) => ({ ...current, predecessor_event_id: event.target.value || undefined, predecessor_relationship: event.target.value ? current.predecessor_relationship || 'SUPERSEDES' : undefined }))} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">Does not replace an earlier event</option>{eligiblePredecessors.map((event) => <option key={event.event_id} value={event.event_id}>{event.title}</option>)}</select></label>{draft.predecessor_event_id && <label className="grid gap-2 text-sm font-medium">Effect on earlier event<select value={draft.predecessor_relationship || 'SUPERSEDES'} onChange={(event) => setDraft((current) => ({ ...current, predecessor_relationship: event.target.value as 'SUPERSEDES' | 'REVOKES' }))} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="SUPERSEDES">Supersedes it</option><option value="REVOKES">Concludes or revokes it</option></select></label>}</div>}</div><button type="button" onClick={() => void submitRecord()} disabled={!canSubmit || submitting} className="mt-6 inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><Send className="h-4 w-4" />{submitting ? 'Submitting...' : 'Submit for independent certification'}</button></section>}

      {loading && <p className="text-sm text-muted">Loading institutional timeline workspace...</p>}
      {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {!loading && !loadingTimeline && subjectId.trim() && events.length === 0 && <p className="border-l-2 border-border pl-4 text-sm text-muted">No institutional context events were found for this subject in the selected domain.</p>}
      {!loading && events.length > 0 && <section aria-labelledby="timeline-records-heading"><h3 id="timeline-records-heading" className="text-lg font-semibold">Recorded institutional history</h3><div className="mt-4 divide-y divide-border border-y border-border">{events.map((event) => { const note = attestationNotes[event.event_id] || ''; return <article key={event.event_id} className="py-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-medium text-muted">{event.event_date} | {eventTypeLabels[event.event_type]}</p><h4 className="mt-1 text-base font-semibold">{event.title}</h4></div><span className="text-sm font-medium">{timelineStateLabel(event)}</span></div><p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">{event.student_summary}</p><dl className="mt-4 grid gap-3 border-l-2 border-border pl-4 text-sm sm:grid-cols-2"><div><dt className="font-medium">Institutional effect</dt><dd className="mt-1 text-muted">{event.institutional_effect}</dd></div><div><dt className="font-medium">Authority</dt><dd className="mt-1 text-muted">{event.authority_name}</dd></div><div><dt className="font-medium">Authority reference</dt><dd className="mt-1 text-muted">{event.authority_reference}</dd></div><div><dt className="font-medium">Source decision reference</dt><dd className="mt-1 text-muted">{event.source_reference}</dd></div>{event.policy_release_version && <div><dt className="font-medium">Related release</dt><dd className="mt-1 text-muted">{event.policy_release_version}</dd></div>}</dl>{event.status === 'SUBMITTED' && canAttest && <div className="mt-5 grid max-w-2xl gap-3 border-t border-border pt-5"><label className="grid gap-2 text-sm font-medium">Independent attestation note<textarea value={note} onChange={(input) => setAttestationNotes((current) => ({ ...current, [event.event_id]: input.target.value }))} minLength={10} maxLength={4000} rows={3} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><div className="flex flex-wrap gap-3"><button type="button" disabled={attestingId === event.event_id || note.trim().length < 10} onClick={() => void attest(event, 'CERTIFY')} className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><ShieldCheck className="h-4 w-4" />{attestingId === event.event_id ? 'Recording...' : 'Certify record'}</button><button type="button" disabled={attestingId === event.event_id || note.trim().length < 10} onClick={() => void attest(event, 'REJECT')} className="inline-flex items-center gap-2 rounded border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40"><X className="h-4 w-4" />Reject record</button></div></div>}{event.status === 'CERTIFIED' && <p className="mt-5 flex items-center gap-2 text-sm text-emerald-800"><CheckCircle2 className="h-4 w-4" />Independently certified</p>}{event.status === 'REJECTED' && <p className="mt-5 text-sm text-muted">The submitted record was not certified.</p>}</article>; })}</div></section>}
    </div>
  );
}
