import { useEffect, useState, type ComponentType } from 'react';
import { AssistanceInbox } from './components/AssistanceInbox';
import { DecisionReviewInbox } from './components/DecisionReviewInbox';
import { GovernanceDesk } from './components/GovernanceDesk';
import { HandbookIntake } from './components/HandbookIntake';
import { InstitutionalIntake } from './components/InstitutionalIntake';
import { InstitutionalTimeline } from './components/InstitutionalTimeline';
import { EvidenceFactReview } from './components/EvidenceFactReview';
import { PolicyAmbiguityRegister } from './components/PolicyAmbiguityRegister';
import { PolicyReview } from './components/PolicyReview';
import { PublicPolicyGuide } from './components/PublicPolicyGuide';
import { SubjectPositionView } from './components/SubjectPositionView';
import { SubjectInstitutionalTimeline } from './components/SubjectInstitutionalTimeline';
import { ShadowCalibration } from './components/ShadowCalibration';
import { SystemRecordImport } from './components/SystemRecordImport';
import { fetchReasoningGraph, fetchSessionCapabilities } from './api/client';
import type { ReasoningGraph, SessionCapabilities } from './api/client';
import {
  Building2,
  ClipboardCheck,
  FileCheck2,
  Files,
  Inbox,
  Landmark,
  MessageSquareWarning,
  Scale,
  ShieldCheck,
  TableProperties,
  TestTube2,
  type LucideProps,
} from 'lucide-react';

type ActiveView =
  | 'governance'
  | 'institution_setup'
  | 'assistance_inbox'
  | 'decision_review_inbox'
  | 'policy_review'
  | 'policy_ambiguities'
  | 'handbook_intake'
  | 'record_import'
  | 'shadow_calibration'
  | 'institutional_timeline'
  | 'evidence_facts';

type NavigationItem = {
  view: ActiveView;
  label: string;
  icon: ComponentType<LucideProps>;
};

const navigationItems: NavigationItem[] = [
  { view: 'governance', label: 'Governance Desk', icon: ShieldCheck },
  { view: 'institution_setup', label: 'Institution Setup', icon: Building2 },
  { view: 'handbook_intake', label: 'Handbook Intake', icon: Files },
  { view: 'record_import', label: 'System Records', icon: TableProperties },
  { view: 'assistance_inbox', label: 'Assistance Inbox', icon: Inbox },
  { view: 'decision_review_inbox', label: 'Review Cases', icon: MessageSquareWarning },
  { view: 'policy_review', label: 'Policy Review', icon: ClipboardCheck },
  { view: 'policy_ambiguities', label: 'Policy Register', icon: Scale },
  { view: 'shadow_calibration', label: 'Shadow Calibration', icon: TestTube2 },
  { view: 'institutional_timeline', label: 'Institutional Timeline', icon: Landmark },
  { view: 'evidence_facts', label: 'Evidence Facts', icon: FileCheck2 },
];

const viewHeading: Record<ActiveView, [string, string]> = {
  governance: ['Governance Desk', 'Tier 1 Controls'],
  institution_setup: ['Institution Setup', 'Policy Draft'],
  assistance_inbox: ['Assistance Inbox', 'Human Follow-up'],
  decision_review_inbox: ['Decision Review', 'Casework'],
  policy_review: ['Policy Review', 'Release Approval'],
  policy_ambiguities: ['Policy Register', 'Interpretations'],
  handbook_intake: ['Handbook Intake', 'Source Verification'],
  record_import: ['System Records', 'CSV Preview'],
  shadow_calibration: ['Shadow Calibration', 'Non-operative Comparison'],
  institutional_timeline: ['Institutional Timeline', 'Context History'],
  evidence_facts: ['Evidence Facts', 'Independent Review'],
};

function isActiveView(value: string): value is ActiveView {
  return navigationItems.some((item) => item.view === value);
}

function errorMessage(error: unknown) {
  const message = error as { message?: string };
  return message.message || 'This decision could not be loaded.';
}

function App() {
  const [capabilities, setCapabilities] = useState<SessionCapabilities | null>(null);
  const [capabilityLoading, setCapabilityLoading] = useState(true);
  const [capabilityError, setCapabilityError] = useState(false);
  const [selectedView, setSelectedView] = useState<ActiveView>('governance');
  const [graph, setGraph] = useState<ReasoningGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);

  const searchParameters = new URLSearchParams(window.location.search);
  const requestedSubjectExperience = searchParameters.get('experience') === 'subject';
  const requestedTraceId = searchParameters.get('trace');

  useEffect(() => {
    let active = true;
    fetchSessionCapabilities()
      .then((response) => {
        if (active) setCapabilities(response);
      })
      .catch(() => {
        if (active) setCapabilityError(true);
      })
      .finally(() => {
        if (active) setCapabilityLoading(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (capabilities?.experience !== 'subject' || !requestedTraceId) return;
    let active = true;
    setGraphLoading(true);
    setGraphError(null);
    void fetchReasoningGraph(requestedTraceId)
      .then((response) => active && setGraph(response))
      .catch((requestError: unknown) => active && setGraphError(errorMessage(requestError)))
      .finally(() => active && setGraphLoading(false));
    return () => { active = false; };
  }, [capabilities?.experience, requestedTraceId]);

  if (capabilityLoading) {
    return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><p className="mx-auto max-w-5xl text-sm text-muted">Checking account access...</p></main>;
  }

  if (capabilityError || !capabilities) {
    return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><div role="alert" className="mx-auto max-w-5xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">We could not verify this account's access. Sign in again or contact your institution.</div></main>;
  }

  if (requestedSubjectExperience && capabilities.experience !== 'subject') {
    return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><div role="alert" className="mx-auto max-w-5xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">This account is not permitted to open a subject decision view.</div></main>;
  }

  if (capabilities.experience === 'subject') {
    return (
      <main className="min-h-screen bg-white px-4 py-8 sm:px-8">
        <div className="mx-auto max-w-5xl">
          <header className="border-b border-border pb-5">
            <h1 className="text-xl font-semibold">{requestedTraceId ? 'Decision review' : 'Your institutional information'}</h1>
          </header>
          {!requestedTraceId && <div className="flex flex-col gap-10 py-6"><SubjectInstitutionalTimeline /><PublicPolicyGuide /></div>}
          {requestedTraceId && graphLoading && <p className="py-8 text-sm text-muted">Loading your decision...</p>}
          {requestedTraceId && graphError && <div role="alert" className="mt-6 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-700">{graphError}</div>}
          {requestedTraceId && !graphLoading && !graphError && !graph && <p className="py-8 text-sm text-muted">No decision was selected.</p>}
          {requestedTraceId && !graphLoading && graph && <div className="flex flex-col gap-10"><SubjectPositionView graph={graph} /><SubjectInstitutionalTimeline /></div>}
        </div>
      </main>
    );
  }

  const allowedViews = capabilities.allowed_views.filter(isActiveView);
  const activeView = allowedViews.includes(selectedView) ? selectedView : allowedViews[0];
  const allowedNavigation = navigationItems.filter((item) => allowedViews.includes(item.view));
  const isTenantAdmin = capabilities.role === 'tenant_admin';
  const canApplyQuickEdit = isTenantAdmin || capabilities.role === 'metadata_steward';
  const canManageHandbook = isTenantAdmin || capabilities.role === 'rule_author';
  const canManageAssistance = isTenantAdmin || capabilities.role === 'assistance_coordinator';
  const canPublishPolicy = isTenantAdmin || capabilities.role === 'rule_approver';
  const canRecordAmbiguity = isTenantAdmin || capabilities.role === 'rule_author' || capabilities.role === 'policy_owner';
  const canResolveAmbiguity = isTenantAdmin || capabilities.role === 'policy_owner';
  const canCreateCalibration = isTenantAdmin || capabilities.role === 'rule_author';
  const canCertifyCalibration = isTenantAdmin || capabilities.role === 'rule_approver' || capabilities.role === 'policy_owner';
  const canResolveCalibrationMismatch = isTenantAdmin || capabilities.role === 'rule_approver' || capabilities.role === 'policy_owner';
  const canRecordInstitutionalContext = isTenantAdmin || capabilities.role === 'institutional_records_steward';
  const canAttestInstitutionalContext = isTenantAdmin || capabilities.role === 'policy_owner';
  const canProposeEvidenceFact = isTenantAdmin || capabilities.role === 'institutional_records_steward';
  const canAttestEvidenceFact = isTenantAdmin || capabilities.role === 'policy_owner';

  if (!activeView) {
    return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><div role="alert" className="mx-auto max-w-5xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">This account does not have access to an operational workspace.</div></main>;
  }

  return (
    <div className="flex h-screen bg-white">
      <aside className="flex w-64 flex-col border-r border-border">
        <div className="border-b border-border p-6">
          <h1 className="text-lg font-semibold tracking-normal">Knowledge Studio</h1>
          <p className="mt-1 text-xs text-muted">{capabilities.role_label}</p>
        </div>
        <nav aria-label="Institution workspace" className="flex-1 space-y-1 p-4">
          {allowedNavigation.map(({ view, label, icon: Icon }) => (
            <button
              key={view}
              type="button"
              onClick={() => setSelectedView(view)}
              className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${activeView === view ? 'bg-accent' : 'text-muted hover:bg-accent'}`}
            >
              <Icon className="h-4 w-4 text-muted" />
              {label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="flex h-16 items-center border-b border-border px-8">
          <div className="flex items-center gap-2 text-sm text-muted">
            <span>{viewHeading[activeView][0]}</span>
            <span>/</span>
            <span className="font-medium text-primary">{viewHeading[activeView][1]}</span>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto p-8">
          {activeView === 'governance' && <GovernanceDesk canApplyQuickEdit={canApplyQuickEdit} />}
          {activeView === 'institution_setup' && <InstitutionalIntake />}
          {activeView === 'assistance_inbox' && <AssistanceInbox canManage={canManageAssistance} />}
          {activeView === 'decision_review_inbox' && <DecisionReviewInbox canManage={canManageAssistance} />}
          {activeView === 'policy_review' && <PolicyReview canPublish={canPublishPolicy} />}
          {activeView === 'policy_ambiguities' && <PolicyAmbiguityRegister canRecord={canRecordAmbiguity} canResolve={canResolveAmbiguity} />}
          {activeView === 'handbook_intake' && <HandbookIntake canManageSource={canManageHandbook} />}
          {activeView === 'record_import' && <SystemRecordImport />}
          {activeView === 'shadow_calibration' && <ShadowCalibration canCreate={canCreateCalibration} canCertify={canCertifyCalibration} canResolveMismatch={canResolveCalibrationMismatch} />}
          {activeView === 'institutional_timeline' && <InstitutionalTimeline canRecord={canRecordInstitutionalContext} canAttest={canAttestInstitutionalContext} />}
          {activeView === 'evidence_facts' && <EvidenceFactReview canPropose={canProposeEvidenceFact} canAttest={canAttestEvidenceFact} />}
        </div>
      </main>
    </div>
  );
}

export default App;
