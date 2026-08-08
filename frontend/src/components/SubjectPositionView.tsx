import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  FileText,
  Info,
  ListChecks,
  Scale,
  ShieldCheck,
  UserCircle,
  XCircle,
} from 'lucide-react';
import type { GraphNode, ReasoningGraph } from '../api/client';
import { SubjectDecisionReview } from './SubjectDecisionReview';

type PositionState = 'satisfied' | 'not_satisfied' | 'human_review' | 'indeterminate';

type PositionPresentation = {
  state: PositionState;
  eyebrow: string;
  title: string;
  meaning: string;
  action: string;
  icon: typeof CheckCircle2;
  panelClassName: string;
  iconClassName: string;
};

type StatusPresentation = {
  label: string;
  className: string;
};

function nodeData(node?: GraphNode): Record<string, unknown> {
  return node?.data && typeof node.data === 'object' ? node.data as Record<string, unknown> : {};
}

function cleanLabel(value: string) {
  return value.replace(/^Fact:\s*/, '').replace(/^Rule:\s*/, '').replace(/^Logical\s+/, 'Combined route: ');
}

function formatDateTime(value?: unknown) {
  if (typeof value !== 'string' || !value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function displayValue(value: unknown): string {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (value === 'NEEDS_MANUAL_REVIEW' || value === 'needs_human_review') return 'Needs human review';
  if (value === null || value === undefined || value === '') return 'Not recorded';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return 'Recorded value available';
}

function sourceAuthorityLabel(value: unknown) {
  if (value === 'official_system') return 'Official institutional record';
  if (value === 'institutional_working_record') return 'Institutional working record';
  if (value === 'subject_submitted') return 'Information submitted for consideration';
  return 'Governed institutional record';
}

function recordStateLabel(value: unknown) {
  if (value === 'confirmed') return 'Confirmed';
  if (value === 'provisional') return 'Provisional';
  return 'Recorded';
}

function expectedValueLabel(condition: GraphNode) {
  const data = nodeData(condition);
  const operator = data.expected_condition;
  const expected = data.expected_value;
  if (operator === undefined && expected === undefined) return 'Policy route';
  return `${String(operator ?? 'requires')} ${displayValue(expected)}`;
}

function requirementStatus(value: unknown): StatusPresentation {
  if (value === true) return { label: 'Satisfied', className: 'border-emerald-200 bg-emerald-50 text-emerald-800' };
  if (value === false) return { label: 'Not satisfied', className: 'border-rose-200 bg-rose-50 text-rose-800' };
  if (value === 'NEEDS_MANUAL_REVIEW') return { label: 'Needs review', className: 'border-amber-200 bg-amber-50 text-amber-800' };
  return { label: 'Unclear', className: 'border-slate-200 bg-slate-50 text-slate-700' };
}

function positionPresentation(conclusion?: GraphNode): PositionPresentation {
  const outcome = nodeData(conclusion).overall_passed;
  if (outcome === 'NEEDS_MANUAL_REVIEW') {
    return {
      state: 'human_review',
      eyebrow: 'Needs review',
      title: 'Your situation needs human consideration.',
      meaning: 'The available record does not support an automatic final position. A person needs to review the relevant information under the published process.',
      action: 'Use the review request below if information is missing, incorrect, or needs policy interpretation.',
      icon: UserCircle,
      panelClassName: 'border-amber-200 bg-amber-50 text-amber-950',
      iconClassName: 'text-amber-700',
    };
  }
  if (outcome === true) {
    return {
      state: 'satisfied',
      eyebrow: 'Current position',
      title: 'You meet the requirements to continue.',
      meaning: 'The accepted facts in this trace satisfy the published policy conditions Cacisa evaluated.',
      action: 'You can still request review if a displayed fact is wrong or important information is missing.',
      icon: CheckCircle2,
      panelClassName: 'border-emerald-200 bg-emerald-50 text-emerald-950',
      iconClassName: 'text-emerald-700',
    };
  }
  if (outcome === false) {
    return {
      state: 'not_satisfied',
      eyebrow: 'Current position',
      title: 'You do not currently meet the requirements.',
      meaning: 'One or more accepted facts in this trace did not satisfy the published policy conditions Cacisa evaluated.',
      action: 'Review the condition that did not pass, then request review if a fact, source, or policy interpretation should be checked.',
      icon: XCircle,
      panelClassName: 'border-rose-200 bg-rose-50 text-rose-950',
      iconClassName: 'text-rose-700',
    };
  }
  return {
    state: 'indeterminate',
    eyebrow: 'Current position',
    title: 'Your position is currently unclear.',
    meaning: 'The trace does not contain enough governed information to present a final policy position.',
    action: 'Request review or contact the responsible institutional route if you need this clarified.',
    icon: Info,
    panelClassName: 'border-slate-200 bg-slate-50 text-slate-950',
    iconClassName: 'text-slate-700',
  };
}

function recordPositionNote(graph: ReasoningGraph) {
  const context = graph.evaluation_context;
  if (!context) return null;
  const source = context.source_system || (context.source_authority === 'official_system' ? 'an official institutional system' : 'the records available to this service');
  const asOf = formatDateTime(context.source_as_of);
  if (context.record_state === 'provisional') return `This is a current, provisional position based on ${source}${asOf ? ` as of ${asOf}` : ''}. It can change when new records or an authorised decision are received.`;
  return `This position is based on a confirmed record from ${source}${asOf ? ` as of ${asOf}` : ''}. A later authorised correction or decision may still create a new position.`;
}

function conditionsWithFacts(graph: ReasoningGraph) {
  const nodes = Object.values(graph.nodes);
  const facts = nodes.filter((node) => node.type === 'fact');
  const factsById = new Map(facts.map((fact) => [fact.id, fact]));
  const incomingFactByCondition = new Map<string, GraphNode>();
  for (const edge of graph.edges) {
    const source = factsById.get(edge.source_id);
    if (source && edge.relation === 'evaluates_to') {
      incomingFactByCondition.set(edge.target_id, source);
    }
  }
  return nodes
    .filter((node) => node.type === 'rule_evaluation')
    .map((condition) => ({ condition, fact: incomingFactByCondition.get(condition.id) }));
}

function primaryCondition(rows: Array<{ condition: GraphNode; fact?: GraphNode }>) {
  return rows.find(({ condition }) => nodeData(condition).passed === false)
    || rows.find(({ condition }) => nodeData(condition).passed === 'NEEDS_MANUAL_REVIEW')
    || rows.find(({ condition }) => nodeData(condition).expected_condition !== undefined)
    || rows[0];
}

function PolicyCondition({ condition, fact }: { condition: GraphNode; fact?: GraphNode }) {
  const conditionData = nodeData(condition);
  const factData = nodeData(fact);
  const status = requirementStatus(conditionData.passed);
  const citation = typeof conditionData.citation === 'string' ? conditionData.citation : '';

  return (
    <article className="grid gap-4 border border-border p-4 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)]">
      <div>
        <div className="flex flex-wrap items-start gap-2">
          <h4 className="font-semibold">{cleanLabel(condition.label)}</h4>
          <span className={`border px-2 py-0.5 text-xs font-semibold ${status.className}`}>{status.label}</span>
        </div>
        {citation && <p className="mt-2 text-sm leading-relaxed text-muted">Policy source: {citation}</p>}
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-normal text-muted">Student information</p>
        <p className="mt-1 text-sm">{fact ? displayValue(factData.resolved_value) : 'Not recorded in this trace'}</p>
        {fact && <p className="mt-1 text-xs text-muted">{cleanLabel(fact.label)}</p>}
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-normal text-muted">Policy requirement</p>
        <p className="mt-1 text-sm">{expectedValueLabel(condition)}</p>
      </div>
    </article>
  );
}

function EvidenceItem({ fact, fallbackContext }: { fact: GraphNode; fallbackContext: ReasoningGraph['evaluation_context'] }) {
  const data = nodeData(fact);
  const source = data.source_system ?? fallbackContext?.source_system;
  const asOf = formatDateTime(data.source_as_of ?? fallbackContext?.source_as_of);
  return (
    <article className="border-l-2 border-border pl-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold">{cleanLabel(fact.label)}</h4>
          <p className="mt-1 text-sm text-muted">Value used: {displayValue(data.resolved_value)}</p>
        </div>
        <span className="text-sm font-medium text-primary">{recordStateLabel(data.record_state ?? fallbackContext?.record_state)}</span>
      </div>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        <div>
          <dt className="font-medium">Source authority</dt>
          <dd className="mt-1 text-muted">{sourceAuthorityLabel(data.source_authority ?? fallbackContext?.source_authority)}</dd>
        </div>
        <div>
          <dt className="font-medium">Source record</dt>
          <dd className="mt-1 text-muted">{source ? String(source) : 'Source recorded in the decision trace'}{asOf ? `, ${asOf}` : ''}</dd>
        </div>
      </dl>
    </article>
  );
}

function TraceSummary({ graph, conclusion, conditions }: { graph: ReasoningGraph; conclusion?: GraphNode; conditions: GraphNode[] }) {
  return (
    <details id="full-trace" className="border-t border-border pt-6">
      <summary className="cursor-pointer text-sm font-semibold text-primary underline underline-offset-4">View full reasoning trace</summary>
      <div className="mt-5 grid gap-5 text-sm">
        <dl className="grid gap-3 border border-border p-4 sm:grid-cols-2">
          <div><dt className="font-medium">Trace reference</dt><dd className="mt-1 font-mono text-xs text-muted">{graph.id}</dd></div>
          <div><dt className="font-medium">Policy release</dt><dd className="mt-1 text-muted">{graph.evaluation_context?.release_version ?? 'Recorded release'}</dd></div>
          <div><dt className="font-medium">Rule graph</dt><dd className="mt-1 font-mono text-xs text-muted">{graph.rule_graph_id}</dd></div>
          <div><dt className="font-medium">Conclusion confidence</dt><dd className="mt-1 text-muted">{conclusion ? `${(conclusion.computed_confidence * 100).toFixed(1)}%` : 'Not recorded'}</dd></div>
        </dl>
        {conditions.length > 0 && (
          <div>
            <h4 className="font-semibold">Trace sequence</h4>
            <ol className="mt-3 grid gap-2">
              {conditions.map((condition, index) => (
                <li key={condition.id} className="border-l-2 border-border pl-3">
                  <span className="text-xs text-muted">Step {index + 1}</span>
                  <p>{cleanLabel(condition.label)}: {requirementStatus(nodeData(condition).passed).label}</p>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </details>
  );
}

export function SubjectPositionView({ graph }: { graph: ReasoningGraph }) {
  const nodes = Object.values(graph.nodes);
  const conclusion = nodes.find((node) => node.type === 'conclusion');
  const facts = nodes.filter((node) => node.type === 'fact');
  const conditionRows = conditionsWithFacts(graph);
  const primary = primaryCondition(conditionRows);
  const presentation = positionPresentation(conclusion);
  const StatusIcon = presentation.icon;
  const recordNote = recordPositionNote(graph);

  return (
    <div className="mx-auto w-full max-w-5xl py-8">
      <section aria-labelledby="position-heading">
        <div className={`border p-6 ${presentation.panelClassName}`}>
          <div className="grid gap-5 md:grid-cols-[auto_minmax(0,1fr)]">
            <StatusIcon aria-hidden="true" className={`h-10 w-10 ${presentation.iconClassName}`} />
            <div>
              <p className="text-sm font-semibold">{presentation.eyebrow}</p>
              <h2 id="position-heading" className="mt-1 text-2xl font-semibold tracking-normal">{presentation.title}</h2>
              <p className="mt-3 max-w-3xl text-base leading-relaxed">{graph.explanation || presentation.meaning}</p>
              {primary && (
                <p className="mt-4 max-w-3xl text-sm leading-relaxed">
                  Most important condition: <span className="font-semibold">{cleanLabel(primary.condition.label)}</span>
                  {' '}is <span className="font-semibold">{requirementStatus(nodeData(primary.condition).passed).label.toLowerCase()}</span>.
                </p>
              )}
            </div>
          </div>
        </div>
        {recordNote && <p className="mt-4 border-l-2 border-border pl-4 text-sm leading-relaxed text-muted">{recordNote}</p>}
      </section>

      <nav aria-label="Decision actions" className="mt-6 flex flex-wrap gap-3">
        <a href="#why" className="inline-flex items-center gap-2 border border-border px-3 py-2 text-sm font-semibold hover:bg-accent"><ListChecks className="h-4 w-4" />See conditions</a>
        <a href="#information-used" className="inline-flex items-center gap-2 border border-border px-3 py-2 text-sm font-semibold hover:bg-accent"><FileText className="h-4 w-4" />See information used</a>
        <a href="#full-trace" className="inline-flex items-center gap-2 border border-border px-3 py-2 text-sm font-semibold hover:bg-accent"><Scale className="h-4 w-4" />View full trace</a>
        <a href="#review-options" className="inline-flex items-center gap-2 border border-border px-3 py-2 text-sm font-semibold hover:bg-accent"><AlertTriangle className="h-4 w-4" />Request review</a>
      </nav>

      <section id="why" aria-labelledby="why-heading" className="mt-10">
        <div className="flex items-center gap-2">
          <ListChecks aria-hidden="true" className="h-5 w-5 text-muted" />
          <h3 id="why-heading" className="text-xl font-semibold">Why Cacisa reached this position</h3>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">These are the governed policy conditions recorded in the trace. They show the student's relevant information beside the requirement and citation used at evaluation time.</p>
        {conditionRows.length === 0 ? (
          <p className="mt-5 border-l-2 border-border pl-4 text-sm text-muted">No individual policy conditions were recorded for this trace.</p>
        ) : (
          <div className="mt-5 grid gap-3">
            {conditionRows.map(({ condition, fact }) => <PolicyCondition key={condition.id} condition={condition} fact={fact} />)}
          </div>
        )}
      </section>

      <section id="information-used" aria-labelledby="information-heading" className="mt-12 border-t border-border pt-8">
        <div className="flex items-center gap-2">
          <ClipboardList aria-hidden="true" className="h-5 w-5 text-muted" />
          <h3 id="information-heading" className="text-xl font-semibold">Information Cacisa used</h3>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">This is the accepted, decision-bound information visible in the trace. It is shown as student language first, with enough provenance to trace it back to the governed record.</p>
        {facts.length === 0 ? (
          <p className="mt-5 border-l-2 border-border pl-4 text-sm text-muted">No accepted facts were recorded for this trace.</p>
        ) : (
          <div className="mt-5 grid gap-5">
            {facts.map((fact) => <EvidenceItem key={fact.id} fact={fact} fallbackContext={graph.evaluation_context} />)}
          </div>
        )}
      </section>

      <section aria-labelledby="policy-heading" className="mt-12 border-t border-border pt-8">
        <div className="flex items-center gap-2">
          <ShieldCheck aria-hidden="true" className="h-5 w-5 text-muted" />
          <h3 id="policy-heading" className="text-xl font-semibold">Published policy sources</h3>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">The trace binds the outcome to the release and citations below. Current policy or repaired evidence does not silently replace this historical decision trace.</p>
        <dl className="mt-5 grid gap-4 border border-border p-4 sm:grid-cols-2">
          <div><dt className="font-medium">Release used</dt><dd className="mt-1 text-sm text-muted">{graph.evaluation_context?.release_version ?? 'Recorded release'}</dd></div>
          <div><dt className="font-medium">Trace reference</dt><dd className="mt-1 font-mono text-xs text-muted">{graph.id}</dd></div>
        </dl>
        <ul className="mt-5 grid gap-2 text-sm">
          {conditionRows
            .map(({ condition }) => nodeData(condition).citation)
            .filter((citation): citation is string => typeof citation === 'string' && citation.length > 0)
            .filter((citation, index, citations) => citations.indexOf(citation) === index)
            .map((citation) => <li key={citation} className="border-l-2 border-border pl-3">{citation}</li>)}
        </ul>
      </section>

      <section id="review-options" aria-labelledby="options-heading" className="mt-12 border-t border-border pt-8">
        <h3 id="options-heading" className="text-xl font-semibold">What you can do</h3>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">{presentation.action}</p>
        <SubjectDecisionReview graph={graph} />
      </section>

      <div className="mt-12">
        <TraceSummary graph={graph} conclusion={conclusion} conditions={conditionRows.map(({ condition }) => condition)} />
      </div>
    </div>
  );
}
