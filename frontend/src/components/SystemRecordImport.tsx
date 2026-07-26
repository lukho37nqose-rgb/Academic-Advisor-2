import { type FormEvent, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileSpreadsheet, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import {
  approveSystemRecordImportMapping,
  fetchAdminDomains,
  fetchRecordImportFields,
  fetchSystemRecordImportMappings,
  previewSystemRecordImport,
  rejectSystemRecordImportMapping,
  submitSystemRecordImportMapping,
  type AdminDomain,
  type RecordImportField,
  type SystemRecordImportContract,
  type SystemRecordImportFieldMapping,
  type SystemRecordImportMapping,
  type SystemRecordImportPreview,
} from '../api/client';

type ValueType = SystemRecordImportFieldMapping['value_type'];

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'The CSV export could not be checked.';
}

function valueTypeForField(field?: RecordImportField): ValueType {
  if (field?.schema_type === 'boolean') return 'boolean';
  if (field?.schema_type === 'number') return 'number';
  return 'text';
}

function newMapping(field?: RecordImportField): SystemRecordImportFieldMapping {
  return {
    source_column: '',
    target_path: field?.target_path || '',
    value_type: valueTypeForField(field),
    required: true,
  };
}

export function SystemRecordImport() {
  const [domains, setDomains] = useState<AdminDomain[]>([]);
  const [domainId, setDomainId] = useState('');
  const [fields, setFields] = useState<RecordImportField[]>([]);
  const [mappingId, setMappingId] = useState('');
  const [sourceSystem, setSourceSystem] = useState('');
  const [subjectColumn, setSubjectColumn] = useState('');
  const [versionColumn, setVersionColumn] = useState('');
  const [asOfColumn, setAsOfColumn] = useState('');
  const [mappings, setMappings] = useState<SystemRecordImportFieldMapping[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [savingMapping, setSavingMapping] = useState(false);
  const [reviewingMappingId, setReviewingMappingId] = useState<string | null>(null);
  const [savedMappings, setSavedMappings] = useState<SystemRecordImportMapping[]>([]);
  const [canSubmitMapping, setCanSubmitMapping] = useState(false);
  const [canReviewMapping, setCanReviewMapping] = useState(false);
  const [rejectionReasons, setRejectionReasons] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [preview, setPreview] = useState<SystemRecordImportPreview | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const loadedDomains = await fetchAdminDomains();
        setDomains(loadedDomains);
        setDomainId(loadedDomains[0]?.domain_id || '');
      } catch (requestError) {
        setError(errorMessage(requestError));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!domainId) {
      setFields([]);
      setMappings([]);
      setSavedMappings([]);
      return;
    }
    void (async () => {
      setLoading(true);
      setError(null);
      setNotice(null);
      setPreview(null);
      try {
        const mappingList = await fetchSystemRecordImportMappings(domainId);
        setSavedMappings(mappingList.items);
        setCanSubmitMapping(mappingList.can_submit);
        setCanReviewMapping(mappingList.can_review);
        if (mappingList.can_submit) {
          const loadedFields = await fetchRecordImportFields(domainId);
          setFields(loadedFields);
          setMappings(loadedFields[0] ? [newMapping(loadedFields[0])] : []);
        } else {
          setFields([]);
          setMappings([]);
        }
      } catch (requestError) {
        setError(errorMessage(requestError));
      } finally {
        setLoading(false);
      }
    })();
  }, [domainId]);

  const updateMapping = (index: number, patch: Partial<SystemRecordImportFieldMapping>) => {
    setMappings((current) => current.map((mapping, mappingIndex) => (
      mappingIndex === index ? { ...mapping, ...patch } : mapping
    )));
  };

  const changeTarget = (index: number, targetPath: string) => {
    const field = fields.find((item) => item.target_path === targetPath);
    updateMapping(index, { target_path: targetPath, value_type: valueTypeForField(field) });
  };

  const buildContract = (): SystemRecordImportContract => ({
    mapping_id: mappingId.trim(),
    source_system: sourceSystem.trim(),
    subject_identifier_column: subjectColumn.trim(),
    source_record_version_column: versionColumn.trim(),
    ...(asOfColumn.trim() ? { source_as_of_date_column: asOfColumn.trim() } : {}),
    fields: mappings.map((mapping) => ({ ...mapping, source_column: mapping.source_column.trim() })),
  });

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file || !domainId) return;
    setPreviewing(true);
    setError(null);
    setNotice(null);
    setPreview(null);
    try {
      setPreview(await previewSystemRecordImport(domainId, buildContract(), file));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setPreviewing(false);
    }
  };

  const submitMappingForReview = async () => {
    if (!domainId || !readyToConfigure) return;
    setSavingMapping(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await submitSystemRecordImportMapping(domainId, buildContract());
      setSavedMappings((current) => [saved, ...current]);
      setNotice(`Mapping ${saved.mapping_name} was submitted for independent review.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSavingMapping(false);
    }
  };

  const replaceSavedMapping = (updated: SystemRecordImportMapping) => {
    setSavedMappings((current) => current.map((mapping) => (
      mapping.mapping_id === updated.mapping_id ? updated : mapping
    )));
  };

  const approveMapping = async (saved: SystemRecordImportMapping) => {
    setReviewingMappingId(saved.mapping_id);
    setError(null);
    setNotice(null);
    try {
      replaceSavedMapping(await approveSystemRecordImportMapping(saved.mapping_id, domainId));
      setNotice(`Mapping ${saved.mapping_name} was approved.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setReviewingMappingId(null);
    }
  };

  const rejectMapping = async (saved: SystemRecordImportMapping) => {
    const reason = rejectionReasons[saved.mapping_id]?.trim() || '';
    if (!reason) {
      setError('A rejection reason is required.');
      return;
    }
    setReviewingMappingId(saved.mapping_id);
    setError(null);
    setNotice(null);
    try {
      replaceSavedMapping(await rejectSystemRecordImportMapping(saved.mapping_id, domainId, reason));
      setNotice(`Mapping ${saved.mapping_name} was returned with a review note.`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setReviewingMappingId(null);
    }
  };

  const loadSavedMapping = (saved: SystemRecordImportMapping) => {
    const contract = saved.contract;
    setMappingId(contract.mapping_id);
    setSourceSystem(contract.source_system);
    setSubjectColumn(contract.subject_identifier_column);
    setVersionColumn(contract.source_record_version_column);
    setAsOfColumn(contract.source_as_of_date_column || '');
    setMappings(contract.fields);
    setPreview(null);
    setNotice(`Loaded ${saved.mapping_name} into the export check form.`);
  };

  const readyToConfigure = Boolean(
    domainId
    && mappingId.trim().length >= 3
    && sourceSystem.trim().length >= 2
    && subjectColumn.trim()
    && versionColumn.trim()
    && mappings.length > 0
    && mappings.every((mapping) => mapping.source_column.trim() && mapping.target_path),
  );

  const readyToPreview = Boolean(
    readyToConfigure
    && file
  );

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 py-4">
      <section className="border-b border-border pb-5">
        <div className="flex items-center gap-3">
          <FileSpreadsheet className="h-5 w-5 text-muted" />
          <div>
            <h2 className="text-2xl font-semibold">System record import</h2>
            <p className="mt-1 text-sm text-muted">Check a CSV export before any evidence import</p>
          </div>
        </div>
      </section>

      {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {notice && <div role="status" className="flex items-start gap-2 border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />{notice}</div>}
      {loading && <p className="flex items-center gap-2 py-6 text-sm text-muted"><LoaderCircle className="h-4 w-4 animate-spin" />Loading import fields...</p>}

      {!loading && canSubmitMapping && (
        <form onSubmit={submit} className="grid gap-7">
          <section className="grid gap-4 border-b border-border pb-6 sm:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium">
              Decision domain
              <select value={domainId} onChange={(event) => setDomainId(event.target.value)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">
                {domains.length === 0 && <option value="">No assigned domains</option>}
                {domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium">
              CSV export
              <input aria-label="CSV export" type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} className="rounded border border-border px-3 py-2 text-sm file:mr-3 file:border-0 file:bg-accent file:px-2 file:py-1 file:text-sm file:font-medium" />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Mapping name
              <input value={mappingId} onChange={(event) => setMappingId(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Source system
              <input value={sourceSystem} onChange={(event) => setSourceSystem(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Subject identifier column
              <input value={subjectColumn} onChange={(event) => setSubjectColumn(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Source record version column
              <input value={versionColumn} onChange={(event) => setVersionColumn(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
            </label>
            <label className="grid gap-2 text-sm font-medium sm:col-span-2">
              Source as-of date column <span className="font-normal text-muted">Optional</span>
              <input value={asOfColumn} onChange={(event) => setAsOfColumn(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
            </label>
          </section>

          <section className="grid gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-base font-semibold">Columns to use in this decision</h3>
              <button type="button" onClick={() => setMappings((current) => [...current, newMapping(fields[0])])} disabled={fields.length === 0} className="inline-flex items-center gap-2 rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40">
                <Plus className="h-4 w-4" />
                Add column
              </button>
            </div>
            {fields.length === 0 && <p className="text-sm text-muted">This domain has no declared facts available for an import mapping.</p>}
            <div className="grid gap-4">
              {mappings.map((mapping, index) => (
                <div key={`${mapping.target_path}-${index}`} className="grid gap-3 border-b border-border pb-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_160px_auto_36px] md:items-end">
                  <label className="grid gap-2 text-sm font-medium">
                    Export column name
                    <input value={mapping.source_column} onChange={(event) => updateMapping(index, { source_column: event.target.value })} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
                  </label>
                  <label className="grid gap-2 text-sm font-medium">
                    Decision fact
                    <select value={mapping.target_path} onChange={(event) => changeTarget(index, event.target.value)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">
                      {fields.map((field) => <option key={field.target_path} value={field.target_path}>{field.label}</option>)}
                    </select>
                  </label>
                  <label className="grid gap-2 text-sm font-medium">
                    Value type
                    <select value={mapping.value_type} onChange={(event) => updateMapping(index, { value_type: event.target.value as ValueType })} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">
                      <option value="text">Text</option>
                      <option value="integer">Whole number</option>
                      <option value="number">Number</option>
                      <option value="boolean">Yes or no</option>
                      <option value="date">Date</option>
                    </select>
                  </label>
                  <label className="flex items-center gap-2 pb-2 text-sm font-medium">
                    <input type="checkbox" checked={mapping.required} onChange={(event) => updateMapping(index, { required: event.target.checked })} className="h-4 w-4" />
                    Required
                  </label>
                  <button type="button" title="Remove column" aria-label="Remove column" disabled={mappings.length === 1} onClick={() => setMappings((current) => current.filter((_, mappingIndex) => mappingIndex !== index))} className="inline-flex h-9 w-9 items-center justify-center rounded border border-border text-muted hover:bg-accent disabled:opacity-40">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </section>

          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => void submitMappingForReview()} disabled={!readyToConfigure || savingMapping} className="inline-flex w-fit items-center gap-2 rounded border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40">
              {savingMapping && <LoaderCircle className="h-4 w-4 animate-spin" />}
              {savingMapping ? 'Submitting...' : 'Submit mapping for review'}
            </button>
            <button type="submit" disabled={!readyToPreview || previewing} className="inline-flex w-fit items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
              {previewing && <LoaderCircle className="h-4 w-4 animate-spin" />}
              {previewing ? 'Checking export...' : 'Check export'}
            </button>
          </div>
        </form>
      )}

      {!loading && (
        <section aria-labelledby="saved-mappings-heading" className="grid gap-4 border-t border-border pt-6">
          <div>
            <h3 id="saved-mappings-heading" className="text-base font-semibold">Saved mapping configurations</h3>
            <p className="mt-1 text-sm text-muted">Configurations are retained for review. CSV exports and subject values are not retained here.</p>
          </div>
          {savedMappings.length === 0 && <p className="text-sm text-muted">No mapping configurations have been submitted for this domain.</p>}
          {savedMappings.map((saved) => (
            <article key={saved.mapping_id} className="grid gap-4 border border-border p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold">{saved.mapping_name}</h4>
                  <p className="mt-1 text-sm text-muted">{saved.source_system}</p>
                </div>
                <span className={`border px-2 py-1 text-xs font-medium ${saved.status === 'APPROVED' ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : saved.status === 'REJECTED' ? 'border-rose-200 bg-rose-50 text-rose-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>{saved.status}</span>
              </div>
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div><dt className="text-xs font-medium uppercase text-muted">Subject column</dt><dd className="mt-1">{saved.contract.subject_identifier_column}</dd></div>
                <div><dt className="text-xs font-medium uppercase text-muted">Version column</dt><dd className="mt-1">{saved.contract.source_record_version_column}</dd></div>
                <div className="sm:col-span-2"><dt className="text-xs font-medium uppercase text-muted">Decision facts</dt><dd className="mt-1">{saved.contract.fields.map((field) => `${field.source_column} to ${field.target_path}`).join(', ')}</dd></div>
              </dl>
              {saved.review_note && <p className="border-l-2 border-border pl-3 text-sm text-muted">Review note: {saved.review_note}</p>}
              <div className="flex flex-wrap gap-3">
                {canSubmitMapping && <button type="button" onClick={() => loadSavedMapping(saved)} className="rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent">Use configuration</button>}
                {canReviewMapping && saved.status === 'PENDING' && (
                  <button type="button" onClick={() => void approveMapping(saved)} disabled={reviewingMappingId === saved.mapping_id} className="inline-flex items-center gap-2 rounded bg-primary px-3 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
                    {reviewingMappingId === saved.mapping_id && <LoaderCircle className="h-4 w-4 animate-spin" />}
                    Approve mapping
                  </button>
                )}
              </div>
              {canReviewMapping && saved.status === 'PENDING' && (
                <div className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
                  <label className="grid min-w-64 flex-1 gap-2 text-sm font-medium">
                    Rejection reason
                    <input value={rejectionReasons[saved.mapping_id] || ''} onChange={(event) => setRejectionReasons((current) => ({ ...current, [saved.mapping_id]: event.target.value }))} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
                  </label>
                  <button type="button" onClick={() => void rejectMapping(saved)} disabled={reviewingMappingId === saved.mapping_id} className="rounded border border-rose-300 px-3 py-2 text-sm font-medium text-rose-800 hover:bg-rose-50 disabled:opacity-40">Reject mapping</button>
                </div>
              )}
            </article>
          ))}
        </section>
      )}

      {preview && (
        <section aria-labelledby="preview-heading" className={`border-t border-border pt-6 ${preview.issues.length === 0 ? '' : 'text-rose-800'}`}>
          <div className="flex items-center gap-2">
            {preview.issues.length === 0 && <CheckCircle2 className="h-5 w-5 text-emerald-600" />}
            <h3 id="preview-heading" className="text-base font-semibold">Export check</h3>
          </div>
          <dl className="mt-4 grid gap-4 sm:grid-cols-3">
            <div><dt className="text-xs font-medium uppercase text-muted">Rows checked</dt><dd className="mt-1 text-sm font-medium">{preview.row_count}</dd></div>
            <div><dt className="text-xs font-medium uppercase text-muted">Records accepted</dt><dd className="mt-1 text-sm font-medium">{preview.accepted_record_count}</dd></div>
            <div><dt className="text-xs font-medium uppercase text-muted">Rows rejected</dt><dd className="mt-1 text-sm font-medium">{preview.rejected_row_count}</dd></div>
          </dl>
          {preview.ignored_columns.length > 0 && <p className="mt-4 text-sm text-muted">Ignored columns: {preview.ignored_columns.join(', ')}.</p>}
          {preview.issues.length > 0 && <ul className="mt-4 grid gap-2 text-sm">{preview.issues.map((issue, index) => <li key={`${issue.code}-${index}`} className="border-l-2 border-rose-300 pl-3">{issue.row_number ? `Row ${issue.row_number}: ` : ''}{issue.message}</li>)}</ul>}
        </section>
      )}
    </div>
  );
}
