import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  FilePlus2,
  ListChecks,
  Plus,
  Trash2,
} from 'lucide-react';
import {
  createInstitutionalDomain,
  type InstitutionalFactDataType,
  type InstitutionalFactInput,
  type InstitutionalIntakePayload,
  type InstitutionalIntakeResponse,
  type InstitutionalRuleInput,
  type InstitutionalRuleOperator,
} from '../api/client';

type IntakeStep = 1 | 2 | 3 | 4;

const steps: Array<{ id: IntakeStep; label: string; icon: typeof Building2 }> = [
  { id: 1, label: 'Decision', icon: Building2 },
  { id: 2, label: 'Facts', icon: ListChecks },
  { id: 3, label: 'Policy', icon: FilePlus2 },
  { id: 4, label: 'Review', icon: ClipboardCheck },
];

const dataTypes: Array<{ value: InstitutionalFactDataType; label: string }> = [
  { value: 'text', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'yes_no', label: 'Yes / no' },
];

const operatorOptions: Record<InstitutionalFactDataType, Array<{ value: InstitutionalRuleOperator; label: string }>> = {
  text: [
    { value: 'equals', label: 'Is exactly' },
    { value: 'does_not_equal', label: 'Is not' },
    { value: 'contains', label: 'Contains' },
  ],
  number: [
    { value: 'equals', label: 'Equals' },
    { value: 'does_not_equal', label: 'Does not equal' },
    { value: 'at_least', label: 'Is at least' },
    { value: 'at_most', label: 'Is at most' },
    { value: 'greater_than', label: 'Is greater than' },
    { value: 'less_than', label: 'Is less than' },
  ],
  yes_no: [
    { value: 'equals', label: 'Is' },
    { value: 'does_not_equal', label: 'Is not' },
  ],
};

let sequence = 0;
function nextId(prefix: string) {
  sequence += 1;
  return `${prefix}_${sequence}`;
}

function newFact(): InstitutionalFactInput {
  return { id: nextId('fact'), label: '', data_type: 'text' };
}

function newRule(factId: string): InstitutionalRuleInput {
  return {
    id: nextId('rule'),
    label: '',
    fact_id: factId,
    operator: 'equals',
    value: '',
    source_citation: '',
  };
}

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Institutional input could not be saved.';
}

export function InstitutionalIntake() {
  const [step, setStep] = useState<IntakeStep>(1);
  const [institutionName, setInstitutionName] = useState('');
  const [domainName, setDomainName] = useState('');
  const [policyName, setPolicyName] = useState('');
  const [publicPolicyGuide, setPublicPolicyGuide] = useState(true);
  const [assistanceRequestsEnabled, setAssistanceRequestsEnabled] = useState(true);
  const [supportResponseTargetHours, setSupportResponseTargetHours] = useState('48');
  const [decisionReviewEnabled, setDecisionReviewEnabled] = useState(false);
  const [decisionReviewResponseTargetHours, setDecisionReviewResponseTargetHours] = useState('120');
  const [supportPrivacyNoticeUrl, setSupportPrivacyNoticeUrl] = useState('');
  const [offlineAssistanceInstructions, setOfflineAssistanceInstructions] = useState('');
  const [facts, setFacts] = useState<InstitutionalFactInput[]>([newFact()]);
  const [rules, setRules] = useState<InstitutionalRuleInput[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InstitutionalIntakeResponse | null>(null);

  const factsById = useMemo(() => new Map(facts.map((fact) => [fact.id, fact])), [facts]);
  const decisionReady = institutionName.trim().length >= 2 && domainName.trim().length >= 2;
  const humanCaseworkEnabled = assistanceRequestsEnabled || decisionReviewEnabled;
  const caseworkContactReady = !humanCaseworkEnabled || (
    /^https?:\/\//.test(supportPrivacyNoticeUrl.trim()) &&
    offlineAssistanceInstructions.trim().length >= 10
  );
  const assistanceReady = !assistanceRequestsEnabled || (
    Number.isInteger(Number(supportResponseTargetHours)) && Number(supportResponseTargetHours) >= 1
  );
  const decisionReviewReady = !decisionReviewEnabled || (
    Number.isInteger(Number(decisionReviewResponseTargetHours)) && Number(decisionReviewResponseTargetHours) >= 1
  );
  const caseworkReady = caseworkContactReady && assistanceReady && decisionReviewReady;
  const factsReady = facts.length > 0 && facts.every((fact) => fact.label.trim().length >= 2);
  const policyReady = rules.length > 0 && rules.every((rule) => (
    rule.label.trim().length >= 2 &&
    rule.source_citation.trim().length >= 3 &&
    factsById.has(rule.fact_id) &&
    (typeof rule.value !== 'string' || rule.value.trim().length > 0)
  ));

  const addFact = () => setFacts((current) => [...current, newFact()]);
  const updateFact = (id: string, patch: Partial<InstitutionalFactInput>) => {
    setFacts((current) => current.map((fact) => (fact.id === id ? { ...fact, ...patch } : fact)));
    if (patch.data_type) {
      setRules((current) => current.map((rule) => {
        if (rule.fact_id !== id) return rule;
        const operator = operatorOptions[patch.data_type as InstitutionalFactDataType][0].value;
        const value = patch.data_type === 'yes_no' ? true : '';
        return { ...rule, operator, value };
      }));
    }
  };
  const removeFact = (id: string) => {
    setFacts((current) => current.filter((fact) => fact.id !== id));
    setRules((current) => current.filter((rule) => rule.fact_id !== id));
  };

  const addRule = () => {
    const fact = facts[0];
    if (fact) setRules((current) => [...current, newRule(fact.id)]);
  };
  const updateRule = (id: string, patch: Partial<InstitutionalRuleInput>) => {
    setRules((current) => current.map((rule) => (rule.id === id ? { ...rule, ...patch } : rule)));
  };
  const removeRule = (id: string) => setRules((current) => current.filter((rule) => rule.id !== id));

  const moveForward = () => {
    if (step === 1 && decisionReady) setStep(2);
    if (step === 2 && factsReady) setStep(3);
    if (step === 3 && policyReady) setStep(4);
  };

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const payload: InstitutionalIntakePayload = {
        institution_name: institutionName.trim(),
        domain_name: domainName.trim(),
        policy_name: policyName.trim() || undefined,
        public_policy_guide: publicPolicyGuide,
        assistance_requests_enabled: assistanceRequestsEnabled,
        support_response_target_hours: Number(supportResponseTargetHours),
        decision_review_enabled: decisionReviewEnabled,
        decision_review_response_target_hours: decisionReviewEnabled ? Number(decisionReviewResponseTargetHours) : undefined,
        support_privacy_notice_url: supportPrivacyNoticeUrl.trim() || undefined,
        offline_assistance_instructions: offlineAssistanceInstructions.trim() || undefined,
        facts: facts.map((fact) => ({ ...fact, label: fact.label.trim() })),
        rules: rules.map((rule) => {
          const fact = factsById.get(rule.fact_id);
          const value = fact?.data_type === 'number' ? Number(rule.value) : rule.value;
          return {
            ...rule,
            label: rule.label.trim(),
            value,
            source_citation: rule.source_citation.trim(),
          };
        }),
      };
      setResult(await createInstitutionalDomain(payload));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 py-8">
        <section className="border-b border-border pb-6">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="h-6 w-6 text-emerald-600" />
            <div>
              <h2 className="text-2xl font-semibold">Policy draft created</h2>
              <p className="mt-1 text-sm text-muted">{result.domain_name}</p>
            </div>
          </div>
        </section>
        <dl className="grid gap-x-8 gap-y-5 border-b border-border pb-6 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-semibold uppercase tracking-normal text-muted">Policy</dt>
            <dd className="mt-1 text-sm font-medium">{result.policy_name}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-normal text-muted">Status</dt>
            <dd className="mt-1 text-sm font-medium">Pending review</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-normal text-muted">Facts</dt>
            <dd className="mt-1 text-sm font-medium">{result.fact_count}</dd>
          </div>
          <div>
            <dt className="text-xs font-semibold uppercase tracking-normal text-muted">Rules</dt>
            <dd className="mt-1 text-sm font-medium">{result.rule_count}</dd>
          </div>
        </dl>
        <p className="text-sm leading-relaxed text-muted">{result.next_step}</p>
        <button
          type="button"
          onClick={() => { setResult(null); setStep(1); }}
          className="inline-flex w-fit items-center gap-2 rounded border border-border px-4 py-2 text-sm font-medium hover:bg-accent"
        >
          <Plus className="h-4 w-4" />
          Create another policy
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <section className="border-b border-border pb-6">
        <div className="flex items-center gap-3">
          <Building2 className="h-5 w-5 text-muted" />
          <div>
            <h2 className="text-2xl font-semibold">Institution setup</h2>
            <p className="mt-1 text-sm text-muted">Create a decision domain and policy draft</p>
          </div>
        </div>
      </section>

      <ol className="grid grid-cols-4 border-b border-border">
        {steps.map((item) => {
          const Icon = item.icon;
          const active = item.id === step;
          const complete = item.id < step;
          return (
            <li key={item.id} className={`flex items-center gap-2 border-b-2 px-2 pb-3 text-sm ${active ? 'border-primary font-semibold' : complete ? 'border-emerald-500 text-primary' : 'border-transparent text-muted'}`}>
              <Icon className="h-4 w-4 shrink-0" />
              <span className="hidden sm:inline">{item.label}</span>
            </li>
          );
        })}
      </ol>

      {step === 1 && (
        <section className="max-w-2xl space-y-5">
          <h3 className="text-base font-semibold">Decision domain</h3>
          <label className="block space-y-2 text-sm font-medium">
            Institution name
            <input value={institutionName} onChange={(event) => setInstitutionName(event.target.value)} className="w-full rounded border border-border px-3 py-2 outline-none focus:border-primary" />
          </label>
          <label className="block space-y-2 text-sm font-medium">
            Decision domain
            <input value={domainName} onChange={(event) => setDomainName(event.target.value)} className="w-full rounded border border-border px-3 py-2 outline-none focus:border-primary" />
          </label>
          <label className="block space-y-2 text-sm font-medium">
            Policy name <span className="font-normal text-muted">Optional</span>
            <input value={policyName} onChange={(event) => setPolicyName(event.target.value)} className="w-full rounded border border-border px-3 py-2 outline-none focus:border-primary" />
          </label>
          <div className="space-y-3 border-t border-border pt-4 text-sm">
            <label className="flex items-center gap-3">
              <input type="checkbox" checked={publicPolicyGuide} onChange={(event) => setPublicPolicyGuide(event.target.checked)} className="h-4 w-4" />
              <span className="font-medium">Publish an approved policy guide</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" checked={assistanceRequestsEnabled} onChange={(event) => setAssistanceRequestsEnabled(event.target.checked)} className="h-4 w-4" />
              <span className="font-medium">Accept requests for human assistance</span>
            </label>
            <label className="flex items-center gap-3">
              <input type="checkbox" checked={decisionReviewEnabled} onChange={(event) => setDecisionReviewEnabled(event.target.checked)} className="h-4 w-4" />
              <span className="font-medium">Enable decision review cases</span>
            </label>
            {humanCaseworkEnabled && <div className="grid gap-4 border-l-2 border-border pl-4 pt-2">
              {assistanceRequestsEnabled && <label className="grid gap-2 text-sm font-medium">
                Response target in hours
                <input aria-label="Response target in hours" type="number" min="1" value={supportResponseTargetHours} onChange={(event) => setSupportResponseTargetHours(event.target.value)} className="w-40 rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
              </label>}
              {decisionReviewEnabled && <label className="grid gap-2 text-sm font-medium">
                Decision review response target in hours
                <input aria-label="Decision review response target in hours" type="number" min="1" value={decisionReviewResponseTargetHours} onChange={(event) => setDecisionReviewResponseTargetHours(event.target.value)} className="w-40 rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
              </label>}
              <label className="grid gap-2 text-sm font-medium">
                Privacy notice URL
                <input aria-label="Privacy notice URL" type="url" value={supportPrivacyNoticeUrl} onChange={(event) => setSupportPrivacyNoticeUrl(event.target.value)} className="w-full rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
              </label>
              <label className="grid gap-2 text-sm font-medium">
                Assisted or offline contact route
                <textarea aria-label="Assisted or offline contact route" rows={3} value={offlineAssistanceInstructions} onChange={(event) => setOfflineAssistanceInstructions(event.target.value)} className="w-full resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
              </label>
            </div>}
          </div>
        </section>
      )}

      {step === 2 && (
        <section className="space-y-5">
          <div className="flex items-center justify-between gap-4">
            <h3 className="text-base font-semibold">Facts used in this decision</h3>
            <button type="button" onClick={addFact} className="inline-flex items-center gap-2 rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent">
              <Plus className="h-4 w-4" />
              Add fact
            </button>
          </div>
          <div className="space-y-3">
            {facts.map((fact) => (
              <div key={fact.id} className="grid gap-3 border-b border-border pb-3 sm:grid-cols-[minmax(0,1fr)_180px_36px] sm:items-end">
                <label className="space-y-2 text-sm font-medium">
                  Fact label
                  <input value={fact.label} onChange={(event) => updateFact(fact.id, { label: event.target.value })} className="w-full rounded border border-border px-3 py-2 outline-none focus:border-primary" />
                </label>
                <label className="space-y-2 text-sm font-medium">
                  Type
                  <select value={fact.data_type} onChange={(event) => updateFact(fact.id, { data_type: event.target.value as InstitutionalFactDataType })} className="w-full rounded border border-border bg-white px-3 py-2 outline-none focus:border-primary">
                    {dataTypes.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                  </select>
                </label>
                <button type="button" title="Remove fact" aria-label="Remove fact" onClick={() => removeFact(fact.id)} disabled={facts.length === 1} className="inline-flex h-9 w-9 items-center justify-center rounded border border-border text-muted hover:bg-accent disabled:opacity-40">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {step === 3 && (
        <section className="space-y-5">
          <div className="flex items-center justify-between gap-4">
            <h3 className="text-base font-semibold">Conditions that must all hold</h3>
            <button type="button" onClick={addRule} className="inline-flex items-center gap-2 rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent">
              <Plus className="h-4 w-4" />
              Add condition
            </button>
          </div>
          {rules.length === 0 && <p className="text-sm text-muted">Add the first condition for this policy.</p>}
          <div className="space-y-6">
            {rules.map((rule) => {
              const fact = factsById.get(rule.fact_id) || facts[0];
              const options = operatorOptions[fact?.data_type || 'text'];
              return (
                <div key={rule.id} className="grid gap-4 border-b border-border pb-5 sm:grid-cols-[minmax(0,1fr)_36px]">
                  <div className="grid gap-4 md:grid-cols-2">
                    <label className="space-y-2 text-sm font-medium">
                      Condition name
                      <input value={rule.label} onChange={(event) => updateRule(rule.id, { label: event.target.value })} className="w-full rounded border border-border px-3 py-2 outline-none focus:border-primary" />
                    </label>
                    <label className="space-y-2 text-sm font-medium">
                      Fact
                      <select value={rule.fact_id} onChange={(event) => {
                        const selected = factsById.get(event.target.value);
                        updateRule(rule.id, { fact_id: event.target.value, operator: operatorOptions[selected?.data_type || 'text'][0].value, value: selected?.data_type === 'yes_no' ? true : '' });
                      }} className="w-full rounded border border-border bg-white px-3 py-2 outline-none focus:border-primary">
                        {facts.map((availableFact) => <option key={availableFact.id} value={availableFact.id}>{availableFact.label || 'Untitled fact'}</option>)}
                      </select>
                    </label>
                    <label className="space-y-2 text-sm font-medium">
                      Test
                      <select value={rule.operator} onChange={(event) => updateRule(rule.id, { operator: event.target.value as InstitutionalRuleOperator })} className="w-full rounded border border-border bg-white px-3 py-2 outline-none focus:border-primary">
                        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </label>
                    <label className="space-y-2 text-sm font-medium">
                      Value
                      {fact?.data_type === 'yes_no' ? (
                        <select value={String(rule.value)} onChange={(event) => updateRule(rule.id, { value: event.target.value === 'true' })} className="w-full rounded border border-border bg-white px-3 py-2 outline-none focus:border-primary">
                          <option value="true">Yes</option>
                          <option value="false">No</option>
                        </select>
                      ) : (
                        <input type={fact?.data_type === 'number' ? 'number' : 'text'} value={String(rule.value)} onChange={(event) => updateRule(rule.id, { value: event.target.value })} className="w-full rounded border border-border px-3 py-2 outline-none focus:border-primary" />
                      )}
                    </label>
                    <label className="space-y-2 text-sm font-medium md:col-span-2">
                      Source citation
                      <input value={rule.source_citation} onChange={(event) => updateRule(rule.id, { source_citation: event.target.value })} className="w-full rounded border border-border px-3 py-2 outline-none focus:border-primary" />
                    </label>
                  </div>
                  <button type="button" title="Remove condition" aria-label="Remove condition" onClick={() => removeRule(rule.id)} className="inline-flex h-9 w-9 items-center justify-center self-end rounded border border-border text-muted hover:bg-accent">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="max-w-3xl space-y-6">
          <h3 className="text-base font-semibold">Review policy draft</h3>
          <dl className="grid gap-x-8 gap-y-5 border-y border-border py-5 sm:grid-cols-2">
            <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Institution</dt><dd className="mt-1 text-sm font-medium">{institutionName}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Decision domain</dt><dd className="mt-1 text-sm font-medium">{domainName}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Facts</dt><dd className="mt-1 text-sm font-medium">{facts.length}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Conditions</dt><dd className="mt-1 text-sm font-medium">{rules.length}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Policy guide</dt><dd className="mt-1 text-sm font-medium">{publicPolicyGuide ? 'Public after approval' : 'Not public'}</dd></div>
            <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Human assistance</dt><dd className="mt-1 text-sm font-medium">{assistanceRequestsEnabled ? 'Available' : 'Not available'}</dd></div>
            {assistanceRequestsEnabled && <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Response target</dt><dd className="mt-1 text-sm font-medium">{supportResponseTargetHours} hours</dd></div>}
            <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Decision review</dt><dd className="mt-1 text-sm font-medium">{decisionReviewEnabled ? 'Enabled' : 'Not enabled'}</dd></div>
            {decisionReviewEnabled && <div><dt className="text-xs font-semibold uppercase tracking-normal text-muted">Review response target</dt><dd className="mt-1 text-sm font-medium">{decisionReviewResponseTargetHours} hours</dd></div>}
          </dl>
          <div className="space-y-3">
            {rules.map((rule) => <div key={rule.id} className="border-b border-border pb-3 text-sm"><p className="font-medium">{rule.label}</p><p className="mt-1 text-muted">{rule.source_citation}</p></div>)}
          </div>
        </section>
      )}

      {error && <div className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}

      <div className="flex items-center justify-between border-t border-border pt-5">
        <button type="button" onClick={() => setStep((current) => Math.max(1, current - 1) as IntakeStep)} disabled={step === 1 || submitting} className="inline-flex items-center gap-2 rounded border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40">
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        {step < 4 ? (
          <button type="button" onClick={moveForward} disabled={(step === 1 && (!decisionReady || !caseworkReady)) || (step === 2 && !factsReady) || (step === 3 && !policyReady)} className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
            Continue
            <ArrowRight className="h-4 w-4" />
          </button>
        ) : (
          <button type="button" onClick={() => void submit()} disabled={submitting || !caseworkReady} className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
            <ClipboardCheck className="h-4 w-4" />
            {submitting ? 'Creating draft...' : 'Create policy draft'}
          </button>
        )}
      </div>
    </div>
  );
}
