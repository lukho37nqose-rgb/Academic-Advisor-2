import { type FormEvent, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock3, Send } from 'lucide-react';
import {
  fetchDecisionReviewCases,
  submitDecisionReview,
  type DecisionReviewCase,
  type ReasoningGraph,
} from '../api/client';

type ReviewCategory = DecisionReviewCase['category'];

const categories: Array<{ value: ReviewCategory; label: string }> = [
  { value: 'evidence_correction', label: 'A fact or record is incorrect' },
  { value: 'missing_evidence', label: 'Relevant evidence is missing' },
  { value: 'policy_interpretation', label: 'I need a policy interpretation checked' },
  { value: 'exceptional_circumstance', label: 'My circumstances need human consideration' },
  { value: 'explanation_accessibility', label: 'I cannot use this explanation as presented' },
];

const statusLabels: Record<DecisionReviewCase['status'], string> = {
  SUBMITTED: 'Submitted',
  ACKNOWLEDGED: 'Acknowledged',
  UNDER_REVIEW: 'Under review',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
};

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'The review request could not be recorded.';
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function SubjectDecisionReview({ graph }: { graph: ReasoningGraph }) {
  const domainId = graph.evaluation_context?.domain_id;
  const factPaths = useMemo(
    () => Object.values(graph.nodes)
      .filter((node) => node.type === 'fact')
      .map((node) => node.label.replace(/^Fact:\s*/, ''))
      .filter((value, index, values) => value.length > 0 && values.indexOf(value) === index),
    [graph.nodes],
  );
  const [cases, setCases] = useState<DecisionReviewCase[]>([]);
  const [category, setCategory] = useState<ReviewCategory>('evidence_correction');
  const [message, setMessage] = useState('');
  const [disputedFacts, setDisputedFacts] = useState<string[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedCase, setSubmittedCase] = useState<DecisionReviewCase | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const loadedCases = await fetchDecisionReviewCases();
        if (!cancelled) {
          setCases(loadedCases.filter((reviewCase) => reviewCase.reasoning_graph_id === graph.id));
        }
      } catch (requestError) {
        if (!cancelled) setError(errorMessage(requestError));
      } finally {
        if (!cancelled) setLoadingCases(false);
      }
    })();
    return () => { cancelled = true; };
  }, [graph.id]);

  const toggleFact = (factPath: string) => {
    setDisputedFacts((current) => current.includes(factPath)
      ? current.filter((item) => item !== factPath)
      : [...current, factPath]);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!domainId) return;
    setSending(true);
    setError(null);
    try {
      const created = await submitDecisionReview({
        domain_id: domainId,
        reasoning_graph_id: graph.id,
        category,
        message: message.trim(),
        ...(disputedFacts.length > 0 ? { disputed_fact_paths: disputedFacts } : {}),
      });
      setSubmittedCase(created);
      setCases((current) => [created, ...current]);
      setMessage('');
      setDisputedFacts([]);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSending(false);
    }
  };

  if (!domainId) return null;

  return (
    <section aria-labelledby="review-heading" className="mt-10 border-t border-border pt-6">
      <div className="flex items-center gap-3">
        <Clock3 className="h-5 w-5 text-muted" />
        <div>
          <h2 id="review-heading" className="text-lg font-semibold">Request a decision review</h2>
          <p className="mt-1 text-sm text-muted">Decision trace {graph.id}</p>
        </div>
      </div>

      {error && <div role="alert" className="mt-5 flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}

      {submittedCase && (
        <div role="status" aria-live="polite" className="mt-5 flex items-start gap-2 border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Review request recorded. Reference: {submittedCase.id}.</span>
        </div>
      )}

      <form onSubmit={submit} className="mt-6 grid max-w-2xl gap-4">
        <label className="grid gap-2 text-sm font-medium">
          What needs review?
          <select value={category} onChange={(event) => setCategory(event.target.value as ReviewCategory)} className="w-full rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">
            {categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>

        {factPaths.length > 0 && (
          <fieldset className="grid gap-2">
            <legend className="text-sm font-medium">Facts to check <span className="font-normal text-muted">Optional</span></legend>
            <div className="grid gap-2 border-l-2 border-border pl-4">
              {factPaths.map((factPath) => (
                <label key={factPath} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={disputedFacts.includes(factPath)} onChange={() => toggleFact(factPath)} className="h-4 w-4" />
                  {factPath}
                </label>
              ))}
            </div>
          </fieldset>
        )}

        <label className="grid gap-2 text-sm font-medium">
          Tell us what should be checked
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={6} minLength={10} maxLength={4000} required className="w-full resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
        </label>
        <button type="submit" disabled={sending || message.trim().length < 10} className="inline-flex w-fit items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
          <Send className="h-4 w-4" />
          {sending ? 'Recording request...' : 'Request review'}
        </button>
      </form>

      {!loadingCases && cases.length > 0 && (
        <div className="mt-8 max-w-2xl border-t border-border pt-5">
          <h3 className="text-sm font-semibold">Your review requests for this decision</h3>
          <div className="mt-3 divide-y divide-border border-y border-border">
            {cases.map((reviewCase) => (
              <article key={reviewCase.id} className="py-4 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium">{statusLabels[reviewCase.status]}</span>
                  {reviewCase.response_due_at && <span className="text-muted">Response target: {formatDate(reviewCase.response_due_at)}</span>}
                </div>
                <p className="mt-2 leading-relaxed">{reviewCase.message}</p>
                {reviewCase.response_message && <p className="mt-2 border-l-2 border-border pl-3 text-muted">{reviewCase.response_message}</p>}
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
