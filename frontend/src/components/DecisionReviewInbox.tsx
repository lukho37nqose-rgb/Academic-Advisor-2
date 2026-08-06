import { useEffect, useState } from 'react';
import { CheckCircle2, Clock3, FileSearch, Send, X } from 'lucide-react';
import {
  fetchAdminDomains,
  fetchDecisionReviewCases,
  updateDecisionReviewCase,
  type DecisionReviewCase,
  type DecisionReviewResolution,
  type DecisionReviewStatus,
} from '../api/client';

const categoryLabels: Record<DecisionReviewCase['category'], string> = {
  evidence_correction: 'Evidence correction',
  missing_evidence: 'Missing evidence',
  policy_interpretation: 'Policy interpretation',
  exceptional_circumstance: 'Exceptional circumstance',
  explanation_accessibility: 'Explanation or accessibility',
};

const resolutionOptions: Array<{ value: DecisionReviewResolution; label: string }> = [
  { value: 'DECISION_CONFIRMED', label: 'Decision confirmed' },
  { value: 'RE_EVALUATION_REQUIRED', label: 'New evaluation required' },
  { value: 'POLICY_CLARIFICATION_PROVIDED', label: 'Policy clarification provided' },
  { value: 'EXCEPTION_REFERRED', label: 'Exception referred' },
  { value: 'OUT_OF_SCOPE', label: 'Outside this process' },
];

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'The review case could not be updated.';
}

function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString() : 'Not recorded';
}

export function DecisionReviewInbox({ canManage }: { canManage: boolean }) {
  const [domains, setDomains] = useState<Array<{ domain_id: string; domain_name: string }>>([]);
  const [domainId, setDomainId] = useState('');
  const [cases, setCases] = useState<DecisionReviewCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolution, setResolution] = useState<DecisionReviewResolution>('DECISION_CONFIRMED');
  const [responseMessage, setResponseMessage] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchAdminDomains()
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
      setCases([]);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    fetchDecisionReviewCases(domainId)
      .then((items) => active && setCases(items))
      .catch((requestError) => active && setError(errorMessage(requestError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [domainId]);

  const transition = async (
    reviewCase: DecisionReviewCase,
    nextStatus: Exclude<DecisionReviewStatus, 'SUBMITTED'>,
    nextResolution?: DecisionReviewResolution,
    nextResponseMessage?: string,
  ) => {
    if (!canManage) return;
    setUpdatingId(reviewCase.id);
    setError(null);
    try {
      const updated = await updateDecisionReviewCase(
        reviewCase.id,
        reviewCase.domain_id,
        nextStatus,
        nextResolution,
        nextResponseMessage,
      );
      setCases((current) => current.map((item) => item.id === updated.id ? updated : item));
      setResolvingId(null);
      setResponseMessage('');
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div className="flex items-center gap-3">
          <FileSearch className="h-5 w-5 text-muted" />
          <div>
            <h2 className="text-xl font-semibold">Decision review cases</h2>
            <p className="mt-1 text-sm text-muted">Assigned institutional casework</p>
          </div>
        </div>
        <label className="grid gap-2 text-sm font-medium">
          Domain
          <select aria-label="Review case domain" value={domainId} onChange={(event) => setDomainId(event.target.value)} className="min-w-64 rounded border border-border bg-white px-3 py-2 outline-none focus:border-primary">
            {domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}
          </select>
        </label>
      </section>

      {error && <div className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><X className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {!loading && domainId && cases.length === 0 && <p className="py-8 text-sm text-muted">No decision review cases in this domain.</p>}

      {!loading && cases.length > 0 && <div className="overflow-x-auto border-y border-border">
        <table className="w-full min-w-[960px] text-left text-sm">
          <thead className="border-b border-border bg-accent text-xs font-medium uppercase tracking-wide text-muted">
            <tr>
              <th scope="col" className="px-3 py-3">Received</th>
              <th scope="col" className="px-3 py-3">Case</th>
              <th scope="col" className="px-3 py-3">Trace</th>
              <th scope="col" className="px-3 py-3">Response due</th>
              <th scope="col" className="px-3 py-3">Status</th>
              <th scope="col" className="px-3 py-3">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {cases.map((reviewCase) => (
              <tr key={reviewCase.id} className="align-top hover:bg-accent/50">
                <td className="whitespace-nowrap px-3 py-4 text-muted">{formatDate(reviewCase.created_at)}</td>
                <td className="max-w-[410px] px-3 py-4">
                  <p className="font-medium">{categoryLabels[reviewCase.category]}</p>
                  <p className="mt-1 leading-relaxed">{reviewCase.message}</p>
                  {reviewCase.responsible_group && <p className="mt-2 text-xs text-muted">Responsible group: {reviewCase.responsible_group}{reviewCase.fallback_group ? ` · fallback: ${reviewCase.fallback_group}` : ''}</p>}
                  {reviewCase.disputed_fact_paths.length > 0 && <p className="mt-2 text-xs text-muted">Facts: {reviewCase.disputed_fact_paths.join(', ')}</p>}
                  {reviewCase.response_message && <p className="mt-2 border-l-2 border-primary pl-2 text-muted">{reviewCase.response_message}</p>}
                </td>
                <td className="px-3 py-4 font-mono text-xs text-muted">{reviewCase.reasoning_graph_id}</td>
                <td className={`whitespace-nowrap px-3 py-4 ${reviewCase.is_overdue ? 'font-medium text-rose-700' : 'text-muted'}`}>
                  <span className="inline-flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" />{formatDate(reviewCase.response_due_at)}</span>
                </td>
                <td className={`whitespace-nowrap px-3 py-4 font-medium ${reviewCase.is_escalated ? 'text-rose-700' : ''}`}>{reviewCase.is_escalated ? 'Escalation due' : reviewCase.status.replace('_', ' ')}</td>
                <td className="px-3 py-4">
                  {canManage && reviewCase.status === 'SUBMITTED' && <button type="button" disabled={updatingId === reviewCase.id} onClick={() => void transition(reviewCase, 'ACKNOWLEDGED')} className="inline-flex items-center gap-2 rounded border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-40"><CheckCircle2 className="h-4 w-4" />Acknowledge</button>}
                  {canManage && reviewCase.status === 'ACKNOWLEDGED' && <button type="button" disabled={updatingId === reviewCase.id} onClick={() => void transition(reviewCase, 'UNDER_REVIEW')} className="inline-flex items-center gap-2 rounded border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-40"><FileSearch className="h-4 w-4" />Begin review</button>}
                  {canManage && reviewCase.status === 'UNDER_REVIEW' && resolvingId !== reviewCase.id && <button type="button" disabled={updatingId === reviewCase.id} onClick={() => setResolvingId(reviewCase.id)} className="inline-flex items-center gap-2 rounded border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-40"><Send className="h-4 w-4" />Resolve</button>}
                  {canManage && reviewCase.status === 'RESOLVED' && <button type="button" disabled={updatingId === reviewCase.id} onClick={() => void transition(reviewCase, 'CLOSED')} className="inline-flex items-center gap-2 rounded border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-40"><CheckCircle2 className="h-4 w-4" />Close case</button>}
                  {reviewCase.status === 'CLOSED' && <span className="text-muted">Closed</span>}
                  {canManage && resolvingId === reviewCase.id && <div className="mt-3 grid min-w-80 gap-2">
                    <select aria-label={`Resolution for case ${reviewCase.id}`} value={resolution} onChange={(event) => setResolution(event.target.value as DecisionReviewResolution)} className="rounded border border-border bg-white px-2 py-1.5 outline-none focus:border-primary">
                      {resolutionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                    <textarea aria-label={`Response for case ${reviewCase.id}`} value={responseMessage} onChange={(event) => setResponseMessage(event.target.value)} rows={3} className="resize-y rounded border border-border px-2 py-1.5 outline-none focus:border-primary" />
                    <div className="flex gap-2">
                      <button type="button" disabled={!responseMessage.trim() || updatingId === reviewCase.id} onClick={() => void transition(reviewCase, 'RESOLVED', resolution, responseMessage.trim())} className="inline-flex items-center gap-2 rounded bg-primary px-3 py-1.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><Send className="h-4 w-4" />Record response</button>
                      <button type="button" onClick={() => { setResolvingId(null); setResponseMessage(''); }} className="rounded border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent">Cancel</button>
                    </div>
                  </div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>}
    </div>
  );
}
