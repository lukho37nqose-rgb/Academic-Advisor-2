import axios from 'axios';

// Defaults to localhost for dev, can be configured via Vite env vars
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

const AUTH_TOKEN = import.meta.env.VITE_AUTH_TOKEN;

apiClient.interceptors.request.use((config) => {
  if (AUTH_TOKEN) {
    config.headers.Authorization = `Bearer ${AUTH_TOKEN}`;
  }
  return config;
});

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

export interface InstitutionalIntakePayload {
    institution_name: string;
    domain_name: string;
    policy_name?: string;
    public_policy_guide: boolean;
    assistance_requests_enabled: boolean;
    support_response_target_hours: number;
    decision_review_enabled: boolean;
    decision_review_response_target_hours?: number;
    support_privacy_notice_url?: string;
    offline_assistance_instructions?: string;
    facts: InstitutionalFactInput[];
    rules: InstitutionalRuleInput[];
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

export type SupportRequestStatus = 'OPEN' | 'IN_PROGRESS' | 'CLOSED';

export interface SupportRequest {
    id: string;
    domain_id: string;
    category: 'missing_information' | 'unique_circumstance' | 'accessibility' | 'other';
    contact_details?: string | null;
    message: string;
    status: SupportRequestStatus;
    response_due_at?: string | null;
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
    resolved_at?: string | null;
    closed_at?: string | null;
    retention_expires_at?: string | null;
    is_overdue?: boolean;
    created_at?: string | null;
    updated_at?: string | null;
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
    proposed_text: string;
    proposed_text_hash: string;
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
export const evaluateEvidence = async (evidenceId: string, ruleGraphId: string, subjectId: string): Promise<EvaluationSummary> => {
    // Requires Idempotency-Key
    const idempotencyKey = `ui-${Date.now()}`;
    const response = await apiClient.post<EvaluationSummary>('/evaluate', {
        rule_graph_id: ruleGraphId,
        evidence_id: evidenceId,
        subject_id: subjectId,
        domain_id: "sandbox_domain",
        release_version: "1.0"
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

export const fetchDecisionReviewCases = async (domainId: string): Promise<DecisionReviewCase[]> => {
    const response = await apiClient.get<{ items: DecisionReviewCase[] }>('/decision-reviews', {
        params: { domain_id: domainId },
    });
    return response.data.items;
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
