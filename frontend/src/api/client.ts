import axios from 'axios';

// Defaults to localhost for dev, can be configured via Vite env vars
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

function apiProblemMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) return 'Something unexpected happened. Your changes were not submitted.';
  if (!error.response) return 'We could not reach the institutional service. Check your connection and try again. Your changes were not submitted.';
  if (error.response.status === 401) return 'Your session has ended. Sign in again and retry your request.';
  if (error.response.status === 403) return 'Your account is not permitted to do that. Contact your institution if this seems incorrect.';
  if (error.response.status === 404) return 'That record is no longer available. Refresh the page and try again.';
  if (error.response.status === 409) return 'This record changed while you were working. Refresh it before trying again.';
  const detail = error.response.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: unknown } | undefined;
    if (typeof first?.msg === 'string') return first.msg;
  }
  if (error.response.status >= 500) return 'The institutional service could not complete that request. Try again shortly; your changes were not submitted.';
  return 'We could not complete that request. Check the information and try again.';
}

// Helper to get the OIDC token from session storage
const getOidcToken = () => {
  const providerSurface = import.meta.env.VITE_APP_SURFACE === 'provider';
  const authority = providerSurface ? import.meta.env.VITE_PROVIDER_OIDC_AUTHORITY : import.meta.env.VITE_OIDC_AUTHORITY;
  const clientId = providerSurface ? import.meta.env.VITE_PROVIDER_OIDC_CLIENT_ID : import.meta.env.VITE_OIDC_CLIENT_ID;
  const oidcStorageKey = `oidc.user:${authority || "https://your-tenant.auth0.com"}:${clientId || "your-client-id"}`;
  const oidcStorage = sessionStorage.getItem(oidcStorageKey);
  if (!oidcStorage) return null;
  try {
    const user = JSON.parse(oidcStorage);
    return user?.access_token || null;
  } catch {
    return null;
  }
};

apiClient.interceptors.request.use((config) => {
  const token = getOidcToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (error && typeof error === 'object') {
      (error as { message?: string }).message = apiProblemMessage(error);
    }
    return Promise.reject(error);
  },
);

// --- Types ---
export interface EvaluationSummary {
    decision: "ELIGIBLE" | "INELIGIBLE" | "NEEDS_MANUAL_REVIEW";
    overall_confidence: number;
    reasoning_graph_id: string;
    release_version: string;
}

export interface GraphNode {
    id: string;
    type: "fact" | "rule_evaluation" | "conclusion";
    label: string;
    data: any;
    computed_confidence: number;
}

export interface GraphEdge {
    source_id: string;
    target_id: string;
    relation: string;
    weight: number;
}

export interface ReasoningGraph {
    id: string;
    subject_id: string;
    rule_graph_id: string;
    nodes: Record<string, GraphNode>;
    edges: GraphEdge[];
    explanation?: string;
    evaluation_context?: {
        domain_id: string;
        release_version: string;
        source_authority?: 'official_system' | 'institutional_working_record' | 'subject_submitted';
        record_state?: 'confirmed' | 'provisional';
        source_system?: string | null;
        source_as_of?: string | null;
    };
}

export interface SubjectCurrentPosition {
    trace_id: string;
    domain_id: string;
    domain_name: string;
    position_type: 'curriculum' | 'assessment_eligibility' | 'eligibility' | 'institutional_standing' | 'other';
    position_label: string;
    governed_person_label?: string;
    position_collection_label?: string;
    decision: 'ELIGIBLE' | 'INELIGIBLE' | 'NEEDS_MANUAL_REVIEW';
    release_version: string;
    evaluated_at: string | null;
    source_authority: 'official_system' | 'institutional_working_record' | 'subject_submitted';
    record_state: 'confirmed' | 'provisional';
    source_system: string | null;
    source_as_of: string | null;
    source_expected_by?: string | null;
    source_is_stale?: boolean;
    responsible_group?: string | null;
    fallback_group?: string | null;
    provisional_escalation_by?: string | null;
}

export interface ProviderTenantControl {
    tenant_id: string;
    tenant_name: string;
    lifecycle_state: 'PILOT' | 'ACTIVE' | 'SUSPENDED' | 'DECOMMISSIONED';
    service_tier: string;
    integration_status: string;
    integration_observed_at?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
}

export interface SessionCapabilities {
    experience: 'staff' | 'subject';
    role: string;
    role_label: string;
    allowed_views: string[];
}

export interface QuickEditPayload {
    domain_id: string;
    target_type: string;
    target_id: string;
    field: string;
    old_value?: string;
    new_value: string;
    reason: string;
    source_reference?: string;
}

export interface MetadataFieldPolicy {
    name: string;
    label: string;
    risk: "low";
    notes: string;
}

export interface MetadataTargetPolicy {
    target_type: string;
    label: string;
    identifier_label: string;
    fields: MetadataFieldPolicy[];
}

export interface RolePermission {
    role: string;
    label: string;
    can_quick_edit: boolean;
    can_author_structured_drafts: boolean;
    can_approve_releases: boolean;
    can_replay_audits: boolean;
    can_manage_assistance_requests: boolean;
    can_manage_decision_reviews: boolean;
    can_resolve_policy_ambiguities: boolean;
    scope: string;
}

export interface GovernancePermissions {
    current_role: string;
    domain_id: string;
    metadata_quick_edits: MetadataTargetPolicy[];
    review_required_changes: string[];
    formal_governance_changes: string[];
    matrix: RolePermission[];
}

export interface QuickEditResponse extends QuickEditPayload {
    change_id: string;
    status: "applied";
    applied_by: string;
    field_policy: {
        label: string;
        risk: string;
        notes: string;
    };
}

export type InstitutionalFactDataType = 'text' | 'number' | 'yes_no';
export type InstitutionalRuleOperator =
    | 'equals'
    | 'does_not_equal'
    | 'at_least'
    | 'at_most'
    | 'greater_than'
    | 'less_than'
    | 'contains';

export interface InstitutionalFactInput {
    id: string;
    label: string;
    data_type: InstitutionalFactDataType;
}

export interface InstitutionalRuleInput {
    id: string;
    label: string;
    fact_id: string;
    operator: InstitutionalRuleOperator;
    value: string | number | boolean;
    source_citation: string;
}

export type InstitutionalRootOperator = 'all' | 'any';
export type InstitutionalRuleGroupOperator = 'all' | 'any' | 'not';

export interface InstitutionalRuleGroupInput {
    id: string;
    label: string;
    operator: InstitutionalRuleGroupOperator;
    children: string[];
}

export interface InstitutionalIntakePayload {
    institution_name: string;
    domain_name: string;
    governed_person_label?: string;
    position_collection_label?: string;
    subject_position_type?: 'curriculum' | 'assessment_eligibility' | 'eligibility' | 'institutional_standing' | 'other';
    subject_position_label?: string;
    automation_mode?: 'automatic' | 'human_confirmation_required';
    policy_name?: string;
    public_policy_guide: boolean;
    assistance_requests_enabled: boolean;
    support_response_target_hours: number;
    decision_review_enabled: boolean;
    decision_review_response_target_hours?: number;
    support_privacy_notice_url?: string;
    offline_assistance_instructions?: string;
    casework_primary_group?: string;
    casework_fallback_group?: string;
    casework_escalation_after_hours?: number;
    facts: InstitutionalFactInput[];
    rules: InstitutionalRuleInput[];
    root_operator?: InstitutionalRootOperator;
    rule_groups?: InstitutionalRuleGroupInput[];
    root_group_id?: string;
}

export interface InstitutionalIntakeResponse {
    tenant_id: string;
    domain_id: string;
    domain_name: string;
    draft_id: string;
    policy_name: string;
    status: 'PENDING_REVIEW';
    fact_count: number;
    rule_count: number;
    next_step: string;
}

export interface PublicPolicyGuideListItem {
    domain_id: string;
    domain_name: string;
    version: string;
}

export interface PublicPolicyGroup {
    kind: 'group';
    label: string;
    mode: 'all' | 'any' | 'not' | 'group';
    children: PublicPolicyNode[];
}

export interface PublicPolicyRule {
    kind: 'rule';
    label: string;
    fact_label: string;
    operator: string;
    expected_value: string | number | boolean | null;
    citation?: string | null;
}

export type PublicPolicyNode = PublicPolicyGroup | PublicPolicyRule;

export interface PublicPolicyGuide {
    domain_id: string;
    domain_name: string;
    version: string;
    governed_person_label?: string;
    position_collection_label?: string;
    policy: PublicPolicyNode;
    assistance_requests_enabled: boolean;
    support_response_target_hours?: number | null;
    support_privacy_notice_url?: string | null;
    offline_assistance_instructions?: string | null;
}

export interface PublicSupportRequestPayload {
    category: 'missing_information' | 'unique_circumstance' | 'accessibility' | 'other';
    contact_details?: string;
    message: string;
}

export interface AdminDomain {
    domain_id: string;
    domain_name: string;
}

export interface RecordImportField {
    target_path: string;
    label: string;
    schema_type: 'string' | 'number' | 'boolean';
}

export interface EvidenceSourceSummary {
    evidence_id: string;
    source_type: string;
    captured_at?: string | null;
    integrity_hash: string;
}

export type EvidenceFactProposalStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED';

export interface EvidenceFactProposal {
    proposal_id: string;
    domain_id: string;
    evidence_id: string;
    subject_id: string;
    target_path: string;
    asserted_value: string | number | boolean;
    source_quote: string;
    source_locator?: string | null;
    proposal_origin: string;
    evidence_sha256: string;
    input_sha256: string;
    status: EvidenceFactProposalStatus;
    proposed_by: string;
    reviewed_by?: string | null;
    review_note?: string | null;
    reviewed_at?: string | null;
    created_at?: string | null;
}

export interface EvidenceFactProposalInput {
    domain_id: string;
    evidence_id: string;
    target_path: string;
    asserted_value: string | number | boolean;
    source_quote: string;
    source_locator?: string;
}

export type InstitutionalContextEventType =
    | 'CONCESSION'
    | 'CURRICULUM_APPLICABILITY'
    | 'ASSESSMENT_ACCOMMODATION'
    | 'APPEAL_OUTCOME'
    | 'REGISTRATION_POSITION'
    | 'PROGRESSION_POSITION'
    | 'GRADUATION_POSITION'
    | 'OTHER';
export type InstitutionalContextVisibility = 'SUBJECT' | 'STAFF_ONLY';
export type InstitutionalContextStatus = 'SUBMITTED' | 'CERTIFIED' | 'REJECTED';
export type InstitutionalContextTimelineState = InstitutionalContextStatus | 'ACTIVE' | 'SUPERSEDED' | 'REVOKED' | 'EXPIRED';

export interface InstitutionalContextEventInput {
    domain_id: string;
    subject_id: string;
    event_type: InstitutionalContextEventType;
    title: string;
    student_summary: string;
    institutional_effect: string;
    authority_name: string;
    authority_reference: string;
    source_reference: string;
    event_date: string;
    effective_from: string;
    effective_until?: string;
    visibility: InstitutionalContextVisibility;
    policy_release_id?: string;
    policy_citation?: string;
    predecessor_event_id?: string;
    predecessor_relationship?: 'SUPERSEDES' | 'REVOKES';
}

export interface InstitutionalContextEvent {
    event_id: string;
    domain_id: string;
    subject_id?: string;
    event_type: InstitutionalContextEventType;
    title: string;
    student_summary: string;
    institutional_effect: string;
    authority_name: string;
    authority_reference?: string;
    source_reference?: string;
    event_date: string;
    effective_from: string;
    effective_until?: string | null;
    visibility: InstitutionalContextVisibility;
    policy_release_id?: string | null;
    policy_release_version?: string | null;
    policy_citation?: string | null;
    predecessor_event_id?: string | null;
    predecessor_relationship?: 'SUPERSEDES' | 'REVOKES' | null;
    status: InstitutionalContextStatus;
    timeline_state: InstitutionalContextTimelineState;
    input_sha256?: string;
    recorded_by?: string;
    attested_by?: string | null;
    attestation_note?: string | null;
    attested_at?: string | null;
    created_at?: string | null;
}

export type CalibrationDecision = 'ELIGIBLE' | 'INELIGIBLE' | 'NEEDS_MANUAL_REVIEW';
export type CalibrationDataBasis = 'SYNTHETIC' | 'APPROVED_DEIDENTIFIED';
export type CalibrationSuiteStatus = 'SUBMITTED' | 'CERTIFIED' | 'COMPLETED';
export type CalibrationFindingClassification = 'SOURCE_DATA' | 'POLICY_MODEL' | 'EVIDENCE' | 'GOVERNANCE';

export interface CalibrationRelease {
    release_id: string;
    version: string;
    effective_from?: string | null;
    effective_until?: string | null;
    calibration_ready: boolean;
    calibration_blocker?: string | null;
}

export interface ShadowCalibrationFactInput {
    target_path: string;
    value: string | number | boolean;
    status?: 'resolved' | 'needs_human_review';
}

export interface ShadowCalibrationCaseInput {
    case_reference: string;
    description: string;
    recorded_decision: CalibrationDecision;
    recorded_outcome_reference: string;
    facts: ShadowCalibrationFactInput[];
}

export interface ShadowCalibrationSuiteInput {
    domain_id: string;
    release_id: string;
    name: string;
    description: string;
    data_basis: CalibrationDataBasis;
    privacy_approval_reference?: string;
    policy_as_of_date: string;
    cases: ShadowCalibrationCaseInput[];
}

export interface ShadowCalibrationSuiteSummary {
    suite_id: string;
    domain_id: string;
    release_id: string;
    release_version: string;
    name: string;
    description: string;
    data_basis: CalibrationDataBasis;
    privacy_approval_reference?: string | null;
    policy_as_of_date: string;
    author_id: string;
    status: CalibrationSuiteStatus;
    input_sha256: string;
    certified_by?: string | null;
    certification_note?: string | null;
    certified_at?: string | null;
    completed_at?: string | null;
    case_count: number;
    created_at?: string | null;
}

export interface ShadowCalibrationCase {
    case_id: string;
    case_reference: string;
    description: string;
    recorded_decision: CalibrationDecision;
    recorded_outcome_reference: string;
    facts: ShadowCalibrationFactInput[];
}

export interface ShadowCalibrationRun {
    run_id: string;
    report: {
        all_cases_passed: boolean;
        policy_sha256: string;
        cases: Array<{
            id: string;
            expected_decision: CalibrationDecision;
            actual_decision: CalibrationDecision;
            passed: boolean;
            input_sha256: string;
            trace_sha256: string;
            evaluated_rules: number;
        }>;
    };
    report_sha256: string;
    executed_by: string;
    created_at?: string | null;
}

export interface ShadowCalibrationFinding {
    finding_id: string;
    case_id: string;
    case_reference: string;
    expected_decision: CalibrationDecision;
    actual_decision: CalibrationDecision;
    input_sha256: string;
    trace_sha256: string;
    status: 'OPEN' | 'RESOLVED';
    classification?: CalibrationFindingClassification | null;
    resolution_note?: string | null;
    resolved_by?: string | null;
    resolved_at?: string | null;
}

export interface ShadowCalibrationSuite extends ShadowCalibrationSuiteSummary {
    cases: ShadowCalibrationCase[];
    events: Array<{ event_type: string; actor_id: string; note?: string | null; created_at?: string | null }>;
    run?: ShadowCalibrationRun | null;
    findings: ShadowCalibrationFinding[];
}

export interface SystemRecordImportFieldMapping {
    source_column: string;
    target_path: string;
    value_type: 'text' | 'integer' | 'number' | 'boolean' | 'date';
    required: boolean;
}

export interface SystemRecordImportContract {
    mapping_id: string;
    source_id?: string;
    source_system: string;
    subject_identifier_column: string;
    source_record_version_column: string;
    source_as_of_date_column?: string;
    record_state?: 'confirmed' | 'provisional';
    fields: SystemRecordImportFieldMapping[];
}

export interface InstitutionalDataSource {
    source_id: string;
    domain_id: string;
    display_name: string;
    source_kind: 'SYSTEM_OF_RECORD' | 'LEARNING_PLATFORM' | 'DEPARTMENT_RECORD' | 'COMMITTEE_REGISTER' | 'MANUAL';
    authority_level: 'AUTHORITATIVE' | 'WORKING' | 'REFERENCE';
    source_owner: string;
    expected_refresh_hours?: number | null;
    source_reference?: string | null;
    connector_kind?: 'NONE' | 'REST_API' | 'SFTP_PULL' | 'DATABASE_VIEW' | 'VENDOR_API';
    credential_reference?: string | null;
    endpoint_reference?: string | null;
    allowed_object?: string | null;
    connector_status?: 'NOT_CONFIGURED' | 'CONFIGURED' | 'TEST_FAILED' | 'APPROVED' | 'PAUSED' | 'RETIRED';
    connector_last_checked_at?: string | null;
    status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'RETIRED';
    author_id: string;
    reviewed_by?: string | null;
    review_note?: string | null;
}

export interface SystemRecordImportPreview {
    contract_sha256: string;
    source_sha256: string;
    source_system: string;
    mapping_id: string;
    row_count: number;
    accepted_record_count: number;
    rejected_row_count: number;
    ignored_columns: string[];
    issues: Array<{ row_number?: number | null; code: string; message: string }>;
}

export type SystemRecordImportMappingStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface SystemRecordImportMapping {
    mapping_id: string;
    domain_id: string;
    mapping_name: string;
    source_system: string;
    contract: SystemRecordImportContract;
    contract_sha256: string;
    status: SystemRecordImportMappingStatus;
    author_id: string;
    reviewed_by?: string | null;
    reviewed_at?: string | null;
    review_note?: string | null;
    created_at?: string | null;
}

export interface SystemRecordImportMappingList {
    items: SystemRecordImportMapping[];
    can_submit: boolean;
    can_review: boolean;
    can_materialize?: boolean;
}

export interface SystemRecordMaterializationResult {
    mapping_id: string;
    source_system: string;
    record_state: 'confirmed' | 'provisional';
    accepted_record_count: number;
    evidence_created: number;
    already_imported: number;
    fact_acceptance: string;
}

export type SupportRequestStatus = 'OPEN' | 'IN_PROGRESS' | 'CLOSED';

export interface SupportRequest {
    id: string;
    domain_id: string;
    category: 'missing_information' | 'unique_circumstance' | 'accessibility' | 'other';
    contact_details?: string | null;
    message: string;
    status: SupportRequestStatus;
    response_due_at?: string | null;
    responsible_group?: string | null;
    fallback_group?: string | null;
    escalation_due_at?: string | null;
    is_escalated?: boolean;
    closed_at?: string | null;
    retention_expires_at?: string | null;
    is_overdue?: boolean;
    created_at?: string | null;
}

export type DecisionReviewStatus = 'SUBMITTED' | 'ACKNOWLEDGED' | 'UNDER_REVIEW' | 'RESOLVED' | 'CLOSED';
export type DecisionReviewResolution =
    | 'DECISION_CONFIRMED'
    | 'RE_EVALUATION_REQUIRED'
    | 'POLICY_CLARIFICATION_PROVIDED'
    | 'EXCEPTION_REFERRED'
    | 'OUT_OF_SCOPE';

export interface DecisionReviewCase {
    id: string;
    domain_id: string;
    subject_id: string;
    reasoning_graph_id: string;
    category: 'evidence_correction' | 'missing_evidence' | 'policy_interpretation' | 'exceptional_circumstance' | 'explanation_accessibility';
    message: string;
    disputed_fact_paths: string[];
    submitted_evidence_ids: string[];
    status: DecisionReviewStatus;
    resolution?: DecisionReviewResolution | null;
    response_message?: string | null;
    response_due_at?: string | null;
    responsible_group?: string | null;
    fallback_group?: string | null;
    escalation_due_at?: string | null;
    is_escalated?: boolean;
    resolved_at?: string | null;
    closed_at?: string | null;
    retention_expires_at?: string | null;
    is_overdue?: boolean;
    created_at?: string | null;
    updated_at?: string | null;
}

export interface DecisionReviewSubmissionPayload {
    domain_id: string;
    reasoning_graph_id: string;
    category: DecisionReviewCase['category'];
    message: string;
    disputed_fact_paths?: string[];
}

export interface PendingPolicyReview {
    draft_id: string;
    domain_id: string;
    domain_name: string;
    policy_name: string;
    author_id: string;
    created_at?: string | null;
}

export interface PolicyReview extends PendingPolicyReview {
    policy: PublicPolicyNode;
}

export interface ReleasePublication {
    release_id: string;
    domain_id: string;
    version: string;
    rule_graph_id: string;
    effective_from: string;
    effective_until?: string | null;
    applicability: Record<string, string[]>;
    approved_by: string;
    authored_by: string;
}

export interface PolicyAmbiguity {
    ambiguity_id: string;
    domain_id: string;
    source_citation: string;
    question: string;
    interpretation_options: string[];
    status: 'OPEN' | 'RESOLVED';
    resolution?: string | null;
    resolution_source_reference?: string | null;
    resolved_by?: string | null;
    resolved_at?: string | null;
    created_by: string;
    created_at?: string | null;
}

export type HandbookStatus = 'QUEUED' | 'EXTRACTING' | 'READY_FOR_REVIEW' | 'NEEDS_MANUAL_REVIEW' | 'OCR_QUEUED' | 'OCR_EXTRACTING' | 'OCR_REVIEW_REQUIRED' | 'FAILED';

export interface HandbookUpload {
    handbook_id: string;
    domain_id: string;
    file_name: string;
    file_size_bytes: number;
    content_hash?: string | null;
    status: HandbookStatus;
    total_pages?: number | null;
    processed_pages: number;
    error_message?: string | null;
    created_at?: string | null;
    updated_at?: string | null;
    next_step?: string;
}

export interface HandbookPageExcerpt {
    page_number: number;
    text_content: string;
    content_hash: string;
    extraction_kind?: string;
    review_priority?: 'NORMAL' | 'HIGH';
}

export interface HandbookSourceReview {
    handbook_id: string;
    file_name: string;
    status: HandbookStatus;
    items: HandbookPageExcerpt[];
    next_page_after?: number | null;
}

export type OCRReviewStatus = 'PENDING_REVIEW' | 'ACCEPTED' | 'CORRECTED' | 'REJECTED';

export interface HandbookOCRReview {
    ocr_review_id: string;
    page_number: number;
    provider_name: string;
    provider_reference?: string | null;
    provider_model_version?: string | null;
    provider_response_hash?: string | null;
    source_page_hash?: string;
    proposed_text: string;
    proposed_text_hash: string;
    proposed_blocks?: Array<{
        text: string;
        block_type: string;
        reading_order: number;
        bounding_box?: { x0: number; y0: number; x1: number; y1: number } | null;
        table_cells?: string[][] | null;
    }> | null;
    quality_signals?: {
        confidence?: number | null;
        language?: string | null;
        contains_table?: boolean;
        handwritten?: boolean;
        low_quality_scan?: boolean;
        continuation_from_previous_page?: boolean;
    } | null;
    review_priority?: 'NORMAL' | 'HIGH';
    status: OCRReviewStatus;
    reviewed_text?: string | null;
    reviewed_by?: string | null;
    reviewed_at?: string | null;
}

interface HandbookUploadSession {
    session_id: string;
    upload_url: string;
    upload_fields: Record<string, string>;
    expires_at: string;
}

// --- API Methods ---
export const fetchSessionCapabilities = async (): Promise<SessionCapabilities> => {
    const response = await apiClient.get<SessionCapabilities>('/session/capabilities');
    return response.data;
}

export const evaluateEvidence = async (
    evidenceId: string,
    ruleGraphId: string,
    subjectId: string,
    domainId: string,
    releaseVersion: string,
): Promise<EvaluationSummary> => {
    // Requires Idempotency-Key.
    const idempotencyKey = `ui-${Date.now()}`;
    const response = await apiClient.post<EvaluationSummary>('/evaluate', {
        rule_graph_id: ruleGraphId,
        evidence_id: evidenceId,
        subject_id: subjectId,
        domain_id: domainId,
        release_version: releaseVersion,
    }, {
        headers: {
            'Idempotency-Key': idempotencyKey
        }
    });
    return response.data;
}

export const fetchReasoningGraph = async (graphId: string): Promise<ReasoningGraph> => {
    const response = await apiClient.get<ReasoningGraph>(`/reasoning/${graphId}`);
    return response.data;
}

export const fetchSubjectCurrentPositions = async (): Promise<SubjectCurrentPosition[]> => {
    const response = await apiClient.get<{ items: SubjectCurrentPosition[] }>('/subject/current-positions');
    return response.data.items;
}

export const fetchProviderSession = async (): Promise<{ experience: 'provider'; role: string }> => {
    const response = await apiClient.get<{ experience: 'provider'; role: string }>('/provider/session');
    return response.data;
}

export const fetchProviderTenants = async (): Promise<ProviderTenantControl[]> => {
    const response = await apiClient.get<{ items: ProviderTenantControl[] }>('/provider/tenants');
    return response.data.items;
}

export const submitQuickEdit = async (payload: QuickEditPayload): Promise<QuickEditResponse> => {
    const response = await apiClient.post<QuickEditResponse>('/admin/quick-edits', payload);
    return response.data;
}

export const fetchGovernancePermissions = async (domainId: string): Promise<GovernancePermissions> => {
    const response = await apiClient.get<GovernancePermissions>('/admin/permissions', {
        params: { domain_id: domainId },
    });
    return response.data;
}

export const createInstitutionalDomain = async (
    payload: InstitutionalIntakePayload,
): Promise<InstitutionalIntakeResponse> => {
    const response = await apiClient.post<InstitutionalIntakeResponse>(
        '/admin/institutional-inputs/domains',
        payload,
    );
    return response.data;
}

export const fetchPublicPolicyGuides = async (): Promise<PublicPolicyGuideListItem[]> => {
    const response = await apiClient.get<{ items: PublicPolicyGuideListItem[] }>('/public/policy-guides');
    return response.data.items;
}

export const fetchPublicPolicyGuide = async (domainId: string): Promise<PublicPolicyGuide> => {
    const response = await apiClient.get<PublicPolicyGuide>(`/public/policy-guides/${domainId}`);
    return response.data;
}

export const requestPublicPolicySupport = async (
    domainId: string,
    payload: PublicSupportRequestPayload,
): Promise<{ request_id: string; status: 'OPEN' }> => {
    const response = await apiClient.post<{ request_id: string; status: 'OPEN' }>(
        `/public/policy-guides/${domainId}/support`,
        payload,
    );
    return response.data;
}

export const fetchAdminDomains = async (): Promise<AdminDomain[]> => {
    const response = await apiClient.get<{ items: AdminDomain[] }>('/admin/domains');
    return response.data.items;
}

export const fetchRecordImportFields = async (domainId: string): Promise<RecordImportField[]> => {
    const response = await apiClient.get<{ items: RecordImportField[] }>(`/admin/domains/${domainId}/record-import-fields`);
    return response.data.items;
}

export const fetchFactReviewFields = async (domainId: string): Promise<RecordImportField[]> => {
    const response = await apiClient.get<{ items: RecordImportField[] }>(`/admin/domains/${domainId}/fact-fields`);
    return response.data.items;
}

export const fetchEvidenceSources = async (
    domainId: string,
    subjectId: string,
): Promise<EvidenceSourceSummary[]> => {
    const response = await apiClient.get<{ items: EvidenceSourceSummary[] }>('/governance/evidence', {
        params: { domain_id: domainId, subject_id: subjectId },
    });
    return response.data.items;
}

export const fetchEvidenceFactProposals = async (
    domainId: string,
    evidenceId: string,
): Promise<EvidenceFactProposal[]> => {
    const response = await apiClient.get<{ items: EvidenceFactProposal[] }>('/governance/evidence-fact-proposals', {
        params: { domain_id: domainId, evidence_id: evidenceId },
    });
    return response.data.items;
}

export const createEvidenceFactProposal = async (
    payload: EvidenceFactProposalInput,
): Promise<EvidenceFactProposal> => {
    const response = await apiClient.post<EvidenceFactProposal>('/governance/evidence-fact-proposals', payload);
    return response.data;
}

export const attestEvidenceFactProposal = async (
    proposalId: string,
    domainId: string,
    action: 'ACCEPT' | 'REJECT',
    note: string,
): Promise<EvidenceFactProposal> => {
    const response = await apiClient.post<EvidenceFactProposal>(`/governance/evidence-fact-proposals/${proposalId}/attest`, {
        domain_id: domainId,
        action,
        note,
    });
    return response.data;
}

export const fetchSubjectInstitutionalTimeline = async (): Promise<InstitutionalContextEvent[]> => {
    const response = await apiClient.get<{ items: InstitutionalContextEvent[] }>('/institutional-timeline');
    return response.data.items;
}

export const fetchStaffInstitutionalTimeline = async (
    domainId: string,
    subjectId: string,
): Promise<InstitutionalContextEvent[]> => {
    const response = await apiClient.get<{ items: InstitutionalContextEvent[] }>('/governance/institutional-timeline', {
        params: { domain_id: domainId, subject_id: subjectId },
    });
    return response.data.items;
}

export const createInstitutionalContextEvent = async (
    payload: InstitutionalContextEventInput,
): Promise<InstitutionalContextEvent> => {
    const response = await apiClient.post<InstitutionalContextEvent>('/governance/institutional-context-events', payload);
    return response.data;
}

export const attestInstitutionalContextEvent = async (
    eventId: string,
    domainId: string,
    action: 'CERTIFY' | 'REJECT',
    note: string,
): Promise<InstitutionalContextEvent> => {
    const response = await apiClient.post<InstitutionalContextEvent>(`/governance/institutional-context-events/${eventId}/attest`, {
        domain_id: domainId,
        action,
        note,
    });
    return response.data;
}

export const fetchCalibrationReleases = async (domainId: string): Promise<CalibrationRelease[]> => {
    const response = await apiClient.get<{ items: CalibrationRelease[] }>(`/governance/domains/${domainId}/calibration-releases`);
    return response.data.items;
}

export const fetchShadowCalibrations = async (domainId: string): Promise<ShadowCalibrationSuiteSummary[]> => {
    const response = await apiClient.get<{ items: ShadowCalibrationSuiteSummary[] }>('/governance/shadow-calibrations', {
        params: { domain_id: domainId },
    });
    return response.data.items;
}

export const fetchShadowCalibration = async (suiteId: string, domainId: string): Promise<ShadowCalibrationSuite> => {
    const response = await apiClient.get<ShadowCalibrationSuite>(`/governance/shadow-calibrations/${suiteId}`, {
        params: { domain_id: domainId },
    });
    return response.data;
}

export const createShadowCalibration = async (payload: ShadowCalibrationSuiteInput): Promise<ShadowCalibrationSuite> => {
    const response = await apiClient.post<ShadowCalibrationSuite>('/governance/shadow-calibrations', payload);
    return response.data;
}

export const certifyShadowCalibration = async (
    suiteId: string,
    domainId: string,
    note: string,
): Promise<ShadowCalibrationSuite> => {
    const response = await apiClient.post<ShadowCalibrationSuite>(`/governance/shadow-calibrations/${suiteId}/certify`, {
        domain_id: domainId,
        note,
    });
    return response.data;
}

export const runShadowCalibration = async (
    suiteId: string,
    domainId: string,
): Promise<{ run: ShadowCalibrationRun; message: string }> => {
    const response = await apiClient.post<{ run: ShadowCalibrationRun; message: string }>(`/governance/shadow-calibrations/${suiteId}/run`, {
        domain_id: domainId,
    });
    return response.data;
}

export const resolveShadowCalibrationFinding = async (
    findingId: string,
    domainId: string,
    classification: CalibrationFindingClassification,
    note: string,
): Promise<ShadowCalibrationFinding> => {
    const response = await apiClient.patch<ShadowCalibrationFinding>(`/governance/shadow-calibration-findings/${findingId}`, {
        domain_id: domainId,
        classification,
        note,
    });
    return response.data;
}

export const previewSystemRecordImport = async (
    domainId: string,
    contract: SystemRecordImportContract,
    file: File,
): Promise<SystemRecordImportPreview> => {
    const formData = new FormData();
    formData.append('domain_id', domainId);
    formData.append('contract_json', JSON.stringify(contract));
    formData.append('file', file);
    const response = await apiClient.post<SystemRecordImportPreview>(
        '/admin/system-record-imports/preview',
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
}

export const materializeSystemRecordImport = async (
    domainId: string,
    mappingId: string,
    file: File,
): Promise<SystemRecordMaterializationResult> => {
    const form = new FormData();
    form.append('domain_id', domainId);
    form.append('mapping_id', mappingId);
    form.append('file', file);
    const response = await apiClient.post<SystemRecordMaterializationResult>(
        '/admin/system-record-imports/materialize', form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return response.data;
}

export const fetchInstitutionalDataSources = async (domainId: string): Promise<InstitutionalDataSource[]> => {
    const response = await apiClient.get<{ items: InstitutionalDataSource[] }>('/admin/institutional-data-sources', { params: { domain_id: domainId } });
    return response.data.items;
};

export const submitInstitutionalDataSource = async (payload: Omit<InstitutionalDataSource, 'source_id' | 'status' | 'author_id' | 'reviewed_by' | 'review_note'>): Promise<InstitutionalDataSource> => {
    const response = await apiClient.post<InstitutionalDataSource>('/admin/institutional-data-sources', payload);
    return response.data;
};

export const approveInstitutionalDataSource = async (sourceId: string, domainId: string): Promise<InstitutionalDataSource> => {
    const response = await apiClient.post<InstitutionalDataSource>(`/admin/institutional-data-sources/${sourceId}/approve`, { domain_id: domainId });
    return response.data;
};

export const fetchSystemRecordImportMappings = async (
    domainId: string,
): Promise<SystemRecordImportMappingList> => {
    const response = await apiClient.get<SystemRecordImportMappingList>('/admin/system-record-import-mappings', {
        params: { domain_id: domainId },
    });
    return response.data;
}

export const submitSystemRecordImportMapping = async (
    domainId: string,
    contract: SystemRecordImportContract,
): Promise<SystemRecordImportMapping> => {
    const response = await apiClient.post<SystemRecordImportMapping>('/admin/system-record-import-mappings', {
        domain_id: domainId,
        contract,
    });
    return response.data;
}

export const approveSystemRecordImportMapping = async (
    mappingId: string,
    domainId: string,
): Promise<SystemRecordImportMapping> => {
    const response = await apiClient.post<SystemRecordImportMapping>(
        `/admin/system-record-import-mappings/${mappingId}/approve`,
        { domain_id: domainId },
    );
    return response.data;
}

export const rejectSystemRecordImportMapping = async (
    mappingId: string,
    domainId: string,
    reason: string,
): Promise<SystemRecordImportMapping> => {
    const response = await apiClient.post<SystemRecordImportMapping>(
        `/admin/system-record-import-mappings/${mappingId}/reject`,
        { domain_id: domainId, reason },
    );
    return response.data;
}

export const fetchSupportRequests = async (domainId: string): Promise<SupportRequest[]> => {
    const response = await apiClient.get<{ items: SupportRequest[] }>('/admin/support-requests', {
        params: { domain_id: domainId },
    });
    return response.data.items;
}

export const updateSupportRequestStatus = async (
    requestId: string,
    domainId: string,
    status: SupportRequestStatus,
): Promise<SupportRequest> => {
    const response = await apiClient.patch<SupportRequest>(`/admin/support-requests/${requestId}`, {
        domain_id: domainId,
        status,
    });
    return response.data;
}

export const fetchDecisionReviewCases = async (domainId?: string): Promise<DecisionReviewCase[]> => {
    const response = await apiClient.get<{ items: DecisionReviewCase[] }>('/decision-reviews', {
        params: domainId ? { domain_id: domainId } : undefined,
    });
    return response.data.items;
}

export const submitDecisionReview = async (
    payload: DecisionReviewSubmissionPayload,
): Promise<DecisionReviewCase> => {
    const response = await apiClient.post<DecisionReviewCase>('/decision-reviews', payload);
    return response.data;
}

export const updateDecisionReviewCase = async (
    reviewCaseId: string,
    domainId: string,
    status: Exclude<DecisionReviewStatus, 'SUBMITTED'>,
    resolution?: DecisionReviewResolution,
    responseMessage?: string,
): Promise<DecisionReviewCase> => {
    const response = await apiClient.patch<DecisionReviewCase>(`/admin/decision-reviews/${reviewCaseId}`, {
        domain_id: domainId,
        status,
        ...(resolution ? { resolution } : {}),
        ...(responseMessage ? { response_message: responseMessage } : {}),
    });
    return response.data;
}

export const fetchPendingPolicyReviews = async (): Promise<PendingPolicyReview[]> => {
    const response = await apiClient.get<{ items: PendingPolicyReview[] }>('/governance/drafts');
    return response.data.items;
}

export const fetchPolicyReview = async (draftId: string): Promise<PolicyReview> => {
    const response = await apiClient.get<PolicyReview>(`/governance/drafts/${draftId}/review`);
    return response.data;
}

export interface ReleaseScheduleInput {
    version: string;
    effectiveFrom: string;
    effectiveUntil?: string;
    applicability?: Array<{ attribute: string; values: string[] }>;
    workflows?: Array<{
        id: string;
        trigger_condition: 'overall == pass' | 'overall == fail';
        action_type: 'CREATE_INTERNAL_TASK' | 'PREPARE_NO_WRITE_EXPORT' | 'PREPARE_NOTIFICATION';
        action_payload: Record<string, string>;
    }>;
}

export const publishPolicyDraft = async (
    draftId: string,
    schedule: ReleaseScheduleInput,
): Promise<ReleasePublication> => {
    const response = await apiClient.post<ReleasePublication>('/governance/releases', {
        draft_id: draftId,
        version: schedule.version,
        effective_from: schedule.effectiveFrom,
        ...(schedule.effectiveUntil ? { effective_until: schedule.effectiveUntil } : {}),
        applicability: schedule.applicability || [],
    });
    return response.data;
}

export const fetchPolicyAmbiguities = async (domainId: string): Promise<PolicyAmbiguity[]> => {
    const response = await apiClient.get<{ items: PolicyAmbiguity[] }>('/governance/policy-ambiguities', {
        params: { domain_id: domainId },
    });
    return response.data.items;
}

export const createPolicyAmbiguity = async (payload: {
    domain_id: string;
    source_citation: string;
    question: string;
    interpretation_options: string[];
}): Promise<PolicyAmbiguity> => {
    const response = await apiClient.post<PolicyAmbiguity>('/governance/policy-ambiguities', payload);
    return response.data;
}

export const resolvePolicyAmbiguity = async (
    ambiguityId: string,
    payload: { domain_id: string; resolution: string; source_reference: string },
): Promise<PolicyAmbiguity> => {
    const response = await apiClient.patch<PolicyAmbiguity>(
        `/governance/policy-ambiguities/${ambiguityId}/resolve`,
        payload,
    );
    return response.data;
}

export const fetchHandbookUploads = async (): Promise<HandbookUpload[]> => {
    const response = await apiClient.get<{ items: HandbookUpload[] }>('/governance/handbooks');
    return response.data.items;
}

export const fetchHandbookPages = async (handbookId: string, afterPage = 0): Promise<HandbookSourceReview> => {
    const response = await apiClient.get<HandbookSourceReview>(`/governance/handbooks/${handbookId}/pages`, {
        params: { after_page: afterPage },
    });
    return response.data;
}

export const requestHandbookOCR = async (handbookId: string): Promise<HandbookUpload> => {
    const response = await apiClient.post<HandbookUpload>(`/governance/handbooks/${handbookId}/ocr`);
    return response.data;
}

export const fetchHandbookOCRReviews = async (handbookId: string): Promise<HandbookOCRReview[]> => {
    const response = await apiClient.get<{ items: HandbookOCRReview[] }>(`/governance/handbooks/${handbookId}/ocr-reviews`);
    return response.data.items;
}

export const reviewHandbookOCR = async (
    handbookId: string,
    pageNumber: number,
    action: 'ACCEPT' | 'CORRECT' | 'REJECT',
    reviewedText?: string,
): Promise<HandbookOCRReview> => {
    const response = await apiClient.patch<HandbookOCRReview>(
        `/governance/handbooks/${handbookId}/ocr-reviews/${pageNumber}`,
        { action, reviewed_text: reviewedText },
    );
    return response.data;
}

export const uploadHandbook = async (domainId: string, file: File): Promise<HandbookUpload> => {
    try {
        const sessionResponse = await apiClient.post<HandbookUploadSession>('/governance/handbook-upload-sessions', {
            domain_id: domainId,
            file_name: file.name,
            content_type: file.type || 'application/pdf',
            file_size_bytes: file.size,
        });
        const directFormData = new FormData();
        for (const [name, value] of Object.entries(sessionResponse.data.upload_fields)) {
            directFormData.append(name, value);
        }
        directFormData.append('file', file);
        const directResponse = await fetch(sessionResponse.data.upload_url, {
            method: 'POST',
            body: directFormData,
        });
        if (!directResponse.ok) {
            throw new Error('The handbook could not be uploaded to secure document storage.');
        }
        const completion = await apiClient.post<HandbookUpload>(
            `/governance/handbook-upload-sessions/${sessionResponse.data.session_id}/complete`,
        );
        return completion.data;
    } catch (error) {
        const status = (error as { response?: { status?: number } }).response?.status;
        if (status !== 503) throw error;
    }

    const formData = new FormData();
    formData.append('domain_id', domainId);
    formData.append('file', file);
    const response = await apiClient.post<HandbookUpload>('/governance/handbooks', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
}
