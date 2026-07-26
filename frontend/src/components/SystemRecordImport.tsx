import { type FormEvent, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileSpreadsheet, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import {
  fetchAdminDomains,
  fetchRecordImportFields,
  previewSystemRecordImport,
  type AdminDomain,
  type RecordImportField,
  type SystemRecordImportContract,
  type SystemRecordImportFieldMapping,
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
  const [error, setError] = useState<string | null>(null);
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
      return;
    }
    void (async () => {
      setLoading(true);
      setError(null);
      setPreview(null);
      try {
        const loadedFields = await fetchRecordImportFields(domainId);
        setFields(loadedFields);
        setMappings(loadedFields[0] ? [newMapping(loadedFields[0])] : []);
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

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file || !domainId) return;
    setPreviewing(true);
    setError(null);
    setPreview(null);
    const contract: SystemRecordImportContract = {
      mapping_id: mappingId.trim(),
      source_system: sourceSystem.trim(),
      subject_identifier_column: subjectColumn.trim(),
      source_record_version_column: versionColumn.trim(),
      ...(asOfColumn.trim() ? { source_as_of_date_column: asOfColumn.trim() } : {}),
      fields: mappings.map((mapping) => ({ ...mapping, source_column: mapping.source_column.trim() })),
    };
    try {
      setPreview(await previewSystemRecordImport(domainId, contract, file));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setPreviewing(false);
    }
  };

  const readyToPreview = Boolean(
    domainId
    && file
    && mappingId.trim().length >= 3
    && sourceSystem.trim().length >= 2
    && subjectColumn.trim()
    && versionColumn.trim()
    && mappings.length > 0
    && mappings.every((mapping) => mapping.source_column.trim() && mapping.target_path),
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
      {loading && <p className="flex items-center gap-2 py-6 text-sm text-muted"><LoaderCircle className="h-4 w-4 animate-spin" />Loading import fields...</p>}

      {!loading && (
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

          <button type="submit" disabled={!readyToPreview || previewing} className="inline-flex w-fit items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
            {previewing && <LoaderCircle className="h-4 w-4 animate-spin" />}
            {previewing ? 'Checking export...' : 'Check export'}
          </button>
        </form>
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
