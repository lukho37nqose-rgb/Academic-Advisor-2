import { type FormEvent, useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  CircleHelp,
  FileText,
  Send,
} from 'lucide-react';
import {
  fetchPublicPolicyGuide,
  fetchPublicPolicyGuides,
  requestPublicPolicySupport,
  type PublicPolicyGuide as PolicyGuide,
  type PublicPolicyGuideListItem,
  type PublicPolicyNode,
  type PublicSupportRequestPayload,
} from '../api/client';

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Policy guide could not be loaded.';
}

function displayValue(value: string | number | boolean | null) {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (value === null) return 'Not specified';
  return String(value);
}

function PolicyNodeView({ node }: { node: PublicPolicyNode }) {
  if (node.kind === 'group') {
    const label = node.mode === 'all' ? 'All of these conditions apply' : node.mode === 'any' ? 'At least one of these conditions applies' : node.label;
    return (
      <section className="space-y-3 border-l-2 border-border pl-4">
        <h3 className="text-sm font-semibold">{label}</h3>
        {node.children.map((child, index) => <PolicyNodeView key={`${child.kind}-${index}`} node={child} />)}
      </section>
    );
  }
  return (
    <article className="border-b border-border pb-4">
      <h3 className="text-sm font-semibold">{node.label}</h3>
      <p className="mt-2 text-sm text-primary">{node.fact_label} {node.operator} <strong>{displayValue(node.expected_value)}</strong></p>
      {node.citation && <p className="mt-2 text-xs text-muted">Source: {node.citation}</p>}
    </article>
  );
}

export function PublicPolicyGuide() {
  const [guides, setGuides] = useState<PublicPolicyGuideListItem[]>([]);
  const [guide, setGuide] = useState<PolicyGuide | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<PublicSupportRequestPayload['category']>('unique_circumstance');
  const [contactDetails, setContactDetails] = useState('');
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [supportSent, setSupportSent] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        setGuides(await fetchPublicPolicyGuides());
      } catch (requestError) {
        setError(errorMessage(requestError));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selectGuide = async (domainId: string) => {
    setLoading(true);
    setError(null);
    setSupportSent(false);
    try {
      setGuide(await fetchPublicPolicyGuide(domainId));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  const submitSupport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!guide) return;
    setSending(true);
    setError(null);
    try {
      await requestPublicPolicySupport(guide.domain_id, {
        category,
        contact_details: contactDetails.trim() || undefined,
        message: message.trim(),
      });
      setSupportSent(true);
      setMessage('');
      setContactDetails('');
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSending(false);
    }
  };

  if (guide) {
    const governedPersonLabel = guide.governed_person_label?.trim();
    const individualCase = governedPersonLabel && governedPersonLabel.toLowerCase() !== 'person'
      ? `a case for an individual ${governedPersonLabel}`
      : 'an individual case';
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 py-4">
        <section className="border-b border-border pb-6">
          <button type="button" onClick={() => { setGuide(null); setSupportSent(false); }} className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-primary">
            <ArrowLeft className="h-4 w-4" />
            All policy guides
          </button>
          <div className="flex items-start gap-3">
            <FileText className="mt-0.5 h-5 w-5 text-muted" />
            <div>
              <h2 className="text-2xl font-semibold">{guide.domain_name}</h2>
              <p className="mt-1 text-sm text-muted">Approved policy version {guide.version}</p>
            </div>
          </div>
        </section>

        <p className="border-l-2 border-primary pl-4 text-sm leading-relaxed text-muted">
          This guide explains the approved policy. It does not decide {individualCase}.
        </p>

        <section className="space-y-5">
          <h3 className="text-base font-semibold">Policy conditions</h3>
          <PolicyNodeView node={guide.policy} />
        </section>

        {guide.assistance_requests_enabled && (
          <section className="border-t border-border pt-6">
            <div className="mb-5 flex items-center gap-2">
              <CircleHelp className="h-5 w-5 text-muted" />
              <h3 className="text-base font-semibold">Request human assistance</h3>
            </div>
            <div className="mb-5 space-y-2 text-sm leading-relaxed text-muted">
              {guide.support_response_target_hours && <p>Response target: within {guide.support_response_target_hours} hours.</p>}
              {guide.offline_assistance_instructions && <p>{guide.offline_assistance_instructions}</p>}
              {guide.support_privacy_notice_url && <a href={guide.support_privacy_notice_url} target="_blank" rel="noreferrer" className="font-medium text-primary underline underline-offset-4">Privacy notice</a>}
            </div>
            {supportSent ? (
              <div role="status" aria-live="polite" className="flex items-start gap-2 border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                <span>Your request has been recorded for human follow-up.</span>
              </div>
            ) : (
              <form onSubmit={submitSupport} className="grid max-w-2xl gap-4">
                <label className="space-y-2 text-sm font-medium">
                  What kind of help do you need?
                  <select value={category} onChange={(event) => setCategory(event.target.value as PublicSupportRequestPayload['category'])} className="w-full rounded border border-border bg-white px-3 py-2 outline-none focus:border-primary">
                    <option value="missing_information">I cannot access the information needed</option>
                    <option value="unique_circumstance">My circumstances are not covered here</option>
                    <option value="accessibility">I need an accessibility accommodation</option>
                    <option value="other">Something else</option>
                  </select>
                </label>
                <label className="space-y-2 text-sm font-medium">
                  Contact details <span className="font-normal text-muted">Optional</span>
                  <input value={contactDetails} onChange={(event) => setContactDetails(event.target.value)} className="w-full rounded border border-border px-3 py-2 outline-none focus:border-primary" />
                </label>
                <label className="space-y-2 text-sm font-medium">
                  What is missing or different?
                  <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={5} minLength={10} required className="w-full resize-y rounded border border-border px-3 py-2 outline-none focus:border-primary" />
                </label>
                <p className="text-xs leading-relaxed text-muted">Do not include supporting documents, account details, or other sensitive evidence here.</p>
                <button type="submit" disabled={sending || message.trim().length < 10} className="inline-flex w-fit items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
                  <Send className="h-4 w-4" />
                  {sending ? 'Sending...' : 'Request assistance'}
                </button>
              </form>
            )}
          </section>
        )}

        {error && <div className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-8 py-4">
      <section className="border-b border-border pb-6">
        <div className="flex items-center gap-3">
          <FileText className="h-5 w-5 text-muted" />
          <div>
            <h2 className="text-2xl font-semibold">Policy guides</h2>
            <p className="mt-1 text-sm text-muted">Approved institutional policy, with source citations</p>
          </div>
        </div>
      </section>
      {loading && <p className="text-sm text-muted">Loading policy guides...</p>}
      {error && <div className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {!loading && !error && guides.length === 0 && <p className="text-sm text-muted">No approved public policy guides are available.</p>}
      <div className="divide-y divide-border border-y border-border">
        {guides.map((item) => (
          <button key={item.domain_id} type="button" onClick={() => void selectGuide(item.domain_id)} className="flex w-full items-center justify-between gap-4 px-1 py-4 text-left hover:bg-accent">
            <span className="font-medium">{item.domain_name}</span>
            <span className="text-sm text-muted">Version {item.version}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
