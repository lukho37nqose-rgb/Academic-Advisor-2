import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function openApplication(page: Page) {
    for (let attempt = 0; attempt < 2; attempt += 1) {
        await page.goto('/', { waitUntil: 'domcontentloaded' });
        try {
            await expect(page.getByRole('button', { name: 'Investigations' })).toBeVisible({ timeout: 5_000 });
            return;
        } catch (error) {
            if (attempt === 1) throw error;
            await page.waitForTimeout(250);
        }
    }
}

// Mock reasoning graph representing a successful evaluation
const mockGraphEligible = {
    id: "trace_1",
    subject_id: "student_1",
    rule_graph_id: "rg_1",
    nodes: {
        "gn_fact_1": { id: "gn_fact_1", type: "fact", label: "Fact: academic.gpa", data: { resolved_value: 3.5 }, computed_confidence: 1.0 },
        "gn_eval_1": { id: "gn_eval_1", type: "rule_evaluation", label: "Check GPA", data: { passed: true, expected_condition: ">=", expected_value: 3.0 }, computed_confidence: 1.0 },
        "gn_conclusion": { id: "gn_conclusion", type: "conclusion", label: "Final Conclusion", data: { overall_passed: true }, computed_confidence: 1.0 }
    },
    edges: []
};

// Mock reasoning graph representing a manual review
const mockGraphManualReview = {
    id: "trace_2",
    subject_id: "student_2",
    rule_graph_id: "rg_2",
    nodes: {
        "gn_fact_2": { id: "gn_fact_2", type: "fact", label: "Fact: academic.gpa", data: { resolved_value: "needs_human_review" }, computed_confidence: 0.5 },
        "gn_eval_2": { id: "gn_eval_2", type: "rule_evaluation", label: "Check GPA", data: { passed: "NEEDS_MANUAL_REVIEW", expected_condition: ">=", expected_value: 3.0 }, computed_confidence: 0.5 },
        "gn_conclusion": { id: "gn_conclusion", type: "conclusion", label: "Final Conclusion", data: { overall_passed: "NEEDS_MANUAL_REVIEW" }, computed_confidence: 0.5 }
    },
    edges: []
};

test.describe('Reasoning Graph Observability Dashboard', () => {

    test('should render empty state initially', async ({ page }) => {
        await openApplication(page);
        await expect(page.getByText('No active trace')).toBeVisible();
    });

    test('should successfully evaluate and render an ELIGIBLE graph', async ({ page }) => {
        // Intercept API calls
        await page.route('**/api/v1/evaluate', async route => {
            const json = { decision: "ELIGIBLE", overall_confidence: 1.0, reasoning_graph_id: "trace_1", release_version: "1.0" };
            await route.fulfill({ json });
        });
        
        await page.route('**/api/v1/reasoning/trace_1', async route => {
            await route.fulfill({ json: mockGraphEligible });
        });

        await openApplication(page);
        
        // Trigger evaluation
        await page.getByRole('button', { name: 'Begin Investigation' }).click();

        // Verify Graph renders correctly
        await expect(page.getByText('Final Conclusion')).toBeVisible();
        await expect(page.getByRole('heading', { name: 'Eligible' })).toBeVisible();
        await expect(page.getByText('Confidence Score: 100.0%')).toBeVisible();
        
        await expect(page.getByText('academic.gpa')).toBeVisible();
        await expect(page.getByText('3.5')).toBeVisible();
        await expect(page.getByText('Check GPA')).toBeVisible();
    });

    test('should render a NEEDS_MANUAL_REVIEW graph', async ({ page }) => {
        // Intercept API calls
        await page.route('**/api/v1/evaluate', async route => {
            const json = { decision: "NEEDS_MANUAL_REVIEW", overall_confidence: 0.5, reasoning_graph_id: "trace_2", release_version: "1.0" };
            await route.fulfill({ json });
        });
        
        await page.route('**/api/v1/reasoning/trace_2', async route => {
            await route.fulfill({ json: mockGraphManualReview });
        });

        await openApplication(page);
        
        // Trigger evaluation
        await page.getByRole('button', { name: 'Begin Investigation' }).click();

        // Verify Graph renders correctly for manual review
        await expect(page.getByRole('heading', { name: 'Needs Manual Review' })).toBeVisible();
        await expect(page.getByText('Confidence Score: 50.0%')).toBeVisible();
        await expect(page.getByText('needs_human_review')).toBeVisible();
    });
});

test.describe('Subject Decision Review', () => {
    test('allows a subject to request a review only for their loaded decision trace', async ({ page }) => {
        const subjectGraph = {
            ...mockGraphEligible,
            id: 'trace_subject',
            evaluation_context: { domain_id: 'dom_subject', release_version: '2026.1' },
        };
        await page.route('**/api/v1/reasoning/trace_subject', async route => {
            await route.fulfill({ json: subjectGraph });
        });
        await page.route('**/api/v1/decision-reviews', async route => {
            if (route.request().method() === 'GET') {
                await route.fulfill({ json: { items: [] } });
                return;
            }
            expect(route.request().postDataJSON()).toEqual({
                domain_id: 'dom_subject',
                reasoning_graph_id: 'trace_subject',
                category: 'evidence_correction',
                message: 'The GPA fact does not reflect my corrected record.',
                disputed_fact_paths: ['academic.gpa'],
            });
            await route.fulfill({
                status: 201,
                json: {
                    id: 'review_subject_1', domain_id: 'dom_subject', subject_id: 'subject_1', reasoning_graph_id: 'trace_subject',
                    category: 'evidence_correction', message: 'The GPA fact does not reflect my corrected record.',
                    disputed_fact_paths: ['academic.gpa'], submitted_evidence_ids: [], status: 'SUBMITTED',
                },
            });
        });

        await page.goto('/?experience=subject&trace=trace_subject', { waitUntil: 'domcontentloaded' });
        await expect(page.getByRole('heading', { name: 'Decision review' })).toBeVisible();
        await page.getByRole('checkbox', { name: 'academic.gpa' }).check();
        await page.getByLabel('Tell us what should be checked').fill('The GPA fact does not reflect my corrected record.');
        await page.getByRole('button', { name: 'Request review' }).click();
        await expect(page.getByText('Review request recorded. Reference: review_subject_1.')).toBeVisible();
    });

    test('has no automated accessibility violations in the trace-bound review form', async ({ page }) => {
        const subjectGraph = {
            ...mockGraphEligible,
            id: 'trace_accessible',
            evaluation_context: { domain_id: 'dom_subject', release_version: '2026.1' },
        };
        await page.route('**/api/v1/reasoning/trace_accessible', async route => {
            await route.fulfill({ json: subjectGraph });
        });
        await page.route('**/api/v1/decision-reviews', async route => {
            await route.fulfill({ json: { items: [] } });
        });

        await page.goto('/?experience=subject&trace=trace_accessible', { waitUntil: 'domcontentloaded' });
        await expect(page.getByRole('heading', { name: 'Request a decision review' })).toBeVisible();

        const accessibilityScan = await new AxeBuilder({ page }).include('main').analyze();
        expect(accessibilityScan.violations).toEqual([]);
    });
});

test.describe('Governance Desk', () => {
    test('loads Edge metadata policy and submits a quick edit', async ({ page }) => {
        await page.route('**/api/v1/admin/permissions*', async route => {
            await route.fulfill({
                json: {
                    current_role: 'metadata_steward',
                    domain_id: 'dom_curr_2026',
                    metadata_quick_edits: [
                        {
                            target_type: 'course',
                            label: 'Course',
                            identifier_label: 'Course code',
                            fields: [
                                {
                                    name: 'course_description',
                                    label: 'Course description',
                                    risk: 'low',
                                    notes: 'Narrative metadata only.',
                                },
                            ],
                        },
                    ],
                    review_required_changes: ['Prerequisites'],
                    formal_governance_changes: ['Graduation requirements'],
                    matrix: [
                        {
                            role: 'metadata_steward',
                            label: 'Metadata steward',
                            can_quick_edit: true,
                            can_author_structured_drafts: false,
                            can_approve_releases: false,
                            can_replay_audits: false,
                            scope: 'Assigned domain metadata only.',
                        },
                    ],
                },
            });
        });
        await page.route('**/api/v1/admin/quick-edits', async route => {
            const payload = route.request().postDataJSON();
            await route.fulfill({
                status: 201,
                json: {
                    ...payload,
                    change_id: 'qe_1',
                    status: 'applied',
                    applied_by: 'steward_1',
                    field_policy: {
                        label: 'Course description',
                        risk: 'low',
                        notes: 'Narrative metadata only.',
                    },
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Governance Desk' }).click();
        await expect(page.getByRole('heading', { name: 'Tier 1 metadata' })).toBeVisible();

        await page.getByLabel('Course code').fill('ECO1010F');
        await page.getByLabel('New value').fill('Updated course description.');
        await page.getByLabel('Reason').fill('Corrected against the current handbook.');
        await page.getByLabel('Source reference').fill('Handbook 2026, p.14');
        await page.getByRole('button', { name: 'Apply quick edit' }).click();

        await expect(page.getByText('Applied Course description to ECO1010F under change qe_1.')).toBeVisible();
    });
});

test.describe('Institutional Input And Public Access', () => {
    test('lets staff preview a CSV export using only declared decision facts', async ({ page }) => {
        await page.route('**/api/v1/admin/domains', async route => {
            await route.fulfill({ json: { items: [{ domain_id: 'dom_import', domain_name: 'Student Support Eligibility' }] } });
        });
        await page.route('**/api/v1/admin/domains/dom_import/record-import-fields', async route => {
            await route.fulfill({ json: { items: [{ target_path: 'facts.household_income', label: 'Annual household income', schema_type: 'number' }] } });
        });
        await page.route('**/api/v1/admin/system-record-imports/preview', async route => {
            expect(route.request().method()).toBe('POST');
            await route.fulfill({
                json: {
                    contract_sha256: 'a'.repeat(64), source_sha256: 'b'.repeat(64), source_system: 'Example records', mapping_id: 'income-v1',
                    row_count: 2, accepted_record_count: 2, rejected_row_count: 0, ignored_columns: ['unneeded_note'], issues: [],
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'System Records' }).click();
        await page.getByLabel('CSV export').setInputFiles({
            name: 'records.csv', mimeType: 'text/csv', buffer: Buffer.from('record_id,version,income\nsubject_1,1,120000\n'),
        });
        await page.getByLabel('Mapping name').fill('income-v1');
        await page.getByLabel('Source system').fill('Example records');
        await page.getByLabel('Subject identifier column').fill('record_id');
        await page.getByLabel('Source record version column').fill('version');
        await page.getByLabel('Export column name').fill('income');
        await page.getByRole('button', { name: 'Check export' }).click();
        await expect(page.getByRole('heading', { name: 'Export check' })).toBeVisible();
        await expect(page.getByText('Ignored columns: unneeded_note.')).toBeVisible();
    });

    test('creates a policy draft from guided institutional input', async ({ page }) => {
        await page.route('**/api/v1/admin/institutional-inputs/domains', async route => {
            const payload = route.request().postDataJSON();
            expect(payload.facts[0].label).toBe('Annual household income');
            expect(payload.rules[0].operator).toBe('at_most');
            expect(payload.decision_review_enabled).toBe(true);
            expect(payload.decision_review_response_target_hours).toBe(120);
            await route.fulfill({
                status: 201,
                json: {
                    tenant_id: 'tenant_1',
                    domain_id: 'dom_1',
                    domain_name: 'Student Support Eligibility',
                    draft_id: 'draft_1',
                    policy_name: 'Student Support Eligibility initial policy',
                    status: 'PENDING_REVIEW',
                    fact_count: 1,
                    rule_count: 1,
                    next_step: 'A separate release approver must review and publish this policy draft.',
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Institution Setup' }).click();
        await page.getByLabel('Institution name').fill('Example Institution');
        await page.getByLabel('Decision domain').fill('Student Support Eligibility');
        await page.getByLabel('Privacy notice URL').fill('https://example.test/privacy');
        await page.getByLabel('Assisted or offline contact route').focus();
        await page.keyboard.insertText('Call the Student Support desk on weekdays.');
        await page.getByRole('checkbox', { name: 'Enable decision review cases' }).check();
        await page.getByRole('button', { name: 'Continue' }).click();

        await page.getByLabel('Fact label').fill('Annual household income');
        await page.getByLabel('Type').selectOption('number');
        await page.getByRole('button', { name: 'Continue' }).click();

        await page.getByRole('button', { name: 'Add condition' }).click();
        await page.getByLabel('Condition name').fill('Income is within the support threshold');
        await page.getByLabel('Test').selectOption('at_most');
        await page.getByLabel('Value').fill('350000');
        await page.getByLabel('Source citation').fill('Support Policy 2026, section 2.1');
        await page.getByRole('button', { name: 'Continue' }).click();
        await page.getByRole('button', { name: 'Create policy draft' }).click();

        await expect(page.getByRole('heading', { name: 'Policy draft created' })).toBeVisible();
        await expect(page.getByText('Pending review')).toBeVisible();
    });

    test('shows an approved public guide and records a human-assistance request', async ({ page }) => {
        await page.route('**/api/v1/public/policy-guides', async route => {
            await route.fulfill({
                json: {
                    items: [{ domain_id: 'dom_public', domain_name: 'Student Support Eligibility', version: '2026.1' }],
                },
            });
        });
        await page.route('**/api/v1/public/policy-guides/dom_public', async route => {
            await route.fulfill({
                json: {
                    domain_id: 'dom_public',
                    domain_name: 'Student Support Eligibility',
                    version: '2026.1',
                    assistance_requests_enabled: true,
                    support_response_target_hours: 48,
                    support_privacy_notice_url: 'https://example.test/privacy',
                    offline_assistance_instructions: 'Call the Student Support desk on weekdays.',
                    policy: {
                        kind: 'rule',
                        label: 'Income is within the support threshold',
                        fact_label: 'Annual household income',
                        operator: 'is at most',
                        expected_value: 350000,
                        citation: 'Support Policy 2026, section 2.1',
                    },
                },
            });
        });
        await page.route('**/api/v1/public/policy-guides/dom_public/support', async route => {
            await route.fulfill({ status: 202, json: { request_id: 'support_1', status: 'OPEN' } });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Policy Guides' }).click();
        await page.getByRole('button', { name: /Student Support Eligibility/ }).click();
        await expect(page.getByText('This guide explains the approved policy. It does not decide an individual case.')).toBeVisible();
        await expect(page.getByText('Support Policy 2026, section 2.1')).toBeVisible();
        await expect(page.getByText('Response target: within 48 hours.')).toBeVisible();
        await expect(page.getByText('Call the Student Support desk on weekdays.')).toBeVisible();

        await page.getByLabel('What is missing or different?').fill('My circumstances are different from the listed policy conditions.');
        await page.getByRole('button', { name: 'Request assistance' }).click();
        await expect(page.getByText('Your request has been recorded for human follow-up.')).toBeVisible();
    });

    test('lets an assistance coordinator triage an assigned domain request', async ({ page }) => {
        await page.route('**/api/v1/admin/domains', async route => {
            await route.fulfill({
                json: { items: [{ domain_id: 'dom_public', domain_name: 'Student Support Eligibility' }] },
            });
        });
        await page.route('**/api/v1/admin/support-requests?domain_id=dom_public', async route => {
            await route.fulfill({
                json: {
                    items: [{
                        id: 'support_1',
                        domain_id: 'dom_public',
                        category: 'accessibility',
                        contact_details: 'person@example.test',
                        message: 'I need an alternative route to access the required information.',
                        status: 'OPEN',
                        response_due_at: '2026-07-27T12:00:00Z',
                        is_overdue: false,
                        created_at: '2026-07-25T12:00:00Z',
                    }],
                },
            });
        });
        await page.route('**/api/v1/admin/support-requests/support_1', async route => {
            expect(route.request().method()).toBe('PATCH');
            expect(route.request().postDataJSON()).toEqual({ domain_id: 'dom_public', status: 'IN_PROGRESS' });
            await route.fulfill({
                json: {
                    id: 'support_1',
                    domain_id: 'dom_public',
                    category: 'accessibility',
                    contact_details: 'person@example.test',
                    message: 'I need an alternative route to access the required information.',
                    status: 'IN_PROGRESS',
                    response_due_at: '2026-07-27T12:00:00Z',
                    is_overdue: false,
                    created_at: '2026-07-25T12:00:00Z',
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Assistance Inbox' }).click();
        await expect(page.getByRole('heading', { name: 'Assistance inbox' })).toBeVisible();
        await expect(page.getByText('I need an alternative route to access the required information.')).toBeVisible();

        const status = page.getByLabel('Status for request support_1');
        await status.selectOption('IN_PROGRESS');
        await expect(status).toHaveValue('IN_PROGRESS');
    });

    test('lets a coordinator acknowledge a subject decision review case', async ({ page }) => {
        await page.route('**/api/v1/admin/domains', async route => {
            await route.fulfill({ json: { items: [{ domain_id: 'dom_review', domain_name: 'Student Support Eligibility' }] } });
        });
        await page.route('**/api/v1/decision-reviews?domain_id=dom_review', async route => {
            await route.fulfill({
                json: {
                    items: [{
                        id: 'review_1', domain_id: 'dom_review', subject_id: 'subject_1', reasoning_graph_id: 'trace_1',
                        category: 'evidence_correction', message: 'The household income record needs correction.',
                        disputed_fact_paths: ['facts.household_income'], submitted_evidence_ids: ['evidence_2'],
                        status: 'SUBMITTED', response_due_at: '2026-07-27T12:00:00Z', is_overdue: false,
                        created_at: '2026-07-25T12:00:00Z',
                    }],
                },
            });
        });
        await page.route('**/api/v1/admin/decision-reviews/review_1', async route => {
            expect(route.request().postDataJSON()).toMatchObject({ domain_id: 'dom_review', status: 'ACKNOWLEDGED' });
            await route.fulfill({
                json: {
                    id: 'review_1', domain_id: 'dom_review', subject_id: 'subject_1', reasoning_graph_id: 'trace_1',
                    category: 'evidence_correction', message: 'The household income record needs correction.',
                    disputed_fact_paths: ['facts.household_income'], submitted_evidence_ids: ['evidence_2'],
                    status: 'ACKNOWLEDGED', response_due_at: '2026-07-27T12:00:00Z', is_overdue: false,
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Review Cases' }).click();
        await expect(page.getByRole('heading', { name: 'Decision review cases' })).toBeVisible();
        await expect(page.getByText('The household income record needs correction.')).toBeVisible();
        await page.getByRole('button', { name: 'Acknowledge' }).click();
        await expect(page.getByRole('button', { name: 'Begin review' })).toBeVisible();
    });

    test('queues a handbook source without creating a policy release', async ({ page }) => {
        await page.route('**/api/v1/admin/domains', async route => {
            await route.fulfill({ json: { items: [{ domain_id: 'dom_1', domain_name: 'Student Support Eligibility' }] } });
        });
        await page.route('**/api/v1/governance/handbooks', async route => {
            await route.fulfill({ json: { items: [] } });
        });
        await page.route('**/api/v1/governance/handbook-upload-sessions', async route => {
            await route.fulfill({
                status: 201,
                json: {
                    session_id: 'session_1',
                    upload_url: 'https://storage.example.test/upload',
                    upload_fields: { key: 'handbook-staging/session_1.pdf' },
                    expires_at: '2026-07-25T13:00:00Z',
                },
            });
        });
        await page.route('https://storage.example.test/upload', async route => {
            await route.fulfill({ status: 204 });
        });
        await page.route('**/api/v1/governance/handbook-upload-sessions/session_1/complete', async route => {
            await route.fulfill({
                status: 201,
                json: {
                    handbook_id: 'handbook_1', domain_id: 'dom_1', file_name: 'handbook.pdf', file_size_bytes: 2048,
                    content_hash: null, status: 'QUEUED', processed_pages: 0,
                    next_step: 'The extraction worker will create and hash an immutable review source; it cannot publish a policy.',
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Handbook Intake' }).click();
        await page.getByLabel('Handbook PDF').setInputFiles({
            name: 'handbook.pdf',
            mimeType: 'application/pdf',
            buffer: Buffer.from('%PDF-1.4 handbook source'),
        });
        await page.getByRole('button', { name: 'Queue handbook' }).click();
        await expect(page.getByText('handbook.pdf')).toBeVisible();
        await expect(page.getByRole('cell', { name: 'QUEUED', exact: true })).toBeVisible();
    });

    test('lets an author inspect extracted handbook pages with a source citation', async ({ page }) => {
        await page.route('**/api/v1/admin/domains', async route => {
            await route.fulfill({ json: { items: [{ domain_id: 'dom_1', domain_name: 'Student Support Eligibility' }] } });
        });
        await page.route('**/api/v1/governance/handbooks', async route => {
            await route.fulfill({
                json: {
                    items: [{
                        handbook_id: 'handbook_ready', domain_id: 'dom_1', file_name: 'support-handbook.pdf', file_size_bytes: 2048,
                        content_hash: 'a'.repeat(64), status: 'READY_FOR_REVIEW', total_pages: 42, processed_pages: 42,
                    }],
                },
            });
        });
        await page.route('**/api/v1/governance/handbooks/handbook_ready/pages*', async route => {
            await route.fulfill({
                json: {
                    handbook_id: 'handbook_ready', file_name: 'support-handbook.pdf', status: 'READY_FOR_REVIEW', next_page_after: null,
                    items: [{ page_number: 4, text_content: 'Applicants must provide current financial evidence.', content_hash: 'b'.repeat(64) }],
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Handbook Intake' }).click();
        await page.getByRole('button', { name: 'Review support-handbook.pdf' }).click();
        await expect(page.getByRole('heading', { name: 'Source review' })).toBeVisible();
        await expect(page.locator('pre').filter({ hasText: 'Applicants must provide current financial evidence.' })).toBeVisible();
        await expect(page.getByText('support-handbook.pdf, page 4')).toBeVisible();
    });

    test('requires staff acceptance before OCR text becomes a handbook page', async ({ page }) => {
        await page.route('**/api/v1/admin/domains', async route => {
            await route.fulfill({ json: { items: [{ domain_id: 'dom_1', domain_name: 'Student Support Eligibility' }] } });
        });
        await page.route('**/api/v1/governance/handbooks', async route => {
            await route.fulfill({
                json: {
                    items: [{
                        handbook_id: 'handbook_ocr', domain_id: 'dom_1', file_name: 'scanned-handbook.pdf', file_size_bytes: 2048,
                        content_hash: 'a'.repeat(64), status: 'OCR_REVIEW_REQUIRED', total_pages: 1, processed_pages: 1,
                    }],
                },
            });
        });
        await page.route('**/api/v1/governance/handbooks/handbook_ocr/pages*', async route => {
            await route.fulfill({
                json: {
                    handbook_id: 'handbook_ocr', file_name: 'scanned-handbook.pdf', status: 'OCR_REVIEW_REQUIRED', next_page_after: null,
                    items: [{ page_number: 1, text_content: '', content_hash: 'b'.repeat(64) }],
                },
            });
        });
        await page.route('**/api/v1/governance/handbooks/handbook_ocr/ocr-reviews', async route => {
            await route.fulfill({
                json: {
                    items: [{
                        ocr_review_id: 'ocr_1', page_number: 1, provider_name: 'institution_ocr', provider_reference: 'job-1/page-1',
                        proposed_text: 'Applicants must provide current financial evidence.', proposed_text_hash: 'c'.repeat(64), status: 'PENDING_REVIEW',
                    }],
                },
            });
        });
        await page.route('**/api/v1/governance/handbooks/handbook_ocr/ocr-reviews/1', async route => {
            expect(route.request().method()).toBe('PATCH');
            expect(route.request().postDataJSON()).toEqual({ action: 'ACCEPT', reviewed_text: 'Applicants must provide current financial evidence.' });
            await route.fulfill({
                json: {
                    ocr_review_id: 'ocr_1', page_number: 1, provider_name: 'institution_ocr', provider_reference: 'job-1/page-1',
                    proposed_text: 'Applicants must provide current financial evidence.', proposed_text_hash: 'c'.repeat(64), status: 'ACCEPTED',
                    reviewed_text: 'Applicants must provide current financial evidence.', reviewed_by: 'author_1',
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Handbook Intake' }).click();
        await page.getByRole('button', { name: 'Review scanned-handbook.pdf' }).click();
        await expect(page.getByLabel('Reviewed OCR text for page 1')).toHaveValue('Applicants must provide current financial evidence.');
        await page.getByRole('button', { name: 'Accept OCR text for page 1' }).click();
        await expect(page.locator('pre').filter({ hasText: 'Applicants must provide current financial evidence.' })).toBeVisible();
    });

    test('lets a release approver review and publish a guided policy draft', async ({ page }) => {
        await page.route('**/api/v1/governance/drafts', async route => {
            await route.fulfill({
                json: { items: [{ draft_id: 'draft_1', domain_id: 'dom_1', domain_name: 'Student Support Eligibility', policy_name: 'Student Support Policy', author_id: 'author_1' }] },
            });
        });
        await page.route('**/api/v1/governance/drafts/draft_1/review', async route => {
            await route.fulfill({
                json: {
                    draft_id: 'draft_1', domain_id: 'dom_1', domain_name: 'Student Support Eligibility', policy_name: 'Student Support Policy', author_id: 'author_1',
                    policy: { kind: 'rule', label: 'Income is within the support threshold', fact_label: 'Annual household income', operator: 'is at most', expected_value: 350000, citation: 'Support Policy 2026, section 2.1' },
                },
            });
        });
        await page.route('**/api/v1/governance/releases', async route => {
            expect(route.request().postDataJSON()).toEqual({ draft_id: 'draft_1', version: '2026.1', effective_from: '2026-01-01', applicability: [] });
            await route.fulfill({ json: { release_id: 'rel_1', domain_id: 'dom_1', version: '2026.1', rule_graph_id: 'rg_1', effective_from: '2026-01-01', applicability: {}, approved_by: 'approver_1', authored_by: 'author_1' } });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Policy Review' }).focus();
        await page.keyboard.press('Enter');
        await page.getByRole('button', { name: /Student Support Policy/ }).click();
        await expect(page.getByText('Annual household income')).toBeVisible();
        await page.getByLabel('Release version').fill('2026.1');
        await page.getByLabel('Effective from').fill('2026-01-01');
        await page.getByRole('button', { name: 'Approve and publish' }).click();
        await expect(page.getByText('Published as immutable release 2026.1.')).toBeVisible();
    });

    test('records and resolves a policy ambiguity without exposing implementation data', async ({ page }) => {
        await page.route('**/api/v1/admin/domains', async route => {
            await route.fulfill({ json: { items: [{ domain_id: 'dom_policy', domain_name: 'Student Support Eligibility' }] } });
        });
        await page.route('**/api/v1/governance/policy-ambiguities*', async route => {
            if (route.request().method() === 'GET') {
                await route.fulfill({ json: { items: [] } });
                return;
            }
            expect(route.request().postDataJSON()).toEqual({
                domain_id: 'dom_policy',
                source_citation: 'Support Policy 2026, section 5.4',
                question: 'Does the transitional threshold apply to returning applicants?',
                interpretation_options: ['Apply threshold', 'Do not apply threshold'],
            });
            await route.fulfill({
                status: 201,
                json: {
                    ambiguity_id: 'amb_1', domain_id: 'dom_policy', source_citation: 'Support Policy 2026, section 5.4',
                    question: 'Does the transitional threshold apply to returning applicants?',
                    interpretation_options: ['Apply threshold', 'Do not apply threshold'], status: 'OPEN', created_by: 'author_1',
                },
            });
        });
        await page.route('**/api/v1/governance/policy-ambiguities/amb_1/resolve', async route => {
            expect(route.request().postDataJSON()).toEqual({
                domain_id: 'dom_policy',
                resolution: 'Apply the threshold to all returning applicants.',
                source_reference: 'Senate resolution 2026/14',
            });
            await route.fulfill({
                json: {
                    ambiguity_id: 'amb_1', domain_id: 'dom_policy', source_citation: 'Support Policy 2026, section 5.4',
                    question: 'Does the transitional threshold apply to returning applicants?',
                    interpretation_options: ['Apply threshold', 'Do not apply threshold'], status: 'RESOLVED', created_by: 'author_1',
                    resolution: 'Apply the threshold to all returning applicants.', resolution_source_reference: 'Senate resolution 2026/14',
                },
            });
        });

        await openApplication(page);
        await page.getByRole('button', { name: 'Policy Register' }).click();
        await page.getByLabel('Ambiguity source citation').fill('Support Policy 2026, section 5.4');
        await page.getByLabel('Interpretation question').fill('Does the transitional threshold apply to returning applicants?');
        await page.getByLabel('Interpretation option 1').fill('Apply threshold');
        await page.getByLabel('Interpretation option 2').fill('Do not apply threshold');
        await page.getByRole('button', { name: 'Record ambiguity' }).click();
        await expect(page.getByText('Does the transitional threshold apply to returning applicants?')).toBeVisible();
        await page.getByRole('button', { name: 'Record interpretation' }).click();
        await page.getByLabel('Resolution for ambiguity amb_1').fill('Apply the threshold to all returning applicants.');
        await page.getByLabel('Resolution source for ambiguity amb_1').fill('Senate resolution 2026/14');
        await page.getByRole('button', { name: 'Record interpretation' }).last().click();
        await expect(page.getByText('Resolved')).toBeVisible();
    });
});
