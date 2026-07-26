import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ClipboardCheck, FileText, Send, X } from 'lucide-react';
import {
  attestEvidenceFactProposal,
  createEvidenceFactProposal,
  fetchAdminDomains,
  fetchEvidenceFactProposals,
  fetchEvidenceSources,
  fetchFactReviewFields,
  type AdminDomain,
  type EvidenceFactProposal,
  type EvidenceSourceSummary,
  type RecordImportField,
} from '../api/client';

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'The evidence fact request could not be completed.';
}

function formatTimestamp(value?: string | null) {
  if (!value) return 'Recorded time unavailable';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function proposalStatusClass(status: EvidenceFactProposal['status']) {
  if (status === 'ACCEPTED') return 'border-emerald-200 bg-emerald-50 text-emerald-800';
  if (status === 'REJECTED') return 'border-rose-200 bg-rose-50 text-rose-800';
  return 'border-amber-200 bg-amber-50 text-amber-800';
}

export function EvidenceFactReview({
  canPropose,
  canAttest,
}: {
  canPropose: boolean;
  canAttest: boolean;
}) {
  const [domains, setDomains] = useState<AdminDomain[]>([]);
  const [domainId, setDomainId] = useState('');
  const [subjectId, setSubjectId] = useState('');
  const [sources, setSources] = useState<EvidenceSourceSummary[]>([]);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState('');
  const [fields, setFields] = useState<RecordImportField[]>([]);
  const [proposals, setProposals] = useState<EvidenceFactProposal[]>([]);
  const [targetPath, setTargetPath] = useState('');
  const [assertedValue, setAssertedValue] = useState('');
  const [sourceQuote, setSourceQuote] = useState('');
  const [sourceLocator, setSourceLocator] = useState('');
  const [attestationNotes, setAttestationNotes] = useState<Record<string, string>>({});
  const [loadingSources, setLoadingSources] = useState(false);
  const [loadingProposals, setLoadingProposals] = useState(false);
  const [saving, setSaving] = useState(false);
  const [attestingId, setAttestingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedField = useMemo(
    () => fields.find((field) => field.target_path === targetPath),
    [fields, targetPath],
  );

  useEffect(() => {
    void fetchAdminDomains()
      .then((items) => {
        setDomains(items);
        setDomainId(items[0]?.domain_id || '');
      })
      .catch((requestError) => setError(errorMessage(requestError)));
  }, []);

  useEffect(() => {
    if (!domainId) {
      setFields([]);
      return;
    }
    void fetchFactReviewFields(domainId)
      .then((items) => {
        setFields(items);
        setTargetPath(items[0]?.target_path || '');
        setAssertedValue(items[0]?.schema_type === 'boolean' ? 'true' : '');
      })
      .catch((requestError) => setError(errorMessage(requestError)));
  }, [domainId]);

  useEffect(() => {
    if (!domainId || !selectedEvidenceId) {
      setProposals([]);
      return;
    }
    setLoadingProposals(true);
    void fetchEvidenceFactProposals(domainId, selectedEvidenceId)
      .then(setProposals)
      .catch((requestError) => setError(errorMessage(requestError)))
      .finally(() => setLoadingProposals(false));
  }, [domainId, selectedEvidenceId]);

  const loadSources = async () => {
    if (!domainId || !subjectId.trim()) return;
    setLoadingSources(true);
    setError(null);
    setSelectedEvidenceId('');
    setProposals([]);
    try {
      const loaded = await fetchEvidenceSources(domainId, subjectId.trim());
      setSources(loaded);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoadingSources(false);
    }
  };

  const selectField = (path: string) => {
    const field = fields.find((candidate) => candidate.target_path === path);
    setTargetPath(path);
    setAssertedValue(field?.schema_type === 'boolean' ? 'true' : '');
  };

  const normalisedValue = () => {
    if (selectedField?.schema_type === 'number') return Number(assertedValue);
    if (selectedField?.schema_type === 'boolean') return assertedValue === 'true';
    return assertedValue.trim();
  };

  const valueIsValid = selectedField?.schema_type === 'number'
    ? assertedValue.trim() !== '' && Number.isFinite(Number(assertedValue))
    : assertedValue.trim() !== '';

  const submitProposal = async () => {
    if (!canPropose || !selectedEvidenceId || !targetPath || !valueIsValid || sourceQuote.trim().length < 3) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createEvidenceFactProposal({
        domain_id: domainId,
        evidence_id: selectedEvidenceId,
        target_path: targetPath,
        asserted_value: normalisedValue(),
        source_quote: sourceQuote.trim(),
        source_locator: sourceLocator.trim() || undefined,
      });
      setProposals((current) => [...current, created]);
      setSourceQuote('');
      setSourceLocator('');
      setAssertedValue(selectedField?.schema_type === 'boolean' ? 'true' : '');
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSaving(false);
    }
  };

  const attest = async (proposal: EvidenceFactProposal, action: 'ACCEPT' | 'REJECT') => {
    const note = attestationNotes[proposal.proposal_id]?.trim() || '';
    if (!canAttest || note.length < 10) return;
    setAttestingId(proposal.proposal_id);
    setError(null);
    try {
      const updated = await attestEvidenceFactProposal(proposal.proposal_id, domainId, action, note);
      setProposals((current) => current.map((item) => item.proposal_id === updated.proposal_id ? updated : item));
      setAttestationNotes((current) => ({ ...current, [proposal.proposal_id]: '' }));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setAttestingId(null);
    }
  };

  return <div className="mx-auto flex w-full max-w-6xl flex-col gap-7 py-4">
    <section className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
      <div className="flex items-start gap-3"><ClipboardCheck className="mt-0.5 h-5 w-5 text-muted" /><div><h2 className="text-2xl font-semibold">Evidence fact review</h2><p className="mt-1 text-sm text-muted">Cited facts require independent acceptance before evaluation.</p></div></div>
    </section>

    <section className="flex flex-wrap items-end gap-4 border-b border-border pb-5">
      <label className="grid gap-2 text-sm font-medium">Decision domain<select value={domainId} onChange={(event) => { setDomainId(event.target.value); setSources([]); setSelectedEvidenceId(''); }} className="min-w-60 rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">Select domain</option>{domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}</select></label>
      <label className="grid gap-2 text-sm font-medium">Subject institutional identifier<input value={subjectId} onChange={(event) => { setSubjectId(event.target.value); setSources([]); setSelectedEvidenceId(''); }} className="min-w-72 rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
      <button type="button" onClick={() => void loadSources()} disabled={!domainId || !subjectId.trim() || loadingSources} className="inline-flex h-10 items-center gap-2 rounded bg-primary px-4 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><FileText className="h-4 w-4" />{loadingSources ? 'Loading...' : 'Load sources'}</button>
    </section>

    {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
    {!loadingSources && subjectId.trim() && sources.length === 0 && <p className="border-l-2 border-border pl-4 text-sm text-muted">No preserved evidence was found for this subject in the selected domain.</p>}

    {sources.length > 0 && <section aria-labelledby="evidence-source-heading"><h3 id="evidence-source-heading" className="text-lg font-semibold">Preserved evidence</h3><div className="mt-4 divide-y divide-border border-y border-border">{sources.map((source) => <button key={source.evidence_id} type="button" onClick={() => setSelectedEvidenceId(source.evidence_id)} className={`grid w-full gap-1 px-3 py-4 text-left hover:bg-accent ${selectedEvidenceId === source.evidence_id ? 'bg-accent' : ''}`}><span className="text-sm font-medium">{source.source_type.replaceAll('_', ' ')}</span><span className="text-xs text-muted">{formatTimestamp(source.captured_at)} | {source.evidence_id}</span></button>)}</div></section>}

    {selectedEvidenceId && canPropose && <section className="border-y border-border py-6"><h3 className="text-lg font-semibold">Record a cited fact</h3><div className="mt-5 grid max-w-4xl gap-4"><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-sm font-medium">Declared fact<select value={targetPath} onChange={(event) => selectField(event.target.value)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">{fields.map((field) => <option key={field.target_path} value={field.target_path}>{field.label}</option>)}</select></label><label className="grid gap-2 text-sm font-medium">Value{selectedField?.schema_type === 'boolean' ? <select value={assertedValue} onChange={(event) => setAssertedValue(event.target.value)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="true">Yes</option><option value="false">No</option></select> : <input type={selectedField?.schema_type === 'number' ? 'number' : 'text'} value={assertedValue} onChange={(event) => setAssertedValue(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />}</label></div><label className="grid gap-2 text-sm font-medium">Exact source quotation<textarea value={sourceQuote} onChange={(event) => setSourceQuote(event.target.value)} minLength={3} maxLength={4000} rows={3} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Source location <span className="font-normal text-muted">Optional</span><input value={sourceLocator} onChange={(event) => setSourceLocator(event.target.value)} maxLength={500} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><button type="button" onClick={() => void submitProposal()} disabled={saving || !valueIsValid || sourceQuote.trim().length < 3} className="inline-flex w-fit items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><Send className="h-4 w-4" />{saving ? 'Submitting...' : 'Submit for independent acceptance'}</button></div></section>}

    {selectedEvidenceId && loadingProposals && <p className="text-sm text-muted">Loading fact review history...</p>}
    {selectedEvidenceId && !loadingProposals && proposals.length === 0 && <p className="border-l-2 border-border pl-4 text-sm text-muted">No fact proposals are recorded for this evidence.</p>}
    {selectedEvidenceId && proposals.length > 0 && <section aria-labelledby="fact-history-heading"><h3 id="fact-history-heading" className="text-lg font-semibold">Fact review history</h3><div className="mt-4 divide-y divide-border border-y border-border">{proposals.map((proposal) => { const note = attestationNotes[proposal.proposal_id] || ''; return <article key={proposal.proposal_id} className="py-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs text-muted">{proposal.target_path}</p><h4 className="mt-1 font-medium">{String(proposal.asserted_value)}</h4></div><span className={`border px-2 py-1 text-xs font-medium ${proposalStatusClass(proposal.status)}`}>{proposal.status.toLowerCase()}</span></div><blockquote className="mt-3 border-l-2 border-border pl-3 text-sm leading-relaxed text-muted">{proposal.source_quote}</blockquote>{proposal.source_locator && <p className="mt-2 text-xs text-muted">{proposal.source_locator}</p>}{proposal.status === 'PENDING' && canAttest && <div className="mt-5 grid max-w-2xl gap-3 border-t border-border pt-5"><label className="grid gap-2 text-sm font-medium">Independent review note<textarea value={note} onChange={(event) => setAttestationNotes((current) => ({ ...current, [proposal.proposal_id]: event.target.value }))} minLength={10} maxLength={4000} rows={3} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><div className="flex flex-wrap gap-3"><button type="button" onClick={() => void attest(proposal, 'ACCEPT')} disabled={attestingId === proposal.proposal_id || note.trim().length < 10} className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><CheckCircle2 className="h-4 w-4" />{attestingId === proposal.proposal_id ? 'Recording...' : 'Accept fact'}</button><button type="button" onClick={() => void attest(proposal, 'REJECT')} disabled={attestingId === proposal.proposal_id || note.trim().length < 10} className="inline-flex items-center gap-2 rounded border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40"><X className="h-4 w-4" />Reject fact</button></div></div>}{proposal.status === 'ACCEPTED' && <p className="mt-4 text-sm text-emerald-800">Independently accepted</p>}{proposal.status === 'REJECTED' && <p className="mt-4 text-sm text-muted">Not accepted</p>}</article>; })}</div></section>}
  </div>;
}
