import { useEffect, useState } from 'react';
import { AlertTriangle, BookOpenCheck, CheckCircle2, Send } from 'lucide-react';
import {
  createPolicyAmbiguity,
  fetchAdminDomains,
  fetchPolicyAmbiguities,
  resolvePolicyAmbiguity,
  type AdminDomain,
  type PolicyAmbiguity,
} from '../api/client';

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'The policy register could not be updated.';
}

export function PolicyAmbiguityRegister() {
  const [domains, setDomains] = useState<AdminDomain[]>([]);
  const [domainId, setDomainId] = useState('');
  const [items, setItems] = useState<PolicyAmbiguity[]>([]);
  const [citation, setCitation] = useState('');
  const [question, setQuestion] = useState('');
  const [options, setOptions] = useState(['', '']);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolution, setResolution] = useState('');
  const [sourceReference, setSourceReference] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const loaded = await fetchAdminDomains();
        setDomains(loaded);
        setDomainId(loaded[0]?.domain_id || '');
      } catch (requestError) {
        setError(errorMessage(requestError));
      }
    })();
  }, []);

  useEffect(() => {
    if (!domainId) {
      setItems([]);
      return;
    }
    void (async () => {
      setError(null);
      try {
        setItems(await fetchPolicyAmbiguities(domainId));
      } catch (requestError) {
        setError(errorMessage(requestError));
      }
    })();
  }, [domainId]);

  const recordAmbiguity = async () => {
    const interpretationOptions = options.map((value) => value.trim()).filter(Boolean);
    if (!domainId || !citation.trim() || !question.trim() || interpretationOptions.length < 2) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createPolicyAmbiguity({
        domain_id: domainId,
        source_citation: citation.trim(),
        question: question.trim(),
        interpretation_options: interpretationOptions,
      });
      setItems((current) => [created, ...current]);
      setCitation('');
      setQuestion('');
      setOptions(['', '']);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSaving(false);
    }
  };

  const resolve = async (item: PolicyAmbiguity) => {
    if (!domainId || !resolution.trim() || !sourceReference.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await resolvePolicyAmbiguity(item.ambiguity_id, {
        domain_id: domainId,
        resolution: resolution.trim(),
        source_reference: sourceReference.trim(),
      });
      setItems((current) => current.map((currentItem) => currentItem.ambiguity_id === updated.ambiguity_id ? updated : currentItem));
      setResolvingId(null);
      setResolution('');
      setSourceReference('');
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSaving(false);
    }
  };

  return <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 py-4">
    <section className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
      <div className="flex items-center gap-3"><BookOpenCheck className="h-5 w-5 text-muted" /><div><h2 className="text-2xl font-semibold">Policy interpretation register</h2><p className="mt-1 text-sm text-muted">Questions that must be settled before publication</p></div></div>
      <label className="grid gap-1 text-sm font-medium">Domain<select aria-label="Policy ambiguity domain" value={domainId} onChange={(event) => setDomainId(event.target.value)} className="min-w-60 rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">Select a domain</option>{domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}</select></label>
    </section>

    {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}

    <section className="grid gap-4 border-b border-border pb-6">
      <label className="grid gap-2 text-sm font-medium">Source citation<textarea aria-label="Ambiguity source citation" value={citation} onChange={(event) => setCitation(event.target.value)} rows={2} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
      <label className="grid gap-2 text-sm font-medium">Interpretation question<textarea aria-label="Interpretation question" value={question} onChange={(event) => setQuestion(event.target.value)} rows={3} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>
      <div className="grid gap-2"><span className="text-sm font-medium">Possible readings</span>{options.map((option, index) => <input key={index} aria-label={`Interpretation option ${index + 1}`} value={option} onChange={(event) => setOptions((current) => current.map((value, currentIndex) => currentIndex === index ? event.target.value : value))} className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary" />)}<div className="flex flex-wrap gap-2"><button type="button" onClick={() => setOptions((current) => [...current, ''])} className="rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent">Add reading</button><button type="button" onClick={() => void recordAmbiguity()} disabled={saving || !domainId || !citation.trim() || !question.trim() || options.filter((value) => value.trim()).length < 2} className="inline-flex items-center gap-2 rounded bg-primary px-3 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><Send className="h-4 w-4" />Record ambiguity</button></div></div>
    </section>

    {!domainId && <p className="text-sm text-muted">No assigned policy domain is available.</p>}
    {domainId && items.length === 0 && <p className="text-sm text-muted">No policy ambiguities are recorded for this domain.</p>}
    <div className="divide-y divide-border border-y border-border">{items.map((item) => <article key={item.ambiguity_id} className="grid gap-3 px-1 py-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-medium">{item.question}</h3><p className="mt-1 text-sm text-muted">{item.source_citation}</p></div><span className={item.status === 'OPEN' ? 'border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800' : 'inline-flex items-center gap-1 border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800'}>{item.status === 'RESOLVED' && <CheckCircle2 className="h-3.5 w-3.5" />}{item.status === 'OPEN' ? 'Open' : 'Resolved'}</span></div><p className="text-sm">{item.interpretation_options.join(' / ')}</p>{item.status === 'RESOLVED' && <div className="border-l-2 border-primary pl-3 text-sm"><p>{item.resolution}</p><p className="mt-1 text-muted">{item.resolution_source_reference}</p></div>}{item.status === 'OPEN' && resolvingId !== item.ambiguity_id && <button type="button" onClick={() => setResolvingId(item.ambiguity_id)} className="w-fit rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent">Record interpretation</button>}{item.status === 'OPEN' && resolvingId === item.ambiguity_id && <div className="grid max-w-2xl gap-2"><textarea aria-label={`Resolution for ambiguity ${item.ambiguity_id}`} value={resolution} onChange={(event) => setResolution(event.target.value)} rows={3} className="resize-y rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary" /><input aria-label={`Resolution source for ambiguity ${item.ambiguity_id}`} value={sourceReference} onChange={(event) => setSourceReference(event.target.value)} className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary" /><div className="flex gap-2"><button type="button" disabled={saving || !resolution.trim() || !sourceReference.trim()} onClick={() => void resolve(item)} className="inline-flex items-center gap-2 rounded bg-primary px-3 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><CheckCircle2 className="h-4 w-4" />Record interpretation</button><button type="button" onClick={() => { setResolvingId(null); setResolution(''); setSourceReference(''); }} className="rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent">Cancel</button></div></div>}</article>)}</div>
  </div>;
}
