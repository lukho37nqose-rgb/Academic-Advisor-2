import { type FormEvent, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileSpreadsheet, LoaderCircle, Plus, Trash2 } from 'lucide-react';
import {
  approveSystemRecordImportMapping,
  fetchAdminDomains,
  fetchRecordImportFields,
  fetchSystemRecordImportMappings,
  fetchInstitutionalDataSources,
  submitInstitutionalDataSource,
  approveInstitutionalDataSource,
  materializeSystemRecordImport,
  previewSystemRecordImport,
  rejectSystemRecordImportMapping,
  submitSystemRecordImportMapping,
  type AdminDomain,
  type RecordImportField,
  type SystemRecordImportContract,
  type SystemRecordImportFieldMapping,
  type SystemRecordImportMapping,
  type SystemRecordImportPreview,
  type InstitutionalDataSource,
} from '../api/client';

type ValueType = SystemRecordImportFieldMapping['value_type'];

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'The source record file could not be checked.';
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
  const [dataSources, setDataSources] = useState<InstitutionalDataSource[]>([]);
  const [sourceId, setSourceId] = useState('');
  const [newSourceName, setNewSourceName] = useState('');
  const [newSourceOwner, setNewSourceOwner] = useState('');
  const [newSourceKind, setNewSourceKind] = useState<InstitutionalDataSource['source_kind']>('SYSTEM_OF_RECORD');
  const [newSourceAuthority, setNewSourceAuthority] = useState<InstitutionalDataSource['authority_level']>('AUTHORITATIVE');
  const [newSourceRefreshHours, setNewSourceRefreshHours] = useState('24');
  const [newConnectorKind, setNewConnectorKind] = useState<NonNullable<InstitutionalDataSource['connector_kind']>>('NONE');
  const [newCredentialReference, setNewCredentialReference] = useState('');
  const [newEndpointReference, setNewEndpointReference] = useState('');
  const [newAllowedObject, setNewAllowedObject] = useState('');
  const [subjectColumn, setSubjectColumn] = useState('');
  const [versionColumn, setVersionColumn] = useState('');
  const [asOfColumn, setAsOfColumn] = useState('');
  const [recordState, setRecordState] = useState<'confirmed' | 'provisional'>('confirmed');
  const [mappings, setMappings] = useState<SystemRecordImportFieldMapping[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [savingMapping, setSavingMapping] = useState(false);
  const [reviewingMappingId, setReviewingMappingId] = useState<string | null>(null);
  const [savedMappings, setSavedMappings] = useState<SystemRecordImportMapping[]>([]);
  const [canSubmitMapping, setCanSubmitMapping] = useState(false);
  const [canReviewMapping, setCanReviewMapping] = useState(false);
  const [canMaterialize, setCanMaterialize] = useState(false);
  const [approvedFiles, setApprovedFiles] = useState<Record<string, File | null>>({});
  const [materializingMappingId, setMaterializingMappingId] = useState<string | null>(null);
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
        const loadedSources = await fetchInstitutionalDataSources(domainId);
        setDataSources(loadedSources);
        setSavedMappings(mappingList.items);
        setCanSubmitMapping(mappingList.can_submit);
        setCanReviewMapping(mappingList.can_review);
        setCanMaterialize(Boolean(mappingList.can_materialize));
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
    source_id: sourceId || undefined,
    source_system: sourceSystem.trim(),
    subject_identifier_column: subjectColumn.trim(),
    source_record_version_column: versionColumn.trim(),
    ...(asOfColumn.trim() ? { source_as_of_date_column: asOfColumn.trim() } : {}),
    record_state: recordState,
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
    setSourceId(contract.source_id || '');
    setSourceSystem(contract.source_system);
    setSubjectColumn(contract.subject_identifier_column);
    setVersionColumn(contract.source_record_version_column);
    setAsOfColumn(contract.source_as_of_date_column || '');
    setRecordState(contract.record_state || 'confirmed');
    setMappings(contract.fields);
    setPreview(null);
    setNotice(`Loaded ${saved.mapping_name} into the export check form.`);
  };

  const materializeApprovedExport = async (saved: SystemRecordImportMapping) => {
    const selectedFile = approvedFiles[saved.mapping_id];
    if (!selectedFile) {
      setError('Choose the approved source record file to import.');
      return;
    }
    setMaterializingMappingId(saved.mapping_id);
    setError(null);
    setNotice(null);
    try {
      const result = await materializeSystemRecordImport(domainId, saved.mapping_id, selectedFile);
      setNotice(`${result.evidence_created} record${result.evidence_created === 1 ? '' : 's'} imported. ${result.already_imported ? `${result.already_imported} already imported. ` : ''}${result.fact_acceptance}`);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setMaterializingMappingId(null);
    }
  };

  const readyToConfigure = Boolean(
    domainId
    && mappingId.trim().length >= 3
    && sourceId.length > 0
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

  const registerSource = async () => {
    if (!domainId || !newSourceName.trim() || !newSourceOwner.trim()) return;
    setError(null); setNotice(null);
    try {
      const connectorPayload = newConnectorKind === 'NONE' ? {} : {
        connector_kind: newConnectorKind,
        credential_reference: newCredentialReference.trim(),
        endpoint_reference: newEndpointReference.trim(),
        allowed_object: newAllowedObject.trim(),
      };
      const source = await submitInstitutionalDataSource({ domain_id: domainId, display_name: newSourceName.trim(), source_owner: newSourceOwner.trim(), source_kind: newSourceKind, authority_level: newSourceAuthority, expected_refresh_hours: Number(newSourceRefreshHours) || undefined, ...connectorPayload });
      setDataSources((current) => [source, ...current]);
      setNewSourceName(''); setNewSourceOwner(''); setNewConnectorKind('NONE'); setNewCredentialReference(''); setNewEndpointReference(''); setNewAllowedObject('');
      setNotice(`${source.display_name} was submitted for independent source approval.`);
    } catch (requestError) { setError(errorMessage(requestError)); }
  };

  const sourceRegistrationReady = Boolean(
    newSourceName.trim()
    && newSourceOwner.trim()
    && (
      newConnectorKind === 'NONE'
      || (newCredentialReference.trim() && newEndpointReference.trim() && newAllowedObject.trim())
    )
  );

  const approveSource = async (source: InstitutionalDataSource) => {
    setError(null); setNotice(null);
    try {
      const approved = await approveInstitutionalDataSource(source.source_id, domainId);
      setDataSources((current) => current.map((item) => item.source_id === approved.source_id ? approved : item));
      setNotice(`${approved.display_name} was approved as an institutional data source.`);
    } catch (requestError) { setError(errorMessage(requestError)); }
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 py-4">
      <section className="border-b border-border pb-5">
        <div className="flex items-center gap-3">
          <FileSpreadsheet className="h-5 w-5 text-muted" />
          <div>
            <h2 className="text-2xl font-semibold">System record intake</h2>
            <p className="mt-1 text-sm text-muted">Prepare governed source records before they become evidence</p>
          </div>
        </div>
      </section>

      {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-3 text-sm text-rose-800"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {notice && <div role="status" className="flex items-start gap-2 border border-emerald-200 bg-emerald-50 px-3 py-3 text-sm text-emerald-800"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />{notice}</div>}
      {loading && <p className="flex items-center gap-2 py-6 text-sm text-muted"><LoaderCircle className="h-4 w-4 animate-spin" />Loading import fields...</p>}

      {!loading && !canSubmitMapping && canReviewMapping && (
        <section className="grid gap-3 border-b border-border pb-6">
          <div><h3 className="text-base font-semibold">Sources awaiting approval</h3><p className="mt-1 text-sm text-muted">Confirm the source owner and whether it may provide confirmed or provisional information.</p></div>
          {dataSources.filter((source) => source.status === 'PENDING').length === 0 ? <p className="text-sm text-muted">There are no source declarations awaiting your review.</p> : dataSources.filter((source) => source.status === 'PENDING').map((source) => <div key={source.source_id} className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-2 text-sm"><span><span className="font-medium">{source.display_name}</span><span className="ml-2 text-muted">{source.authority_level.toLowerCase()} · {source.source_owner}</span></span><button type="button" onClick={() => void approveSource(source)} className="rounded border border-border px-2 py-1 font-medium hover:bg-accent">Approve source</button></div>)}
        </section>
      )}

      {!loading && canSubmitMapping && (
        <form onSubmit={submit} className="grid gap-7">
          <section className="grid gap-4 border-b border-border pb-6">
            <div><h3 className="text-base font-semibold">Institutional data sources</h3><p className="mt-1 text-sm text-muted">Declare what a source is allowed to mean before its records can inform a decision.</p></div>
            <div className="grid gap-3 sm:grid-cols-6">
              <input aria-label="Data source name" value={newSourceName} onChange={(event) => setNewSourceName(event.target.value)} placeholder="Authoritative system records" className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary" />
              <input aria-label="Data source owner" value={newSourceOwner} onChange={(event) => setNewSourceOwner(event.target.value)} placeholder="Registrar" className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary" />
              <select aria-label="Data source kind" value={newSourceKind} onChange={(event) => setNewSourceKind(event.target.value as InstitutionalDataSource['source_kind'])} className="rounded border border-border bg-white px-3 py-2 text-sm"><option value="SYSTEM_OF_RECORD">System of record</option><option value="LEARNING_PLATFORM">Learning platform</option><option value="DEPARTMENT_RECORD">Department record</option><option value="COMMITTEE_REGISTER">Committee register</option><option value="MANUAL">Verified manual record</option></select>
              <select aria-label="Data source authority" value={newSourceAuthority} onChange={(event) => setNewSourceAuthority(event.target.value as InstitutionalDataSource['authority_level'])} className="rounded border border-border bg-white px-3 py-2 text-sm"><option value="AUTHORITATIVE">Authoritative</option><option value="WORKING">Working / provisional</option><option value="REFERENCE">Reference only</option></select>
              <input aria-label="Expected source refresh hours" type="number" min="1" value={newSourceRefreshHours} onChange={(event) => setNewSourceRefreshHours(event.target.value)} className="rounded border border-border px-3 py-2 text-sm" />
              <button type="button" onClick={() => void registerSource()} disabled={!sourceRegistrationReady} className="rounded border border-border px-3 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40">Register source</button>
            </div>
            <div className="grid gap-3 border-l-2 border-border pl-4">
              <label className="grid gap-2 text-sm font-medium">
                Read-only connector
                <select value={newConnectorKind} onChange={(event) => setNewConnectorKind(event.target.value as NonNullable<InstitutionalDataSource['connector_kind']>)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">
                  <option value="NONE">File fallback for validation</option>
                  <option value="REST_API">REST API</option>
                  <option value="SFTP_PULL">Managed SFTP pull</option>
                  <option value="DATABASE_VIEW">Read-only database view</option>
                  <option value="VENDOR_API">Vendor API</option>
                </select>
              </label>
              {newConnectorKind !== 'NONE' && <div className="grid gap-3 sm:grid-cols-3">
                <input aria-label="Credential reference" value={newCredentialReference} onChange={(event) => setNewCredentialReference(event.target.value)} placeholder="Secrets Manager reference" className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary" />
                <input aria-label="Endpoint reference" value={newEndpointReference} onChange={(event) => setNewEndpointReference(event.target.value)} placeholder="Approved endpoint reference" className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary" />
                <input aria-label="Allowed source object" value={newAllowedObject} onChange={(event) => setNewAllowedObject(event.target.value)} placeholder="API scope, path, table, or view" className="rounded border border-border px-3 py-2 text-sm outline-none focus:border-primary" />
              </div>}
            </div>
            {dataSources.length > 0 && <div className="grid gap-2 text-sm">{dataSources.map((source) => <div key={source.source_id} className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-2"><span><span className="font-medium">{source.display_name}</span><span className="ml-2 text-muted">{source.authority_level.toLowerCase()} · {source.source_owner} · {source.status.toLowerCase()}</span></span>{canReviewMapping && source.status === 'PENDING' && <button type="button" onClick={() => void approveSource(source)} className="rounded border border-border px-2 py-1 text-sm font-medium hover:bg-accent">Approve source</button>}</div>)}</div>}
          </section>
          <section className="grid gap-4 border-b border-border pb-6 sm:grid-cols-2">
            <label className="grid gap-2 text-sm font-medium">
              Decision domain
              <select value={domainId} onChange={(event) => setDomainId(event.target.value)} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">
                {domains.length === 0 && <option value="">No assigned domains</option>}
                {domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}
              </select>
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Source record file
              <input aria-label="Source record file" type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} className="rounded border border-border px-3 py-2 text-sm file:mr-3 file:border-0 file:bg-accent file:px-2 file:py-1 file:text-sm file:font-medium" />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Mapping name
              <input value={mappingId} onChange={(event) => setMappingId(event.target.value)} className="rounded border border-border px-3 py-2 font-normal outline-none focus:border-primary" />
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Approved institutional data source
              <select value={sourceId} onChange={(event) => {
                const selected = dataSources.find((source) => source.source_id === event.target.value);
                setSourceId(event.target.value);
                if (selected) {
                  setSourceSystem(selected.display_name);
                  setRecordState(selected.authority_level === 'AUTHORITATIVE' ? 'confirmed' : 'provisional');
                }
              }} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">
                <option value="">Choose an approved source</option>
                {dataSources.filter((source) => source.status === 'APPROVED' && source.authority_level !== 'REFERENCE').map((source) => <option key={source.source_id} value={source.source_id}>{source.display_name} ({source.authority_level === 'AUTHORITATIVE' ? 'confirmed' : 'provisional'})</option>)}
              </select>
              {dataSources.filter((source) => source.status === 'APPROVED' && source.authority_level !== 'REFERENCE').length === 0 && <span className="font-normal text-amber-700">No approved source is available for this domain. Register and approve one before mapping an export.</span>}
            </label>
            <label className="grid gap-2 text-sm font-medium">
              Source system
              <input value={sourceSystem} readOnly aria-readonly="true" className="rounded border border-border bg-accent px-3 py-2 font-normal text-muted" />
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
            <label className="grid gap-2 text-sm font-medium sm:col-span-2">
              Record status when imported
              <select value={recordState} onChange={(event) => setRecordState(event.target.value as 'confirmed' | 'provisional')} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary">
                <option value="confirmed">Confirmed system record</option>
                <option value="provisional">Current provisional record</option>
              </select>
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
                    Source field or column name
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
              {previewing ? 'Checking source records...' : 'Check source records'}
            </button>
          </div>
        </form>
      )}

      {!loading && (
        <section aria-labelledby="saved-mappings-heading" className="grid gap-4 border-t border-border pt-6">
          <div>
            <h3 id="saved-mappings-heading" className="text-base font-semibold">Saved mapping configurations</h3>
            <p className="mt-1 text-sm text-muted">Configurations are retained for review. Source files and subject values are not retained here.</p>
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
                <div><dt className="text-xs font-medium uppercase text-muted">Imported status</dt><dd className="mt-1">{saved.contract.record_state === 'provisional' ? 'Provisional' : 'Confirmed'}</dd></div>
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
              {canMaterialize && saved.status === 'APPROVED' && <div className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
                <label className="grid min-w-64 flex-1 gap-2 text-sm font-medium">
                  Approved source record file
                  <input aria-label={`Approved source record file for ${saved.mapping_name}`} type="file" accept=".csv,text/csv" onChange={(event) => setApprovedFiles((current) => ({ ...current, [saved.mapping_id]: event.target.files?.[0] || null }))} className="rounded border border-border px-3 py-2 text-sm file:mr-3 file:border-0 file:bg-accent file:px-2 file:py-1 file:text-sm file:font-medium" />
                </label>
                <button type="button" onClick={() => void materializeApprovedExport(saved)} disabled={materializingMappingId === saved.mapping_id} className="inline-flex items-center gap-2 rounded bg-primary px-3 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
                  {materializingMappingId === saved.mapping_id && <LoaderCircle className="h-4 w-4 animate-spin" />}
                  {materializingMappingId === saved.mapping_id ? 'Importing...' : 'Preserve as evidence'}
                </button>
              </div>}
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
