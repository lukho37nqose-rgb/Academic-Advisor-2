import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  ClipboardCheck,
  FileText,
  Scale,
  XCircle,
} from 'lucide-react';
import type { GraphNode, ReasoningGraph } from '../api/client';
import { SubjectDecisionReview } from './SubjectDecisionReview';

type PositionState = 'satisfied' | 'not_satisfied' | 'human_review' | 'indeterminate';

type PositionPresentation = {
  state: PositionState;
  title: string;
  summary: string;
  process: string;
  icon: typeof CheckCircle2;
  panelClassName: string;
  iconClassName: string;
};

function positionPresentation(conclusion?: GraphNode): PositionPresentation {
  const outcome = conclusion?.data.overall_passed;
  if (outcome === 'NEEDS_MANUAL_REVIEW') {
    return {
      state: 'human_review',
      title: 'Human consideration is required',
      summary: 'Your record meets a condition that needs human consideration under the published process.',
      process: 'This is not, by itself, a final institutional decision or an adverse outcome.',
      icon: AlertTriangle,
      panelClassName: 'border-amber-200 bg-amber-50 text-amber-950',
      iconClassName: 'text-amber-700',
    };
  }
  if (outcome === true) {
    return {
      state: 'satisfied',
      title: 'The evaluated policy conditions are satisfied',
      summary: 'Based on the authorised record used for this trace, the published conditions evaluated here are currently satisfied.',
      process: 'This view explains the policy application. It does not replace a separate institutional confirmation or committee process.',
      icon: CheckCircle2,
      panelClassName: 'border-emerald-200 bg-emerald-50 text-emerald-950',
      iconClassName: 'text-emerald-700',
    };
  }
  if (outcome === false) {
    return {
      state: 'not_satisfied',
      title: 'One or more evaluated conditions are not yet satisfied',
      summary: 'The trace identifies the conditions that did not pass against the authorised record used for this evaluation.',
      process: 'This view does not change an institutional record or replace a separate institutional decision process.',
      icon: XCircle,
      panelClassName: 'border-rose-200 bg-rose-50 text-rose-950',
      iconClassName: 'text-rose-700',
    };
  }
  return {
    state: 'indeterminate',
    title: 'Your policy position needs institutional review',
    summary: 'The available trace does not contain a complete policy position that can be shown safely.',
    process: 'This is not a final institutional decision. An authorised institutional reviewer needs to confirm the next step.',
    icon: AlertTriangle,
    panelClassName: 'border-amber-200 bg-amber-50 text-amber-950',
    iconClassName: 'text-amber-700',
  };
}

function displayValue(value: unknown): string {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (value === null || value === undefined || value === '') return 'Not recorded';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return 'Recorded value available';
}

function displayOperator(value: unknown): string {
  const labels: Record<string, string> = {
    '==': 'is exactly',
    '!=': 'is not',
    '>=': 'is at least',
    '<=': 'is at most',
    '>': 'is greater than',
    '<': 'is less than',
    includes: 'includes',
  };
  return typeof value === 'string' ? labels[value] ?? value : 'matches';
}

function requirementStatus(node: GraphNode): { label: string; className: string } {
  if (node.data.passed === 'NEEDS_MANUAL_REVIEW') {
    return { label: 'Human review required', className: 'text-amber-800' };
  }
  if (node.data.passed === true) {
    return { label: 'Satisfied', className: 'text-emerald-800' };
  }
  return { label: 'Not yet satisfied', className: 'text-rose-800' };
}

export function SubjectPositionView({ graph }: { graph: ReasoningGraph }) {
  const nodes = Object.values(graph.nodes);
  const conclusion = nodes.find((node) => node.type === 'conclusion');
  const facts = nodes.filter((node) => node.type === 'fact');
  const requirements = nodes.filter((node) => node.type === 'rule_evaluation');
  const presentation = positionPresentation(conclusion);
  const StatusIcon = presentation.icon;
  const releaseVersion = graph.evaluation_context?.release_version ?? 'Recorded release';
  const domainId = graph.evaluation_context?.domain_id;

  return (
    <div className="mx-auto w-full max-w-4xl py-6">
      <section aria-labelledby="position-heading" className="border-b border-border pb-6">
        <p className="text-sm font-medium text-muted">Your current position</p>
        <h2 id="position-heading" className="mt-1 text-2xl font-semibold">How the published policy applies to your record</h2>
        <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted">
          <span>Policy release {releaseVersion}</span>
          {domainId && <span>Decision area {domainId}</span>}
          <span>Trace {graph.id}</span>
        </div>
      </section>

      <section aria-labelledby="where-heading" data-position-state={presentation.state} className={`mt-6 border p-5 ${presentation.panelClassName}`}>
        <div className="flex items-start gap-3">
          <StatusIcon aria-hidden="true" className={`mt-0.5 h-6 w-6 shrink-0 ${presentation.iconClassName}`} />
          <div>
            <h3 id="where-heading" className="text-lg font-semibold">{presentation.title}</h3>
            <p className="mt-2 text-sm leading-relaxed">{presentation.summary}</p>
          </div>
        </div>
      </section>

      <section aria-labelledby="why-heading" className="mt-10">
        <div className="flex items-center gap-2">
          <Scale aria-hidden="true" className="h-5 w-5 text-muted" />
          <h3 id="why-heading" className="text-lg font-semibold">Why this is your current position</h3>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">Each item below applies the same published policy release to the authorised record used for this trace.</p>
        {requirements.length === 0 ? (
          <p className="mt-5 text-sm text-muted">No individual policy conditions were recorded in this trace.</p>
        ) : (
          <div className="mt-5 divide-y divide-border border-y border-border">
            {requirements.map((requirement) => {
              const status = requirementStatus(requirement);
              const expectedValue = requirement.data.expected_value;
              return (
                <article key={requirement.id} className="py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <h4 className="text-sm font-semibold">{requirement.label}</h4>
                    <span className={`text-sm font-medium ${status.className}`}>{status.label}</span>
                  </div>
                  {requirement.data.expected_condition && (
                    <p className="mt-2 text-sm text-muted">
                      Published condition: {displayOperator(requirement.data.expected_condition)} {displayValue(expectedValue)}
                    </p>
                  )}
                  {typeof requirement.data.citation === 'string' && requirement.data.citation && (
                    <p className="mt-2 text-xs text-muted">Policy source: {requirement.data.citation}</p>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>

      <section aria-labelledby="record-heading" className="mt-10">
        <div className="flex items-center gap-2">
          <FileText aria-hidden="true" className="h-5 w-5 text-muted" />
          <h3 id="record-heading" className="text-lg font-semibold">Record used for this view</h3>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">These are the facts the institution recorded and used for this trace. A fact can be challenged without changing the published policy.</p>
        {facts.length === 0 ? (
          <p className="mt-5 text-sm text-muted">No resolved facts were recorded in this trace.</p>
        ) : (
          <dl className="mt-5 grid gap-x-8 gap-y-4 border-y border-border py-5 sm:grid-cols-2">
            {facts.map((fact) => (
              <div key={fact.id}>
                <dt className="text-sm font-medium">{fact.label.replace(/^Fact:\s*/, '')}</dt>
                <dd className="mt-1 text-sm text-muted">{displayValue(fact.data.resolved_value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section aria-labelledby="process-heading" className="mt-10 border-y border-border py-6">
        <div className="flex items-center gap-2">
          <ClipboardCheck aria-hidden="true" className="h-5 w-5 text-muted" />
          <h3 id="process-heading" className="text-lg font-semibold">What process applies</h3>
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">{presentation.process}</p>
      </section>

      <section aria-labelledby="options-heading" className="mt-10 border-t border-border pt-6">
        <div className="flex items-center gap-2">
          <CircleHelp aria-hidden="true" className="h-5 w-5 text-muted" />
          <h3 id="options-heading" className="text-lg font-semibold">What you can do</h3>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">You can request a review of a fact, missing evidence, policy interpretation, or accessibility concern. You can also use the approved policy guide and assistance route available for your institution.</p>
        <SubjectDecisionReview graph={graph} />
      </section>
    </div>
  );
}
