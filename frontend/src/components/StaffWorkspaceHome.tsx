import { ArrowRight, ClipboardCheck, FileCheck2, Files, Inbox, Landmark, Scale, TableProperties, TestTube2 } from 'lucide-react';

type WorkspaceView =
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

type Task = { view: WorkspaceView; label: string; description: string; icon: typeof Inbox };

const tasksByRole: Record<string, Task[]> = {
  staff_member: [
    { view: 'assistance_inbox', label: 'Assistance Inbox', description: 'Work through requests that need a human response.', icon: Inbox },
    { view: 'decision_review_inbox', label: 'Review Cases', description: 'Check records, provide a response, or route a case onward.', icon: ClipboardCheck },
    { view: 'evidence_facts', label: 'Evidence Facts', description: 'Record or inspect cited information that needs human review.', icon: FileCheck2 },
    { view: 'institutional_timeline', label: 'Institutional Timeline', description: 'Preserve a concession, appeal, or other decision that explains a person\'s position.', icon: Landmark },
  ],
  policy_editor: [
    { view: 'institution_setup', label: 'Institution Setup', description: 'Prepare a policy update in guided fields and submit it for review.', icon: ClipboardCheck },
    { view: 'handbook_intake', label: 'Handbook Intake', description: 'Review source material before drafting a policy update.', icon: Files },
    { view: 'record_import', label: 'System Records', description: 'Set up the approved information used in a decision.', icon: TableProperties },
    { view: 'policy_ambiguities', label: 'Policy Register', description: 'Record an interpretation question instead of making an unstated assumption.', icon: Scale },
    { view: 'shadow_calibration', label: 'Outcome Calibration', description: 'Compare a proposed policy against non-identifying historic cases.', icon: TestTube2 },
  ],
  approver: [
    { view: 'policy_review', label: 'Approve a policy update', description: 'Review a proposed change, its evidence, and when it will apply.', icon: ClipboardCheck },
    { view: 'evidence_facts', label: 'Review evidence', description: 'Accept or return information that cannot safely be accepted automatically.', icon: FileCheck2 },
    { view: 'policy_ambiguities', label: 'Resolve an interpretation', description: 'Record the authorised reading and its source.', icon: Scale },
    { view: 'institutional_timeline', label: 'Certify institutional context', description: 'Confirm a recorded concession, appeal, or committee decision.', icon: Landmark },
  ],
  auditor: [
    { view: 'governance', label: 'Inspect governance history', description: 'Review published controls and low-risk change history.', icon: ClipboardCheck },
    { view: 'policy_review', label: 'Inspect policy releases', description: 'Review published policy material without changing it.', icon: Files },
    { view: 'evidence_facts', label: 'Inspect evidence history', description: 'Review how facts were accepted without changing them.', icon: FileCheck2 },
  ],
  tenant_admin: [
    { view: 'governance', label: 'Governance Desk', description: 'Inspect governance status and correct low-risk display information.', icon: ClipboardCheck },
    { view: 'policy_review', label: 'Policy Review', description: 'Use only when designated approvers cannot act; every action remains auditable.', icon: Files },
    { view: 'record_import', label: 'System Records', description: 'Review approved sources, mappings, and import health.', icon: TableProperties },
    { view: 'shadow_calibration', label: 'Outcome Calibration', description: 'Check a proposed policy against non-identifying historic cases.', icon: TestTube2 },
    { view: 'institutional_timeline', label: 'Institutional Timeline', description: 'Inspect institutional context that explains an individual position.', icon: Landmark },
    { view: 'evidence_facts', label: 'Evidence Facts', description: 'Inspect how evidence was accepted into a decision.', icon: FileCheck2 },
  ],
};

const fallbackTasks: Record<WorkspaceView, Omit<Task, 'view'>> = {
  governance: { label: 'Governance Desk', description: 'Review the assigned governance work.', icon: ClipboardCheck },
  institution_setup: { label: 'Institution Setup', description: 'Prepare an assigned policy update.', icon: ClipboardCheck },
  assistance_inbox: { label: 'Assistance Inbox', description: 'Work through assigned human requests.', icon: Inbox },
  decision_review_inbox: { label: 'Review Cases', description: 'Work through assigned review cases.', icon: ClipboardCheck },
  policy_review: { label: 'Policy Review', description: 'Review an assigned policy release.', icon: Files },
  policy_ambiguities: { label: 'Policy Register', description: 'Review an assigned interpretation.', icon: Scale },
  handbook_intake: { label: 'Handbook Intake', description: 'Review assigned source material.', icon: Files },
  record_import: { label: 'System Records', description: 'Review the information used in a decision.', icon: TableProperties },
  shadow_calibration: { label: 'Outcome Calibration', description: 'Review an assigned comparison.', icon: TestTube2 },
  institutional_timeline: { label: 'Institutional Timeline', description: 'Review institutional context history.', icon: Landmark },
  evidence_facts: { label: 'Evidence Facts', description: 'Review cited decision information.', icon: FileCheck2 },
};

export function StaffWorkspaceHome({ role, allowedViews, onOpen }: { role: string; allowedViews: WorkspaceView[]; onOpen: (view: WorkspaceView) => void }) {
  const assigned = (tasksByRole[role] || []).filter((task) => allowedViews.includes(task.view));
  const tasks = [...assigned, ...allowedViews.filter((view) => !assigned.some((task) => task.view === view)).map((view) => ({ view, ...fallbackTasks[view] }))];
  return <div className="mx-auto flex w-full max-w-4xl flex-col gap-7 py-4">
    <section className="border-b border-border pb-5"><h2 className="text-2xl font-semibold">Your work</h2><p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">Choose the task you need to complete. Your access is an assignment to a specific institutional function, not a statement of seniority or ownership of every decision. The service keeps policy and audit controls in the background.</p></section>
    {tasks.length === 0 ? <p className="border-l-2 border-border pl-4 text-sm leading-relaxed text-muted">There are no tasks assigned to this account. Contact your institution if you expected access to a particular area.</p> : <section aria-label="Available tasks" className="divide-y divide-border border-y border-border">{tasks.map(({ view, label, description, icon: Icon }) => <button key={view} type="button" onClick={() => onOpen(view)} className="grid w-full grid-cols-[24px_minmax(0,1fr)_20px] gap-4 px-1 py-5 text-left hover:bg-accent"><Icon aria-hidden="true" className="mt-0.5 h-5 w-5 text-muted" /><span><span className="block font-semibold">{label}</span><span className="mt-1 block text-sm leading-relaxed text-muted">{description}</span></span><ArrowRight aria-hidden="true" className="mt-1 h-4 w-4 text-muted" /></button>)}</section>}
  </div>;
}
