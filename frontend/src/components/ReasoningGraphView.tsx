import React from 'react';
import type { ReasoningGraph } from '../api/client';
import { CheckCircle2, XCircle, AlertCircle, FileText } from 'lucide-react';
import { SubjectDecisionReview } from './SubjectDecisionReview';

interface Props {
  graph: ReasoningGraph | null;
  showDecisionReview?: boolean;
}

const NodeIcon = ({ type, passed }: { type: string, passed?: boolean | string }) => {
  if (type === 'fact') return <FileText className="w-5 h-5 text-blue-500" />;
  if (passed === 'NEEDS_MANUAL_REVIEW') return <AlertCircle className="w-5 h-5 text-amber-500" />;
  if (passed === true) return <CheckCircle2 className="w-5 h-5 text-emerald-500" />;
  if (passed === false) return <XCircle className="w-5 h-5 text-rose-500" />;
  return <div className="w-5 h-5 rounded-full bg-gray-200" />;
};

export const ReasoningGraphView: React.FC<Props> = ({ graph, showDecisionReview = false }) => {
  if (!graph) return <div className="p-8 text-center text-muted">Loading graph data...</div>;

  // We sort nodes conceptually: Facts -> Evaluations -> Conclusion
  const nodesList = Object.values(graph.nodes);
  const facts = nodesList.filter(n => n.type === 'fact');
  const evaluations = nodesList.filter(n => n.type === 'rule_evaluation');
  const conclusion = nodesList.find(n => n.type === 'conclusion');

  return (
    <div className="max-w-4xl mx-auto py-8">
      <div className="mb-12 border-b border-border pb-8">
        <h2 className="text-sm font-semibold tracking-wide uppercase text-muted mb-2">Final Conclusion</h2>
        {conclusion && (
          <div className={`p-6 rounded-lg flex items-center gap-4 ${
            conclusion.data.overall_passed === true ? 'bg-emerald-50 border border-emerald-200' :
            conclusion.data.overall_passed === 'NEEDS_MANUAL_REVIEW' ? 'bg-amber-50 border border-amber-200' :
            'bg-rose-50 border border-rose-200'
          }`}>
             <NodeIcon type="conclusion" passed={conclusion.data.overall_passed} />
             <div>
               <h1 className="text-2xl font-semibold">
                 {conclusion.data.overall_passed === true ? 'Eligible' : 
                  conclusion.data.overall_passed === 'NEEDS_MANUAL_REVIEW' ? 'Needs Manual Review' : 
                  'Ineligible'}
               </h1>
               <p className="text-sm opacity-80 mt-1">Confidence Score: {(conclusion.computed_confidence * 100).toFixed(1)}%</p>
             </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
        <div>
          <h2 className="text-sm font-semibold tracking-wide uppercase text-muted mb-4">Resolved Facts</h2>
          <div className="space-y-4">
            {facts.map(fact => (
              <div key={fact.id} className="p-4 rounded border border-border bg-white shadow-sm flex items-start gap-3">
                <NodeIcon type="fact" />
                <div>
                  <h3 className="font-medium text-sm">{fact.label.replace('Fact: ', '')}</h3>
                  <p className="text-lg mt-1">{String(fact.data.resolved_value)}</p>
                  <p className="text-xs text-muted mt-2">Confidence: {(fact.computed_confidence * 100).toFixed(1)}%</p>
                </div>
              </div>
            ))}
            {facts.length === 0 && <p className="text-sm text-muted">No facts resolved.</p>}
          </div>
        </div>

        <div>
          <h2 className="text-sm font-semibold tracking-wide uppercase text-muted mb-4">Rule Evaluations (AST)</h2>
          <div className="space-y-4 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-border before:to-transparent">
            {evaluations.map(evalNode => (
              <div key={evalNode.id} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                <div className="flex items-center justify-center w-10 h-10 rounded-full border-4 border-white bg-white shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10">
                   <NodeIcon type="rule_evaluation" passed={evalNode.data.passed} />
                </div>
                <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded border border-border bg-white shadow-sm">
                  <div className="flex justify-between items-start">
                     <h3 className="font-medium text-sm">{evalNode.label}</h3>
                  </div>
                  {evalNode.data.expected_condition && (
                    <div className="mt-2 text-sm bg-accent p-2 rounded flex items-center gap-2">
                       <span className="font-mono">{evalNode.data.expected_condition}</span>
                       <span className="font-mono text-muted">{String(evalNode.data.expected_value)}</span>
                    </div>
                  )}
                  {evalNode.data.citation && (
                     <p className="text-xs text-muted mt-3 pt-3 border-t border-border italic">
                       Source: {evalNode.data.citation}
                     </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      {showDecisionReview && <SubjectDecisionReview graph={graph} />}
    </div>
  );
};
