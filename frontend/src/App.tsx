import { useState } from 'react';
import { ReasoningGraphView } from './components/ReasoningGraphView';
import { GovernanceDesk } from './components/GovernanceDesk';
import { InstitutionalIntake } from './components/InstitutionalIntake';
import { PublicPolicyGuide } from './components/PublicPolicyGuide';
import { AssistanceInbox } from './components/AssistanceInbox';
import { PolicyReview } from './components/PolicyReview';
import { HandbookIntake } from './components/HandbookIntake';
import { DecisionReviewInbox } from './components/DecisionReviewInbox';
import { PolicyAmbiguityRegister } from './components/PolicyAmbiguityRegister';
import { evaluateEvidence, fetchReasoningGraph } from './api/client';
import type { ReasoningGraph } from './api/client';
import { FileSearch, BookOpen, Building2, Settings, LayoutGrid, ShieldCheck, Inbox, ClipboardCheck, Files, MessageSquareWarning, Scale } from 'lucide-react';

type ActiveView = 'investigations' | 'governance' | 'institution_setup' | 'policy_guides' | 'assistance_inbox' | 'decision_review_inbox' | 'policy_review' | 'policy_ambiguities' | 'handbook_intake';

const viewHeading: Record<ActiveView, [string, string]> = {
  investigations: ['Investigations', 'Academic Standing Review'],
  governance: ['Governance Desk', 'Tier 1 Controls'],
  institution_setup: ['Institution Setup', 'Policy Draft'],
  policy_guides: ['Policy Guides', 'Approved Policy'],
  assistance_inbox: ['Assistance Inbox', 'Human Follow-up'],
  decision_review_inbox: ['Decision Review', 'Casework'],
  policy_review: ['Policy Review', 'Release Approval'],
  policy_ambiguities: ['Policy Register', 'Interpretations'],
  handbook_intake: ['Handbook Intake', 'Source Verification'],
};

function App() {
  const [graph, setGraph] = useState<ReasoningGraph | null>(null);
  const [activeView, setActiveView] = useState<ActiveView>('investigations');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // In a real app, this would be a multi-step form. 
  // For the sandbox, we trigger the demo evaluation flow.
  const handleRunEvaluation = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Trigger evaluate (using dummy evidence ID, assuming demo fallback logic)
      const summary = await evaluateEvidence("demo_evidence", "mock_rule_graph", "student_123");
      
      // 2. Fetch the generated reasoning graph
      const fullGraph = await fetchReasoningGraph(summary.reasoning_graph_id);
      setGraph(fullGraph);
    } catch (err: any) {
      setError(err.message || "Failed to run evaluation");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-white">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border flex flex-col">
        <div className="p-6 border-b border-border">
          <h1 className="text-lg font-semibold tracking-tight">Knowledge Studio</h1>
          <p className="text-xs text-muted mt-1">Institutional Reasoning</p>
        </div>
        <nav className="flex-1 p-4 space-y-1">
          <button
            type="button"
            onClick={() => setActiveView('investigations')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'investigations' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <FileSearch className="w-4 h-4 text-muted" />
            Investigations
          </button>
          <button
            type="button"
            onClick={() => setActiveView('governance')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'governance' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <ShieldCheck className="w-4 h-4 text-muted" />
            Governance Desk
          </button>
          <button
            type="button"
            onClick={() => setActiveView('institution_setup')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'institution_setup' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <Building2 className="w-4 h-4 text-muted" />
            Institution Setup
          </button>
          <button
            type="button"
            onClick={() => setActiveView('handbook_intake')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'handbook_intake' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <Files className="w-4 h-4 text-muted" />
            Handbook Intake
          </button>
          <button
            type="button"
            onClick={() => setActiveView('policy_guides')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'policy_guides' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <BookOpen className="w-4 h-4" />
            Policy Guides
          </button>
          <button
            type="button"
            onClick={() => setActiveView('assistance_inbox')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'assistance_inbox' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <Inbox className="w-4 h-4" />
            Assistance Inbox
          </button>
          <button
            type="button"
            onClick={() => setActiveView('decision_review_inbox')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'decision_review_inbox' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <MessageSquareWarning className="w-4 h-4" />
            Review Cases
          </button>
          <button
            type="button"
            onClick={() => setActiveView('policy_review')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'policy_review' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <ClipboardCheck className="w-4 h-4" />
            Policy Review
          </button>
          <button
            type="button"
            onClick={() => setActiveView('policy_ambiguities')}
            className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${
              activeView === 'policy_ambiguities' ? 'bg-accent' : 'text-muted hover:bg-accent'
            }`}
          >
            <Scale className="w-4 h-4" />
            Policy Register
          </button>
          <button type="button" className="flex w-full items-center gap-3 px-3 py-2 text-muted hover:bg-accent rounded text-left text-sm font-medium transition-colors">
            <LayoutGrid className="w-4 h-4" />
            Workflows
          </button>
        </nav>
        <div className="p-4 border-t border-border">
          <button type="button" className="flex w-full items-center gap-3 px-3 py-2 text-muted hover:bg-accent rounded text-left text-sm font-medium transition-colors">
            <Settings className="w-4 h-4" />
            Settings
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="h-16 border-b border-border flex items-center justify-between px-8">
           <div className="flex items-center gap-2 text-sm text-muted">
             <span>{viewHeading[activeView][0]}</span>
             <span>/</span>
             <span className="text-primary font-medium">{viewHeading[activeView][1]}</span>
           </div>
           {activeView === 'investigations' && (
             <button
                onClick={handleRunEvaluation}
                disabled={loading}
                className="px-4 py-2 bg-primary text-white text-sm font-medium rounded hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
               {loading ? 'Evaluating...' : 'Begin Investigation'}
             </button>
           )}
        </header>
        
        <div className="flex-1 overflow-y-auto p-8">
           {activeView === 'investigations' && (
             <>
               {error && (
                 <div className="max-w-4xl mx-auto p-4 bg-rose-50 text-rose-600 rounded border border-rose-200 mb-8">
                   {error}
                 </div>
               )}

               {!graph && !loading && !error && (
                 <div className="h-full flex items-center justify-center">
                   <div className="max-w-md text-center">
                     <div className="w-16 h-16 bg-accent rounded flex items-center justify-center mx-auto mb-6">
                        <FileSearch className="w-8 h-8 text-muted" />
                     </div>
                     <h2 className="text-xl font-semibold mb-2">No active trace</h2>
                     <p className="text-muted text-sm leading-relaxed">
                       Upload evidence and begin an investigation to see how the Institutional Engine applies policy rules to the facts.
                     </p>
                   </div>
                 </div>
               )}

               {graph && <ReasoningGraphView graph={graph} />}
             </>
           )}
           {activeView === 'governance' && <GovernanceDesk />}
           {activeView === 'institution_setup' && <InstitutionalIntake />}
           {activeView === 'policy_guides' && <PublicPolicyGuide />}
           {activeView === 'assistance_inbox' && <AssistanceInbox />}
           {activeView === 'decision_review_inbox' && <DecisionReviewInbox />}
           {activeView === 'policy_review' && <PolicyReview />}
           {activeView === 'policy_ambiguities' && <PolicyAmbiguityRegister />}
           {activeView === 'handbook_intake' && <HandbookIntake />}
        </div>
      </main>
    </div>
  );
}

export default App;
