import { useEffect, useState } from 'react';
import { AlertTriangle, ArrowLeft, CheckCircle2, ClipboardCheck, Send } from 'lucide-react';
import {
  fetchPendingPolicyReviews,
  fetchPolicyReview,
  publishPolicyDraft,
  type PendingPolicyReview,
  type PolicyReview as PolicyReviewData,
  type PublicPolicyNode,
} from '../api/client';

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Policy review could not be loaded.';
}

function displayValue(value: string | number | boolean | null) {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (value === null) return 'Not specified';
  return String(value);
}

function ReviewNode({ node }: { node: PublicPolicyNode }) {
  if (node.kind === 'group') {
    const label = node.mode === 'all' ? 'All conditions' : node.mode === 'any' ? 'At least one condition' : node.label;
    return <section className="space-y-3 border-l-2 border-border pl-4"><h3 className="text-sm font-semibold">{label}</h3>{node.children.map((child, index) => <ReviewNode key={`${child.kind}-${index}`} node={child} />)}</section>;
  }
  return <article className="border-b border-border pb-4"><h3 className="text-sm font-semibold">{node.label}</h3><p className="mt-2 text-sm">{node.fact_label} {node.operator} <strong>{displayValue(node.expected_value)}</strong></p>{node.citation && <p className="mt-2 text-xs text-muted">Source: {node.citation}</p>}</article>;
}

export function PolicyReview({ canPublish }: { canPublish: boolean }) {
  const [reviews, setReviews] = useState<PendingPolicyReview[]>([]);
  const [review, setReview] = useState<PolicyReviewData | null>(null);
  const [version, setVersion] = useState('');
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [effectiveUntil, setEffectiveUntil] = useState('');
  const [applicabilityAttribute, setApplicabilityAttribute] = useState('');
  const [applicabilityValues, setApplicabilityValues] = useState('');
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [publishedVersion, setPublishedVersion] = useState<string | null>(null);

  const loadReviews = async () => {
    setLoading(true);
    setError(null);
    try {
      setReviews(await fetchPendingPolicyReviews());
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadReviews(); }, []);

  const openReview = async (draftId: string) => {
    setLoading(true);
    setError(null);
    setPublishedVersion(null);
    try {
      setReview(await fetchPolicyReview(draftId));
      setVersion('');
      setEffectiveFrom('');
      setEffectiveUntil('');
      setApplicabilityAttribute('');
      setApplicabilityValues('');
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  const publish = async () => {
    if (!canPublish) return;
    const hasApplicability = applicabilityAttribute.trim() || applicabilityValues.trim();
    if (!review || !version.trim() || !effectiveFrom || (hasApplicability && (!applicabilityAttribute.trim() || !applicabilityValues.trim()))) return;
    setPublishing(true);
    setError(null);
    try {
      const values = applicabilityValues.split(',').map((value) => value.trim()).filter(Boolean);
      const publication = await publishPolicyDraft(review.draft_id, {
        version: version.trim(),
        effectiveFrom,
        ...(effectiveUntil ? { effectiveUntil } : {}),
        ...(applicabilityAttribute.trim() && values.length > 0
          ? { applicability: [{ attribute: applicabilityAttribute.trim(), values }] }
          : {}),
      });
      setPublishedVersion(publication.version);
      setReviews((current) => current.filter((item) => item.draft_id !== review.draft_id));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setPublishing(false);
    }
  };

  if (review) {
    return <div className="mx-auto flex w-full max-w-4xl flex-col gap-7 py-4">
      <section className="border-b border-border pb-5">
        <button type="button" onClick={() => { setReview(null); setPublishedVersion(null); }} className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-primary"><ArrowLeft className="h-4 w-4" />All pending reviews</button>
        <div className="flex items-start gap-3"><ClipboardCheck className="mt-0.5 h-5 w-5 text-muted" /><div><h2 className="text-2xl font-semibold">{review.policy_name}</h2><p className="mt-1 text-sm text-muted">{review.domain_name} · Submitted by {review.author_id}</p></div></div>
      </section>
      {publishedVersion ? <div role="status" className="flex items-start gap-2 border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />Published as immutable release {publishedVersion}.</div> : <>
        <section className="space-y-5"><h3 className="text-base font-semibold">Policy conditions</h3><ReviewNode node={review.policy} /></section>
        {canPublish ? <section className="flex flex-wrap items-end gap-3 border-t border-border pt-6">
          <label className="grid gap-2 text-sm font-medium">Release version<input aria-label="Release version" value={version} onChange={(event) => setVersion(event.target.value)} placeholder="2026.1" className="w-40 rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
          <label className="grid gap-2 text-sm font-medium">Effective from<input aria-label="Effective from" type="date" value={effectiveFrom} onChange={(event) => setEffectiveFrom(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
          <label className="grid gap-2 text-sm font-medium">Effective until<input aria-label="Effective until" type="date" value={effectiveUntil} onChange={(event) => setEffectiveUntil(event.target.value)} min={effectiveFrom || undefined} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
          <label className="grid gap-2 text-sm font-medium">Applies when<input aria-label="Applicability attribute" value={applicabilityAttribute} onChange={(event) => setApplicabilityAttribute(event.target.value)} placeholder="Entry year" className="w-36 rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
          <label className="grid gap-2 text-sm font-medium">Matching values<input aria-label="Applicability values" value={applicabilityValues} onChange={(event) => setApplicabilityValues(event.target.value)} placeholder="2026, 2027" className="w-40 rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
          <button type="button" onClick={() => void publish()} disabled={publishing || !version.trim() || !effectiveFrom || (Boolean(applicabilityAttribute.trim() || applicabilityValues.trim()) && (!applicabilityAttribute.trim() || !applicabilityValues.trim()))} className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><Send className="h-4 w-4" />{publishing ? 'Publishing...' : 'Approve and publish'}</button>
        </section> : <p className="border-l-2 border-border pl-3 text-sm text-muted">This account may inspect pending policy conditions but cannot approve or publish a release.</p>}
      </>}
      {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
    </div>;
  }

  return <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 py-4">
    <section className="flex items-center gap-3 border-b border-border pb-5"><ClipboardCheck className="h-5 w-5 text-muted" /><div><h2 className="text-2xl font-semibold">Policy review</h2><p className="mt-1 text-sm text-muted">Pending releases</p></div></section>
    {loading && <p className="text-sm text-muted">Loading pending reviews...</p>}
    {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
    {!loading && !error && reviews.length === 0 && <p className="text-sm text-muted">No policy drafts are awaiting review.</p>}
    <div className="divide-y divide-border border-y border-border">{reviews.map((item) => <button key={item.draft_id} type="button" onClick={() => void openReview(item.draft_id)} className="flex w-full items-center justify-between gap-4 px-1 py-4 text-left hover:bg-accent"><span><span className="block font-medium">{item.policy_name}</span><span className="mt-1 block text-sm text-muted">{item.domain_name}</span></span><span className="text-sm text-muted">Review</span></button>)}</div>
  </div>;
}
