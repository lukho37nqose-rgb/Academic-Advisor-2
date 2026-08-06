import {
  CheckCircle2,
  XCircle,
  Info,
  UserCircle
} from 'lucide-react';
import type { GraphNode, ReasoningGraph } from '../api/client';
import { SubjectDecisionReview } from './SubjectDecisionReview';

type PositionState = 'satisfied' | 'not_satisfied' | 'human_review' | 'indeterminate';

type PositionPresentation = {
  state: PositionState;
  title: string;
  meaning: string;
  action: string;
  icon: typeof CheckCircle2;
  panelClassName: string;
  iconClassName: string;
};

function positionPresentation(conclusion?: GraphNode): PositionPresentation {
  const outcome = conclusion?.data.overall_passed;
  if (outcome === 'NEEDS_MANUAL_REVIEW') {
    return {
      state: 'human_review',
      title: 'Your situation needs human consideration.',
      meaning: 'Your record contains information that requires a person to review it under the published process. This is not a final decision.',
      action: 'An authorised institutional reviewer will look at your case. You do not need to take action right now unless contacted.',
      icon: UserCircle,
      panelClassName: 'border-amber-200 bg-amber-50 text-amber-950',
      iconClassName: 'text-amber-700',
    };
  }
  if (outcome === true) {
    return {
      state: 'satisfied',
      title: 'You meet the requirements to continue.',
      meaning: 'Based on your current record, you have satisfied the necessary conditions for this process.',
      action: 'This explains the policy conditions evaluated here. Your institution remains responsible for any separate registration or committee decision.',
      icon: CheckCircle2,
      panelClassName: 'border-emerald-200 bg-emerald-50 text-emerald-950',
      iconClassName: 'text-emerald-700',
    };
  }
  if (outcome === false) {
    return {
      state: 'not_satisfied',
      title: 'You do not currently meet the requirements.',
      meaning: 'Based on your record, one or more conditions for this process have not been met.',
      action: 'You may need to seek a concession, submit missing evidence, or speak to an advisor about your options.',
      icon: XCircle,
      panelClassName: 'border-rose-200 bg-rose-50 text-rose-950',
      iconClassName: 'text-rose-700',
    };
  }
  return {
    state: 'indeterminate',
    title: 'Your position is currently unclear.',
    meaning: 'We cannot determine your position automatically based on the available information.',
    action: 'Please contact the responsible institutional office or support route for clarification.',
    icon: Info,
    panelClassName: 'border-slate-200 bg-slate-50 text-slate-950',
    iconClassName: 'text-slate-700',
  };
}

function displayValue(value: unknown): string {
  if (value === true) return 'Yes';
  if (value === false) return 'No';
  if (value === null || value === undefined || value === '') return 'Not recorded';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return 'Recorded value available';
}

function requirementStatus(value: unknown) {
  if (value === true) return { label: 'Met', className: 'text-emerald-800' };
  if (value === false) return { label: 'Not met', className: 'text-rose-800' };
  if (value === 'NEEDS_MANUAL_REVIEW') return { label: 'Needs human review', className: 'text-amber-800' };
  return { label: 'Not yet determined', className: 'text-slate-700' };
}

function recordPositionNote(graph: ReasoningGraph) {
  const context = graph.evaluation_context;
  if (!context) return null;
  const source = context.source_system || (context.source_authority === 'official_system' ? 'an official institutional system' : 'the records available to this service');
  const asOf = context.source_as_of ? new Date(context.source_as_of).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }) : null;
  if (context.record_state === 'provisional') return `This is a current, provisional position based on ${source}${asOf ? ` as of ${asOf}` : ''}. It can change when new records or an authorised decision are received.`;
  return `This position is based on a confirmed record from ${source}${asOf ? ` as of ${asOf}` : ''}. A later authorised correction or decision may still create a new position.`;
}

export function SubjectPositionView({ graph }: { graph: ReasoningGraph }) {
  const nodes = Object.values(graph.nodes);
  const conclusion = nodes.find((node) => node.type === 'conclusion');
  const facts = nodes.filter((node) => node.type === 'fact');
  const requirements = nodes.filter((node) => node.type === 'rule_evaluation');
  const presentation = positionPresentation(conclusion);
  const StatusIcon = presentation.icon;
  const recordNote = recordPositionNote(graph);

  // Find the primary reason (the first failed requirement, or the first passed one if all passed)
  const primaryReason = requirements.find(r => r.data.passed === false) ||
                        requirements.find(r => r.data.passed === 'NEEDS_MANUAL_REVIEW') ||
                        requirements[0];

  return (
    <div className="mx-auto w-full max-w-3xl py-8">
      <section aria-labelledby="position-heading">
        <h2 id="position-heading" className="text-sm font-semibold uppercase tracking-wider text-muted mb-4">Your current position</h2>

        <div className={`rounded-lg border p-6 ${presentation.panelClassName}`}>
          <div className="flex items-start gap-4">
            <StatusIcon aria-hidden="true" className={`mt-1 h-8 w-8 shrink-0 ${presentation.iconClassName}`} />
            <div>
              <h3 className="text-xl font-semibold mb-2">{presentation.title}</h3>
              {graph.explanation ? (
                <p className="text-base leading-relaxed">{graph.explanation}</p>
              ) : (
                <p className="text-base leading-relaxed">
                  {primaryReason ? `Because: ${primaryReason.label.replace(/^Rule:\s*/, '')}` : presentation.meaning}
                </p>
              )}
              <a href="#review-options" className="mt-4 inline-flex text-sm font-semibold underline underline-offset-4">Ask a question or request review</a>
            </div>
          </div>
        </div>
        {recordNote && <p className="mt-4 border-l-2 border-border pl-4 text-sm leading-relaxed text-muted">{recordNote}</p>}
      </section>

      {primaryReason && <section aria-labelledby="primary-reason-heading" className="mt-8 border-l-2 border-primary pl-5">
        <h3 id="primary-reason-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">What most affected this result</h3>
        <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
          <p className="font-medium">{primaryReason.label.replace(/^Rule:\s*/, '')}</p>
          <span className={`text-sm font-semibold ${requirementStatus(primaryReason.data.passed).className}`}>{requirementStatus(primaryReason.data.passed).label}</span>
        </div>
        {typeof primaryReason.data.citation === 'string' && primaryReason.data.citation && <p className="mt-2 text-sm text-muted">Policy source: {primaryReason.data.citation}</p>}
      </section>}

      <div className="mt-8 grid gap-8 sm:grid-cols-2">
        <section aria-labelledby="meaning-heading">
          <h3 id="meaning-heading" className="text-sm font-semibold uppercase tracking-wider text-muted mb-3">What this means now</h3>
          <p className="text-base leading-relaxed">{presentation.meaning}</p>
        </section>

        <section aria-labelledby="action-heading">
          <h3 id="action-heading" className="text-sm font-semibold uppercase tracking-wider text-muted mb-3">What you may need to do</h3>
          <p className="text-base leading-relaxed">{presentation.action}</p>
        </section>
      </div>

      <section aria-labelledby="requirements-heading" className="mt-12 border-t border-border pt-8">
        <h3 id="requirements-heading" className="text-sm font-semibold uppercase tracking-wider text-muted mb-4">Policy conditions considered</h3>
        {requirements.length === 0 ? <p className="text-sm text-muted">No individual policy conditions were recorded for this trace.</p> : (
          <div className="space-y-3">
            {requirements.map((requirement) => (
              <article key={requirement.id} className="border-l-2 border-border pl-4">
                <div className="flex flex-wrap items-start justify-between gap-3"><p className="font-medium">{requirement.label.replace(/^Rule:\s*/, '')}</p><span className={`text-sm font-semibold ${requirementStatus(requirement.data.passed).className}`}>{requirementStatus(requirement.data.passed).label}</span></div>
                {typeof requirement.data.citation === 'string' && requirement.data.citation && <p className="mt-1 text-sm text-muted">Policy source: {requirement.data.citation}</p>}
              </article>
            ))}
          </div>
        )}
      </section>

      <section id="review-options" aria-labelledby="options-heading" className="mt-12 border-t border-border pt-8">
        <h3 id="options-heading" className="text-sm font-semibold uppercase tracking-wider text-muted mb-4">Need to challenge or clarify this?</h3>
        <p className="mb-6 text-base leading-relaxed text-muted">
          If you believe information is missing, a rule was applied incorrectly, or you have exceptional circumstances, you can start a review. You do not need to know the exact policy name to ask for help.
        </p>
        <SubjectDecisionReview graph={graph} />
      </section>

      {/* Institutional Details (Collapsible or secondary) */}
      <details className="mt-12 group border-t border-border pt-6">
        <summary className="cursor-pointer text-sm font-medium text-muted hover:text-foreground transition-colors">
          View institutional details and record history
        </summary>
        <div className="mt-6 space-y-8">
          <section>
            <h4 className="text-sm font-semibold mb-3">Record used for this view</h4>
            {facts.length === 0 ? (
              <p className="text-sm text-muted">No resolved facts were recorded.</p>
            ) : (
              <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2 bg-slate-50 p-4 rounded-md border border-slate-100">
                {facts.map((fact) => (
                  <div key={fact.id}>
                    <dt className="text-xs font-medium text-muted">{fact.label.replace(/^Fact:\s*/, '')}</dt>
                    <dd className="mt-1 text-sm">{displayValue(fact.data.resolved_value)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
          <section>
            <h4 className="text-sm font-semibold mb-3">Policy Application</h4>
            <div className="bg-slate-50 p-4 rounded-md border border-slate-100 text-sm">
              <p className="text-muted mb-2">Trace ID: <span className="font-mono text-xs">{graph.id}</span></p>
              <p className="text-muted">Release: <span className="font-mono text-xs">{graph.evaluation_context?.release_version ?? 'Recorded release'}</span></p>
            </div>
          </section>
        </div>
      </details>
    </div>
  );
}
