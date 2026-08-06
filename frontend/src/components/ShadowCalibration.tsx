import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Play,
  Plus,
  Send,
  ShieldCheck,
  TestTube2,
  X,
} from 'lucide-react';
import {
  certifyShadowCalibration,
  createShadowCalibration,
  fetchAdminDomains,
  fetchCalibrationReleases,
  fetchRecordImportFields,
  fetchShadowCalibration,
  fetchShadowCalibrations,
  resolveShadowCalibrationFinding,
  runShadowCalibration,
  type CalibrationDataBasis,
  type CalibrationDecision,
  type CalibrationFindingClassification,
  type RecordImportField,
  type ShadowCalibrationCaseInput,
  type ShadowCalibrationFactInput,
  type ShadowCalibrationFinding,
  type ShadowCalibrationSuite,
  type ShadowCalibrationSuiteSummary,
} from '../api/client';

type DraftFact = {
  targetPath: string;
  value: string;
  status: 'resolved' | 'needs_human_review';
};

type DraftCase = {
  caseReference: string;
  description: string;
  recordedDecision: CalibrationDecision;
  recordedOutcomeReference: string;
  facts: DraftFact[];
};

type FindingDraft = {
  classification: CalibrationFindingClassification;
  note: string;
};

const decisionLabels: Record<CalibrationDecision, string> = {
  ELIGIBLE: 'Conditions satisfied',
  INELIGIBLE: 'Conditions not satisfied',
  NEEDS_MANUAL_REVIEW: 'Human consideration required',
};

const findingLabels: Record<CalibrationFindingClassification, string> = {
  SOURCE_DATA: 'Source data',
  POLICY_MODEL: 'Policy model',
  EVIDENCE: 'Evidence',
  GOVERNANCE: 'Governance',
};

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Outcome calibration could not be completed.';
}

function emptyCase(): DraftCase {
  return {
    caseReference: '',
    description: '',
    recordedDecision: 'ELIGIBLE',
    recordedOutcomeReference: '',
    facts: [],
  };
}

function formatValue(value: string | number | boolean) {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  return String(value);
}

function dataBasisLabel(value: CalibrationDataBasis) {
  return value === 'SYNTHETIC' ? 'Synthetic representative cases' : 'Approved de-identified cases';
}

export function ShadowCalibration({
  canCreate,
  canCertify,
  canResolveMismatch,
}: {
  canCreate: boolean;
  canCertify: boolean;
  canResolveMismatch: boolean;
}) {
  const [domains, setDomains] = useState<Array<{ domain_id: string; domain_name: string }>>([]);
  const [domainId, setDomainId] = useState('');
  const [releases, setReleases] = useState<Array<{ release_id: string; version: string; calibration_ready: boolean; calibration_blocker?: string | null }>>([]);
  const [fields, setFields] = useState<RecordImportField[]>([]);
  const [suites, setSuites] = useState<ShadowCalibrationSuiteSummary[]>([]);
  const [selectedSuite, setSelectedSuite] = useState<ShadowCalibrationSuite | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingSuite, setLoadingSuite] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [certifying, setCertifying] = useState(false);
  const [running, setRunning] = useState(false);
  const [resolvingFinding, setResolvingFinding] = useState<string | null>(null);

  const [releaseId, setReleaseId] = useState('');
  const [suiteName, setSuiteName] = useState('');
  const [suiteDescription, setSuiteDescription] = useState('');
  const [dataBasis, setDataBasis] = useState<CalibrationDataBasis>('SYNTHETIC');
  const [privacyApprovalReference, setPrivacyApprovalReference] = useState('');
  const [policyAsOfDate, setPolicyAsOfDate] = useState('');
  const [draftCases, setDraftCases] = useState<DraftCase[]>([]);
  const [draftCase, setDraftCase] = useState<DraftCase>(emptyCase());
  const [factTarget, setFactTarget] = useState('');
  const [factValue, setFactValue] = useState('');
  const [factStatus, setFactStatus] = useState<'resolved' | 'needs_human_review'>('resolved');
  const [certificationNote, setCertificationNote] = useState('');
  const [findingDrafts, setFindingDrafts] = useState<Record<string, FindingDraft>>({});

  const fieldsByPath = useMemo(() => new Map(fields.map((field) => [field.target_path, field])), [fields]);
  const selectedFactField = fieldsByPath.get(factTarget);
  const canRun = canCreate || canCertify;

  const loadDomain = useCallback(async (selectedDomainId: string) => {
    setLoading(true);
    setError(null);
    setSelectedSuite(null);
    try {
      const requests: [Promise<Awaited<ReturnType<typeof fetchCalibrationReleases>>>, Promise<Awaited<ReturnType<typeof fetchShadowCalibrations>>>, Promise<RecordImportField[]>?] = [
        fetchCalibrationReleases(selectedDomainId),
        fetchShadowCalibrations(selectedDomainId),
      ];
      if (canCreate) requests.push(fetchRecordImportFields(selectedDomainId));
      const [loadedReleases, loadedSuites, loadedFields] = await Promise.all(requests);
      setReleases(loadedReleases);
      setSuites(loadedSuites);
      setFields(loadedFields || []);
      const readyRelease = loadedReleases.find((release) => release.calibration_ready);
      setReleaseId(readyRelease?.release_id || '');
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [canCreate]);

  useEffect(() => {
    let active = true;
    void fetchAdminDomains()
      .then((loadedDomains) => {
        if (!active) return;
        setDomains(loadedDomains);
        setDomainId(loadedDomains[0]?.domain_id || '');
      })
      .catch((requestError) => active && setError(errorMessage(requestError)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (domainId) void loadDomain(domainId);
  }, [domainId, loadDomain]);

  const openSuite = async (suiteId: string) => {
    if (!domainId) return;
    setLoadingSuite(true);
    setError(null);
    try {
      setSelectedSuite(await fetchShadowCalibration(suiteId, domainId));
      setCertificationNote('');
      setFindingDrafts({});
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoadingSuite(false);
    }
  };

  const resetDraft = () => {
    setSuiteName('');
    setSuiteDescription('');
    setDataBasis('SYNTHETIC');
    setPrivacyApprovalReference('');
    setPolicyAsOfDate('');
    setDraftCases([]);
    setDraftCase(emptyCase());
    setFactTarget('');
    setFactValue('');
    setFactStatus('resolved');
  };

  const addFact = () => {
    if (!selectedFactField || !factValue.trim() || draftCase.facts.some((fact) => fact.targetPath === factTarget)) return;
    setDraftCase((current) => ({
      ...current,
      facts: [...current.facts, { targetPath: factTarget, value: factValue.trim(), status: factStatus }],
    }));
    setFactTarget('');
    setFactValue('');
    setFactStatus('resolved');
  };

  const addCase = () => {
    if (!draftCase.caseReference.trim() || !draftCase.description.trim() || !draftCase.recordedOutcomeReference.trim() || draftCase.facts.length === 0) return;
    if (draftCases.some((item) => item.caseReference === draftCase.caseReference.trim())) return;
    setDraftCases((current) => [...current, {
      ...draftCase,
      caseReference: draftCase.caseReference.trim(),
      description: draftCase.description.trim(),
      recordedOutcomeReference: draftCase.recordedOutcomeReference.trim(),
    }]);
    setDraftCase(emptyCase());
    setFactTarget('');
    setFactValue('');
    setFactStatus('resolved');
  };

  const buildFacts = (facts: DraftFact[]): ShadowCalibrationFactInput[] => facts.map((fact) => {
    const field = fieldsByPath.get(fact.targetPath);
    const value = field?.schema_type === 'number'
      ? Number(fact.value)
      : field?.schema_type === 'boolean'
        ? fact.value === 'true'
        : fact.value;
    return { target_path: fact.targetPath, value, status: fact.status };
  });

  const createSuite = async () => {
    if (!domainId || !releaseId || !suiteName.trim() || !suiteDescription.trim() || !policyAsOfDate || draftCases.length === 0) return;
    if (dataBasis === 'APPROVED_DEIDENTIFIED' && privacyApprovalReference.trim().length < 8) return;
    setCreating(true);
    setError(null);
    try {
      const cases: ShadowCalibrationCaseInput[] = draftCases.map((item) => ({
        case_reference: item.caseReference,
        description: item.description,
        recorded_decision: item.recordedDecision,
        recorded_outcome_reference: item.recordedOutcomeReference,
        facts: buildFacts(item.facts),
      }));
      const created = await createShadowCalibration({
        domain_id: domainId,
        release_id: releaseId,
        name: suiteName.trim(),
        description: suiteDescription.trim(),
        data_basis: dataBasis,
        ...(dataBasis === 'APPROVED_DEIDENTIFIED' ? { privacy_approval_reference: privacyApprovalReference.trim() } : {}),
        policy_as_of_date: policyAsOfDate,
        cases,
      });
      setSelectedSuite(created);
      setSuites((current) => [created, ...current]);
      setShowCreate(false);
      resetDraft();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setCreating(false);
    }
  };

  const certifySuite = async () => {
    if (!selectedSuite || !domainId || certificationNote.trim().length < 10) return;
    setCertifying(true);
    setError(null);
    try {
      const certified = await certifyShadowCalibration(selectedSuite.suite_id, domainId, certificationNote.trim());
      setSelectedSuite(certified);
      setSuites((current) => current.map((suite) => suite.suite_id === certified.suite_id ? certified : suite));
      setCertificationNote('');
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setCertifying(false);
    }
  };

  const runSuite = async () => {
    if (!selectedSuite || !domainId) return;
    setRunning(true);
    setError(null);
    try {
      await runShadowCalibration(selectedSuite.suite_id, domainId);
      const refreshed = await fetchShadowCalibration(selectedSuite.suite_id, domainId);
      setSelectedSuite(refreshed);
      setSuites((current) => current.map((suite) => suite.suite_id === refreshed.suite_id ? refreshed : suite));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setRunning(false);
    }
  };

  const resolveFinding = async (finding: ShadowCalibrationFinding) => {
    const draft = findingDrafts[finding.finding_id];
    if (!domainId || !selectedSuite || !draft || draft.note.trim().length < 10) return;
    setResolvingFinding(finding.finding_id);
    setError(null);
    try {
      const resolved = await resolveShadowCalibrationFinding(finding.finding_id, domainId, draft.classification, draft.note.trim());
      setSelectedSuite((current) => current ? {
        ...current,
        findings: current.findings.map((item) => item.finding_id === resolved.finding_id ? resolved : item),
      } : current);
      setFindingDrafts((current) => {
        const { [finding.finding_id]: _resolved, ...remaining } = current;
        return remaining;
      });
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setResolvingFinding(null);
    }
  };

  if (selectedSuite) {
    const caseById = new Map(selectedSuite.cases.map((item) => [item.case_id, item]));
    const allCasesMatched = selectedSuite.run?.report.all_cases_passed;
    return (
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 py-4">
        <section className="border-b border-border pb-5">
          <button type="button" onClick={() => setSelectedSuite(null)} className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-primary"><ArrowLeft className="h-4 w-4" />All calibration suites</button>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3"><TestTube2 aria-hidden="true" className="mt-0.5 h-5 w-5 text-muted" /><div><h2 className="text-2xl font-semibold">{selectedSuite.name}</h2><p className="mt-1 text-sm text-muted">Release {selectedSuite.release_version}  |  {selectedSuite.case_count} representative cases</p></div></div>
            <span className="text-sm font-medium">{selectedSuite.status}</span>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-relaxed text-muted">{selectedSuite.description}</p>
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted"><span>{dataBasisLabel(selectedSuite.data_basis)}</span><span>Policy as of {selectedSuite.policy_as_of_date}</span><span>Input hash {selectedSuite.input_sha256}</span></div>
        </section>

        {selectedSuite.status === 'SUBMITTED' && <section aria-labelledby="certification-heading" className="border-y border-border py-6">
          <div className="flex items-center gap-2"><ShieldCheck aria-hidden="true" className="h-5 w-5 text-muted" /><h3 id="certification-heading" className="text-lg font-semibold">Independent certification</h3></div>
          {canCertify ? <div className="mt-4 grid max-w-2xl gap-3"><label className="grid gap-2 text-sm font-medium">Certification note<textarea value={certificationNote} onChange={(event) => setCertificationNote(event.target.value)} minLength={10} maxLength={4000} rows={4} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><button type="button" onClick={() => void certifySuite()} disabled={certifying || certificationNote.trim().length < 10} className="inline-flex w-fit items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><ShieldCheck className="h-4 w-4" />{certifying ? 'Certifying...' : 'Certify case inputs'}</button></div> : <p className="mt-3 text-sm text-muted">This account can inspect the submitted case set but cannot certify it.</p>}
        </section>}

        {selectedSuite.status === 'CERTIFIED' && <section aria-labelledby="run-heading" className="border-y border-border py-6">
          <div className="flex items-center gap-2"><Play aria-hidden="true" className="h-5 w-5 text-muted" /><h3 id="run-heading" className="text-lg font-semibold">Run pre-production comparison</h3></div>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">The comparison uses the signed release and the certified representative facts. It does not create or communicate an operative institutional outcome.</p>
          {canRun && <button type="button" onClick={() => void runSuite()} disabled={running} className="mt-4 inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><Play className="h-4 w-4" />{running ? 'Running comparison...' : 'Run comparison'}</button>}
        </section>}

        {selectedSuite.run && <section aria-labelledby="results-heading" className="border-y border-border py-6">
          <div className="flex items-center gap-2"><ClipboardCheck aria-hidden="true" className="h-5 w-5 text-muted" /><h3 id="results-heading" className="text-lg font-semibold">Comparison results</h3></div>
          <p className={`mt-3 text-sm font-medium ${allCasesMatched ? 'text-emerald-800' : 'text-amber-800'}`}>{allCasesMatched ? 'All recorded outcomes matched this signed release.' : 'One or more recorded outcomes need institutional interpretation.'}</p>
          <p className="mt-2 text-xs text-muted">Report hash {selectedSuite.run.report_sha256}</p>
          <div className="mt-5 divide-y divide-border border-y border-border">{selectedSuite.run.report.cases.map((result) => {
            const calibrationCase = caseById.get(result.id);
            return <article key={result.id} className="flex flex-wrap items-center justify-between gap-3 py-4"><div><h4 className="text-sm font-semibold">{calibrationCase?.case_reference || result.id}</h4><p className="mt-1 text-sm text-muted">Recorded: {decisionLabels[result.expected_decision]}  |  Calculated: {decisionLabels[result.actual_decision]}</p></div><span className={`text-sm font-medium ${result.passed ? 'text-emerald-800' : 'text-amber-800'}`}>{result.passed ? 'Matched' : 'Needs interpretation'}</span></article>;
          })}</div>
        </section>}

        <section aria-labelledby="cases-heading">
          <h3 id="cases-heading" className="text-lg font-semibold">Certified representative cases</h3>
          <div className="mt-4 divide-y divide-border border-y border-border">{selectedSuite.cases.map((item) => <article key={item.case_id} className="py-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="text-sm font-semibold">{item.case_reference}</h4><p className="mt-1 max-w-3xl text-sm text-muted">{item.description}</p></div><span className="text-sm font-medium">{decisionLabels[item.recorded_decision]}</span></div><p className="mt-3 text-xs text-muted">Recorded outcome source: {item.recorded_outcome_reference}</p><dl className="mt-4 grid gap-3 border-l-2 border-border pl-4 sm:grid-cols-2">{item.facts.map((fact) => <div key={fact.target_path}><dt className="text-xs font-medium">{fieldsByPath.get(fact.target_path)?.label || fact.target_path}</dt><dd className="mt-1 text-sm text-muted">{formatValue(fact.value)}{fact.status === 'needs_human_review' ? '  |  Human consideration' : ''}</dd></div>)}</dl></article>)}</div>
        </section>

        {selectedSuite.findings.length > 0 && <section aria-labelledby="findings-heading" className="border-t border-border pt-6"><div className="flex items-center gap-2"><AlertTriangle aria-hidden="true" className="h-5 w-5 text-amber-700" /><h3 id="findings-heading" className="text-lg font-semibold">Mismatches requiring interpretation</h3></div><div className="mt-4 divide-y divide-border border-y border-border">{selectedSuite.findings.map((finding) => {
          const draft = findingDrafts[finding.finding_id] || { classification: 'POLICY_MODEL' as const, note: '' };
          return <article key={finding.finding_id} className="py-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="text-sm font-semibold">{finding.case_reference}</h4><p className="mt-1 text-sm text-muted">Recorded: {decisionLabels[finding.expected_decision]}  |  Calculated: {decisionLabels[finding.actual_decision]}</p></div><span className="text-sm font-medium">{finding.status === 'OPEN' ? 'Open' : findingLabels[finding.classification || 'GOVERNANCE']}</span></div>{finding.status === 'RESOLVED' ? <p className="mt-3 border-l-2 border-border pl-3 text-sm text-muted">{finding.resolution_note}</p> : canResolveMismatch ? <div className="mt-4 grid max-w-2xl gap-3"><label className="grid gap-2 text-sm font-medium">Mismatch category<select value={draft.classification} onChange={(event) => setFindingDrafts((current) => ({ ...current, [finding.finding_id]: { ...draft, classification: event.target.value as CalibrationFindingClassification } }))} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">{Object.entries(findingLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="grid gap-2 text-sm font-medium">Interpretation note<textarea value={draft.note} onChange={(event) => setFindingDrafts((current) => ({ ...current, [finding.finding_id]: { ...draft, note: event.target.value } }))} minLength={10} maxLength={4000} rows={4} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><button type="button" onClick={() => void resolveFinding(finding)} disabled={resolvingFinding === finding.finding_id || draft.note.trim().length < 10} className="inline-flex w-fit items-center gap-2 rounded border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40"><CheckCircle2 className="h-4 w-4" />{resolvingFinding === finding.finding_id ? 'Recording...' : 'Record interpretation'}</button></div> : <p className="mt-3 text-sm text-muted">This account can inspect the mismatch but cannot classify it.</p>}</article>;
        })}</div></section>}

        {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      </div>
    );
  }

  const canAddCurrentCase = Boolean(draftCase.caseReference.trim() && draftCase.description.trim() && draftCase.recordedOutcomeReference.trim() && draftCase.facts.length > 0);
  const canSubmitSuite = Boolean(domainId && releaseId && suiteName.trim() && suiteDescription.trim() && policyAsOfDate && draftCases.length > 0 && (dataBasis !== 'APPROVED_DEIDENTIFIED' || privacyApprovalReference.trim().length >= 8));

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 py-4">
      <section className="flex flex-wrap items-center justify-between gap-4 border-b border-border pb-5"><div className="flex items-center gap-3"><TestTube2 aria-hidden="true" className="h-5 w-5 text-muted" /><div><h2 className="text-2xl font-semibold">Outcome calibration</h2><p className="mt-1 text-sm text-muted">Compare recorded outcomes with an approved policy release before operational use.</p></div></div>{canCreate && <button type="button" onClick={() => { setShowCreate((current) => !current); resetDraft(); }} className="inline-flex items-center gap-2 rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent"><Plus className="h-4 w-4" />New suite</button>}</section>

      <section className="flex flex-wrap items-end gap-4"><label className="grid gap-2 text-sm font-medium">Decision domain<select value={domainId} onChange={(event) => setDomainId(event.target.value)} className="min-w-64 rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">Select domain</option>{domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}</select></label></section>

      {showCreate && <section aria-labelledby="new-suite-heading" className="border-y border-border py-6"><h3 id="new-suite-heading" className="text-lg font-semibold">New calibration suite</h3><div className="mt-5 grid max-w-3xl gap-5"><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-sm font-medium">Signed policy release<select value={releaseId} onChange={(event) => setReleaseId(event.target.value)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">Select verified release</option>{releases.map((release) => <option key={release.release_id} value={release.release_id} disabled={!release.calibration_ready}>Release {release.version}{release.calibration_ready ? '' : '  |  not verifiable'}</option>)}</select></label><label className="grid gap-2 text-sm font-medium">Policy as of<input type="date" value={policyAsOfDate} onChange={(event) => setPolicyAsOfDate(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label></div><label className="grid gap-2 text-sm font-medium">Suite name<input value={suiteName} onChange={(event) => setSuiteName(event.target.value)} maxLength={160} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Comparison purpose<textarea value={suiteDescription} onChange={(event) => setSuiteDescription(event.target.value)} minLength={10} maxLength={2000} rows={3} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Case basis<select value={dataBasis} onChange={(event) => setDataBasis(event.target.value as CalibrationDataBasis)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="SYNTHETIC">Synthetic representative cases</option><option value="APPROVED_DEIDENTIFIED">Approved de-identified cases</option></select></label>{dataBasis === 'APPROVED_DEIDENTIFIED' && <label className="grid gap-2 text-sm font-medium">Privacy approval reference<input value={privacyApprovalReference} onChange={(event) => setPrivacyApprovalReference(event.target.value)} minLength={8} maxLength={500} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label>}</div>

        <div className="mt-8 border-t border-border pt-6"><h4 className="text-base font-semibold">Representative case</h4><div className="mt-4 grid max-w-3xl gap-4"><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-sm font-medium">Non-identifying case reference<input value={draftCase.caseReference} onChange={(event) => setDraftCase((current) => ({ ...current, caseReference: event.target.value }))} placeholder="case_progression_01" className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Recorded institutional outcome<select value={draftCase.recordedDecision} onChange={(event) => setDraftCase((current) => ({ ...current, recordedDecision: event.target.value as CalibrationDecision }))} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">{Object.entries(decisionLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><label className="grid gap-2 text-sm font-medium">Case description<textarea value={draftCase.description} onChange={(event) => setDraftCase((current) => ({ ...current, description: event.target.value }))} minLength={5} maxLength={1200} rows={3} className="resize-y rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label><label className="grid gap-2 text-sm font-medium">Recorded outcome source<input value={draftCase.recordedOutcomeReference} onChange={(event) => setDraftCase((current) => ({ ...current, recordedOutcomeReference: event.target.value }))} minLength={5} maxLength={500} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" /></label></div>

        <div className="mt-6 border-l-2 border-border pl-4"><h5 className="text-sm font-semibold">Facts used for this comparison</h5><div className="mt-3 grid max-w-3xl gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"><label className="grid gap-2 text-sm font-medium">Policy fact<select value={factTarget} onChange={(event) => { setFactTarget(event.target.value); setFactValue(''); }} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">Select fact</option>{fields.filter((field) => !draftCase.facts.some((fact) => fact.targetPath === field.target_path)).map((field) => <option key={field.target_path} value={field.target_path}>{field.label}</option>)}</select></label><label className="grid gap-2 text-sm font-medium">Recorded value{selectedFactField?.schema_type === 'boolean' ? <select value={factValue} onChange={(event) => setFactValue(event.target.value)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="">Select</option><option value="true">Yes</option><option value="false">No</option></select> : <input type={selectedFactField?.schema_type === 'number' ? 'number' : 'text'} value={factValue} onChange={(event) => setFactValue(event.target.value)} disabled={!selectedFactField} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary disabled:bg-accent" />}</label><button type="button" onClick={addFact} disabled={!selectedFactField || !factValue.trim()} className="mt-7 inline-flex h-10 items-center justify-center gap-2 rounded border border-border px-3 text-sm font-medium hover:bg-accent disabled:opacity-40"><Plus className="h-4 w-4" />Add fact</button></div><label className="mt-3 grid max-w-xs gap-2 text-sm font-medium">Fact status<select value={factStatus} onChange={(event) => setFactStatus(event.target.value as 'resolved' | 'needs_human_review')} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary"><option value="resolved">Recorded</option><option value="needs_human_review">Needs human consideration</option></select></label><div className="mt-4 divide-y divide-border border-y border-border">{draftCase.facts.map((fact) => <div key={fact.targetPath} className="flex items-center justify-between gap-3 py-3 text-sm"><span>{fieldsByPath.get(fact.targetPath)?.label || fact.targetPath}: {fact.value}{fact.status === 'needs_human_review' ? '  |  Human consideration' : ''}</span><button type="button" aria-label={`Remove ${fieldsByPath.get(fact.targetPath)?.label || fact.targetPath}`} onClick={() => setDraftCase((current) => ({ ...current, facts: current.facts.filter((item) => item.targetPath !== fact.targetPath) }))} className="rounded p-1 text-muted hover:bg-accent hover:text-primary"><X className="h-4 w-4" /></button></div>)}</div></div>
        <button type="button" onClick={addCase} disabled={!canAddCurrentCase} className="mt-5 inline-flex items-center gap-2 rounded border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40"><Plus className="h-4 w-4" />Add representative case</button></div>

        {draftCases.length > 0 && <div className="mt-6 divide-y divide-border border-y border-border">{draftCases.map((item) => <article key={item.caseReference} className="flex items-start justify-between gap-4 py-4"><div><h5 className="text-sm font-semibold">{item.caseReference}</h5><p className="mt-1 text-sm text-muted">{item.description}</p><p className="mt-2 text-xs text-muted">{item.facts.length} policy facts  |  {decisionLabels[item.recordedDecision]}</p></div><button type="button" aria-label={`Remove ${item.caseReference}`} onClick={() => setDraftCases((current) => current.filter((caseItem) => caseItem.caseReference !== item.caseReference))} className="rounded p-1 text-muted hover:bg-accent hover:text-primary"><X className="h-4 w-4" /></button></article>)}</div>}
        <button type="button" onClick={() => void createSuite()} disabled={creating || !canSubmitSuite} className="mt-6 inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40"><Send className="h-4 w-4" />{creating ? 'Submitting...' : 'Submit for independent certification'}</button>
      </section>}

      {loading && <p className="text-sm text-muted">Loading outcome calibration workspace...</p>}
      {loadingSuite && <p className="text-sm text-muted">Loading calibration suite...</p>}
      {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {!loading && !error && suites.length === 0 && <p className="text-sm text-muted">No outcome calibration suites have been submitted for this domain.</p>}
      {!loading && <div className="divide-y divide-border border-y border-border">{suites.map((suite) => <button key={suite.suite_id} type="button" onClick={() => void openSuite(suite.suite_id)} className="flex w-full items-center justify-between gap-4 px-1 py-4 text-left hover:bg-accent"><span><span className="block font-medium">{suite.name}</span><span className="mt-1 block text-sm text-muted">Release {suite.release_version}  |  {suite.case_count} cases  |  {dataBasisLabel(suite.data_basis)}</span></span><span className="text-sm font-medium">{suite.status}</span></button>)}</div>}
    </div>
  );
}
