import { lazy, Suspense, useEffect, useState, type ComponentType } from 'react';
import { useAuth } from "react-oidc-context";
import { isOidcConfigured } from './authConfig';
import { StaffWorkspaceHome } from './components/StaffWorkspaceHome';
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
  LayoutDashboard,
  ChevronDown,
  type LucideProps,
} from 'lucide-react';

const AssistanceInbox = lazy(async () => ({ default: (await import('./components/AssistanceInbox')).AssistanceInbox }));
const DecisionReviewInbox = lazy(async () => ({ default: (await import('./components/DecisionReviewInbox')).DecisionReviewInbox }));
const GovernanceDesk = lazy(async () => ({ default: (await import('./components/GovernanceDesk')).GovernanceDesk }));
const HandbookIntake = lazy(async () => ({ default: (await import('./components/HandbookIntake')).HandbookIntake }));
const InstitutionalIntake = lazy(async () => ({ default: (await import('./components/InstitutionalIntake')).InstitutionalIntake }));
const InstitutionalTimeline = lazy(async () => ({ default: (await import('./components/InstitutionalTimeline')).InstitutionalTimeline }));
const EvidenceFactReview = lazy(async () => ({ default: (await import('./components/EvidenceFactReview')).EvidenceFactReview }));
const PolicyAmbiguityRegister = lazy(async () => ({ default: (await import('./components/PolicyAmbiguityRegister')).PolicyAmbiguityRegister }));
const PolicyReview = lazy(async () => ({ default: (await import('./components/PolicyReview')).PolicyReview }));
const PublicPolicyGuide = lazy(async () => ({ default: (await import('./components/PublicPolicyGuide')).PublicPolicyGuide }));
const SubjectPositionView = lazy(async () => ({ default: (await import('./components/SubjectPositionView')).SubjectPositionView }));
const SubjectInformationView = lazy(async () => ({ default: (await import('./components/SubjectInformationView')).SubjectInformationView }));
const SubjectInstitutionalTimeline = lazy(async () => ({ default: (await import('./components/SubjectInstitutionalTimeline')).SubjectInstitutionalTimeline }));
const SubjectTransparencyDashboard = lazy(async () => ({ default: (await import('./components/SubjectTransparencyDashboard')).SubjectTransparencyDashboard }));
const ShadowCalibration = lazy(async () => ({ default: (await import('./components/ShadowCalibration')).ShadowCalibration }));
const SystemRecordImport = lazy(async () => ({ default: (await import('./components/SystemRecordImport')).SystemRecordImport }));

type ActiveView =
  | 'home'
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
  { view: 'home', label: 'Your work', icon: LayoutDashboard },
  { view: 'governance', label: 'Governance Desk', icon: ShieldCheck },
  { view: 'institution_setup', label: 'Institution Setup', icon: Building2 },
  { view: 'handbook_intake', label: 'Handbook Intake', icon: Files },
  { view: 'record_import', label: 'System Records', icon: TableProperties },
  { view: 'assistance_inbox', label: 'Assistance Inbox', icon: Inbox },
  { view: 'decision_review_inbox', label: 'Review Cases', icon: MessageSquareWarning },
  { view: 'policy_review', label: 'Policy Review', icon: ClipboardCheck },
  { view: 'policy_ambiguities', label: 'Policy Register', icon: Scale },
  { view: 'shadow_calibration', label: 'Outcome Calibration', icon: TestTube2 },
  { view: 'institutional_timeline', label: 'Institutional Timeline', icon: Landmark },
  { view: 'evidence_facts', label: 'Evidence Facts', icon: FileCheck2 },
];

const viewHeading: Record<ActiveView, [string, string]> = {
  home: ['Your work', 'Task queue'],
  governance: ['Governance Desk', 'Tier 1 Controls'],
  institution_setup: ['Institution Setup', 'Policy Draft'],
  assistance_inbox: ['Assistance Inbox', 'Human Follow-up'],
  decision_review_inbox: ['Decision Review', 'Casework'],
  policy_review: ['Policy Review', 'Release Approval'],
  policy_ambiguities: ['Policy Register', 'Interpretations'],
  handbook_intake: ['Handbook Intake', 'Source Verification'],
  record_import: ['System Records', 'Source Preview'],
  shadow_calibration: ['Outcome Calibration', 'Pre-production Comparison'],
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
  const auth = useAuth();
  const [capabilities, setCapabilities] = useState<SessionCapabilities | null>(null);
  const [capabilityLoading, setCapabilityLoading] = useState(true);
  const [capabilityError, setCapabilityError] = useState(false);
  const [selectedView, setSelectedView] = useState<ActiveView>('home');
  const [showSpecialistTools, setShowSpecialistTools] = useState(false);
  const [graph, setGraph] = useState<ReasoningGraph | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);

  const searchParameters = new URLSearchParams(window.location.search);
  const requestedSubjectExperience = searchParameters.get('experience') === 'subject';
  const requestedTraceId = searchParameters.get('trace');
  const requestedInformationId = searchParameters.get('information');

  useEffect(() => {
    if (!isOidcConfigured) return;
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
    if (!isOidcConfigured) return;
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

  if (!isOidcConfigured) {
    return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><div role="alert" className="mx-auto max-w-5xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">Institutional sign-in is not configured. Set the approved OIDC authority and client identifier before using this workspace.</div></main>;
  }

  if (auth.isLoading) {
    return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><p className="mx-auto max-w-5xl text-sm text-muted">Redirecting to institution login...</p></main>;
  }

  if (auth.error) {
    return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><div role="alert" className="mx-auto max-w-5xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">Authentication error: {auth.error.message}</div></main>;
  }

  if (!auth.isAuthenticated) {
    return (
      <main className="min-h-screen bg-white px-4 py-8 sm:px-8 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-semibold mb-4">Curriculum Reasoning Engine</h1>
          <p className="text-muted mb-8">Please sign in with your institutional account to continue.</p>
          <button
            onClick={() => void auth.signinRedirect()}
            className="bg-primary text-primary-foreground hover:bg-primary/90 px-4 py-2 rounded-md font-medium"
          >
            Sign in with Institution
          </button>
        </div>
      </main>
    );
  }

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
          <Suspense fallback={<p className="py-8 text-sm text-muted">Loading your information...</p>}>
            {!requestedTraceId && <div className="flex flex-col gap-10 py-6"><SubjectInformationView highlightInformationId={requestedInformationId} /><SubjectTransparencyDashboard /><SubjectInstitutionalTimeline /><PublicPolicyGuide /></div>}
            {requestedTraceId && graphLoading && <p className="py-8 text-sm text-muted">Loading your decision...</p>}
            {requestedTraceId && graphError && <div role="alert" className="mt-6 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-700">{graphError}</div>}
            {requestedTraceId && !graphLoading && !graphError && !graph && <p className="py-8 text-sm text-muted">No decision was selected.</p>}
            {requestedTraceId && !graphLoading && graph && <div className="flex flex-col gap-10"><SubjectPositionView graph={graph} /><SubjectInstitutionalTimeline /></div>}
          </Suspense>
        </div>
      </main>
    );
  }

  const allowedViews = ['home', ...capabilities.allowed_views.filter(isActiveView)] as ActiveView[];
  const activeView = allowedViews.includes(selectedView) ? selectedView : allowedViews[0];
  const specialistViews: ActiveView[] = ['institution_setup', 'handbook_intake', 'record_import', 'policy_review', 'policy_ambiguities', 'shadow_calibration', 'governance'];
  const specialistNavigation = navigationItems.filter((item) => allowedViews.includes(item.view) && specialistViews.includes(item.view));
  const isTenantAdmin = capabilities.role === 'tenant_admin';
  const canApplyQuickEdit = isTenantAdmin || capabilities.role === 'staff_member';
  const canManageHandbook = isTenantAdmin || capabilities.role === 'policy_editor';
  const canManageAssistance = isTenantAdmin || capabilities.role === 'staff_member';
  const canPublishPolicy = isTenantAdmin || capabilities.role === 'approver';
  const canRecordAmbiguity = isTenantAdmin || capabilities.role === 'policy_editor' || capabilities.role === 'approver';
  const canResolveAmbiguity = isTenantAdmin || capabilities.role === 'approver';
  const canCreateCalibration = isTenantAdmin || capabilities.role === 'policy_editor';
  const canCertifyCalibration = isTenantAdmin || capabilities.role === 'approver';
  const canResolveCalibrationMismatch = isTenantAdmin || capabilities.role === 'approver';
  const canRecordInstitutionalContext = isTenantAdmin || capabilities.role === 'staff_member';
  const canAttestInstitutionalContext = isTenantAdmin || capabilities.role === 'approver';
  const canProposeEvidenceFact = isTenantAdmin || capabilities.role === 'staff_member';
  const canAttestEvidenceFact = isTenantAdmin || capabilities.role === 'approver';

  if (!activeView) {
    return <main className="min-h-screen bg-white px-4 py-8 sm:px-8"><div role="alert" className="mx-auto max-w-5xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">This account does not have access to an operational workspace.</div></main>;
  }

  return (
    <div className="flex h-screen bg-white">
      <aside className="flex w-64 flex-col border-r border-border">
        <div className="border-b border-border p-6">
          <h1 className="text-lg font-semibold tracking-normal">Institutional Decisions</h1>
          <p className="mt-1 text-xs text-muted">{capabilities.role_label}</p>
        </div>
        <nav aria-label="Institution workspace" className="flex-1 space-y-1 p-4">
          <button type="button" onClick={() => setSelectedView('home')} className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${activeView === 'home' ? 'bg-accent' : 'text-muted hover:bg-accent'}`}>
            <LayoutDashboard className="h-4 w-4 text-muted" />Your work
          </button>
          {activeView !== 'home' && <button type="button" onClick={() => setSelectedView('home')} className="mt-3 w-full border-t border-border pt-4 text-left text-sm text-muted hover:text-foreground">Back to your work</button>}
          {specialistNavigation.length > 0 && <div className="mt-5 border-t border-border pt-4">
            <button type="button" onClick={() => setShowSpecialistTools((current) => !current)} aria-expanded={showSpecialistTools} className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-semibold uppercase tracking-normal text-muted hover:bg-accent">
              Onboarding and assurance <ChevronDown className={`h-4 w-4 transition-transform ${showSpecialistTools ? 'rotate-180' : ''}`} />
            </button>
            {showSpecialistTools && <div className="mt-1 space-y-1">{specialistNavigation.map(({ view, label, icon: Icon }) => (
            <button
              key={view}
              type="button"
              onClick={() => setSelectedView(view)}
              className={`flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium transition-colors ${activeView === view ? 'bg-accent' : 'text-muted hover:bg-accent'}`}
            >
              <Icon className="h-4 w-4 text-muted" />
              {label}
            </button>
            ))}</div>}
          </div>}
        </nav>
          <div className="border-t border-border p-4">
            <button
              type="button"
              onClick={() => void auth.signoutRedirect()}
              className="flex w-full items-center gap-3 rounded px-3 py-2 text-left text-sm font-medium text-muted hover:bg-accent transition-colors"
            >
              Sign out
            </button>
          </div>
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
          <Suspense fallback={<p className="mx-auto max-w-4xl py-8 text-sm text-muted">Opening your workspace...</p>}>
          {activeView === 'home' && <StaffWorkspaceHome role={capabilities.role} allowedViews={allowedViews.filter((view) => view !== 'home')} onOpen={setSelectedView} />}
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
          </Suspense>
        </div>
      </main>
    </div>
  );
}

export default App;
