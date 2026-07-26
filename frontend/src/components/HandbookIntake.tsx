import { type ChangeEvent, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Check, ChevronLeft, ChevronRight, FileSearch, Files, LoaderCircle, Pencil, ScanText, Upload, X } from 'lucide-react';
import {
  fetchAdminDomains,
  fetchHandbookPages,
  fetchHandbookOCRReviews,
  fetchHandbookUploads,
  requestHandbookOCR,
  reviewHandbookOCR,
  uploadHandbook,
  type AdminDomain,
  type HandbookOCRReview,
  type HandbookPageExcerpt,
  type HandbookUpload,
} from '../api/client';

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Handbook intake could not be completed.';
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatProgress(upload: HandbookUpload) {
  if (!upload.total_pages) return upload.status === 'QUEUED' ? 'Queued' : 'Preparing pages';
  return `${upload.processed_pages} of ${upload.total_pages} pages`;
}

export function HandbookIntake() {
  const [domains, setDomains] = useState<AdminDomain[]>([]);
  const [domainId, setDomainId] = useState('');
  const [uploads, setUploads] = useState<HandbookUpload[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewUpload, setReviewUpload] = useState<HandbookUpload | null>(null);
  const [reviewPages, setReviewPages] = useState<HandbookPageExcerpt[]>([]);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewPageAfter, setReviewPageAfter] = useState(0);
  const [reviewHistory, setReviewHistory] = useState<number[]>([]);
  const [nextReviewPageAfter, setNextReviewPageAfter] = useState<number | null>(null);
  const [ocrReviews, setOcrReviews] = useState<HandbookOCRReview[]>([]);
  const [ocrDrafts, setOcrDrafts] = useState<Record<number, string>>({});
  const [ocrRequestingId, setOcrRequestingId] = useState<string | null>(null);
  const [ocrUpdatingPage, setOcrUpdatingPage] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [loadedDomains, loadedUploads] = await Promise.all([fetchAdminDomains(), fetchHandbookUploads()]);
      setDomains(loadedDomains);
      setDomainId((current) => current || loadedDomains[0]?.domain_id || '');
      setUploads(loadedUploads);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const loadReview = async (upload: HandbookUpload, afterPage: number, history: number[]) => {
    setReviewUpload(upload);
    setReviewLoading(true);
    setReviewError(null);
    try {
      const [review, loadedOcrReviews] = await Promise.all([
        fetchHandbookPages(upload.handbook_id, afterPage),
        upload.status === 'OCR_REVIEW_REQUIRED' ? fetchHandbookOCRReviews(upload.handbook_id) : Promise.resolve([]),
      ]);
      setReviewPages(review.items);
      setOcrReviews(loadedOcrReviews);
      setOcrDrafts(Object.fromEntries(loadedOcrReviews.map((item) => [item.page_number, item.proposed_text])));
      setReviewPageAfter(afterPage);
      setReviewHistory(history);
      setNextReviewPageAfter(review.next_page_after || null);
    } catch (requestError) {
      setReviewError(errorMessage(requestError));
    } finally {
      setReviewLoading(false);
    }
  };

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    setSelectedFile(event.target.files?.[0] || null);
    setError(null);
  };

  const submit = async () => {
    if (!selectedFile || !domainId) return;
    setUploading(true);
    setError(null);
    try {
      const upload = await uploadHandbook(domainId, selectedFile);
      setUploads((current) => [upload, ...current]);
      setSelectedFile(null);
      if (inputRef.current) inputRef.current.value = '';
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setUploading(false);
    }
  };

  const requestOCR = async (upload: HandbookUpload) => {
    setOcrRequestingId(upload.handbook_id);
    setError(null);
    try {
      const updated = await requestHandbookOCR(upload.handbook_id);
      setUploads((current) => current.map((item) => item.handbook_id === updated.handbook_id ? updated : item));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setOcrRequestingId(null);
    }
  };

  const submitOCRDecision = async (pageNumber: number, action: 'ACCEPT' | 'CORRECT' | 'REJECT') => {
    if (!reviewUpload) return;
    setOcrUpdatingPage(pageNumber);
    setReviewError(null);
    try {
      const updated = await reviewHandbookOCR(reviewUpload.handbook_id, pageNumber, action, ocrDrafts[pageNumber]);
      setOcrReviews((current) => current.map((item) => item.page_number === pageNumber ? updated : item));
      if (action !== 'REJECT') {
        const sourceText = action === 'ACCEPT' ? updated.proposed_text : updated.reviewed_text || '';
        setReviewPages((current) => current.map((page) => page.page_number === pageNumber ? { ...page, text_content: sourceText } : page));
      }
      void load();
    } catch (requestError) {
      setReviewError(errorMessage(requestError));
    } finally {
      setOcrUpdatingPage(null);
    }
  };

  const closeReview = () => {
    setReviewUpload(null);
    setReviewPages([]);
    setReviewError(null);
    setReviewHistory([]);
    setNextReviewPageAfter(null);
    setOcrReviews([]);
    setOcrDrafts({});
  };

  return <div className="mx-auto flex w-full max-w-5xl flex-col gap-7 py-4">
    <section className="flex items-center gap-3 border-b border-border pb-5">
      <Files className="h-5 w-5 text-muted" />
      <div><h2 className="text-2xl font-semibold">Handbook intake</h2><p className="mt-1 text-sm text-muted">Verified source documents</p></div>
    </section>

    <section className="grid gap-4 border-b border-border pb-6 md:grid-cols-[minmax(0,1fr)_220px_auto] md:items-end">
      <label className="grid gap-2 text-sm font-medium">
        Handbook PDF
        <input ref={inputRef} aria-label="Handbook PDF" type="file" accept="application/pdf,.pdf" onChange={selectFile} className="block w-full text-sm text-muted file:mr-3 file:rounded file:border-0 file:bg-accent file:px-3 file:py-2 file:text-sm file:font-medium file:text-primary hover:file:bg-border" />
      </label>
      <label className="grid gap-2 text-sm font-medium">
        Domain
        <select aria-label="Handbook domain" value={domainId} onChange={(event) => setDomainId(event.target.value)} disabled={domains.length === 0} className="rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary disabled:bg-accent">
          {domains.length === 0 && <option value="">No assigned domains</option>}
          {domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}
        </select>
      </label>
      <button type="button" onClick={() => void submit()} disabled={!selectedFile || !domainId || uploading} className="inline-flex h-10 items-center justify-center gap-2 rounded bg-primary px-4 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-40">
        {uploading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
        {uploading ? 'Verifying...' : 'Queue handbook'}
      </button>
    </section>

    {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
    {loading && <div className="flex items-center gap-2 py-8 text-sm text-muted"><LoaderCircle className="h-4 w-4 animate-spin" />Loading handbook sources...</div>}
    {!loading && !error && uploads.length === 0 && <p className="py-8 text-sm text-muted">No handbook sources have been queued.</p>}
    {!loading && uploads.length > 0 && <div className="overflow-x-auto border-y border-border"><table className="w-full min-w-[860px] text-left text-sm"><thead className="border-b border-border bg-accent text-xs font-medium uppercase tracking-wide text-muted"><tr><th scope="col" className="px-3 py-3">Source</th><th scope="col" className="px-3 py-3">Status</th><th scope="col" className="px-3 py-3">Progress</th><th scope="col" className="px-3 py-3">Verification</th><th scope="col" className="w-24 px-3 py-3"><span className="sr-only">Source actions</span></th></tr></thead><tbody className="divide-y divide-border">{uploads.map((upload) => <tr key={upload.handbook_id} className="align-top"><td className="px-3 py-4"><span className="block font-medium">{upload.file_name}</span><span className="mt-1 block text-xs text-muted">{formatBytes(upload.file_size_bytes)}</span></td><td className="px-3 py-4 font-medium">{upload.status.replaceAll('_', ' ')}</td><td className="px-3 py-4 text-muted">{formatProgress(upload)}{upload.error_message && <span className="mt-1 block text-rose-700">{upload.error_message}</span>}</td><td className="px-3 py-4 font-mono text-xs text-muted">{upload.content_hash ? `${upload.content_hash.slice(0, 12)}...` : 'Awaiting verification'}</td><td className="px-3 py-4"><div className="flex items-center gap-1"><button type="button" aria-label={`Review ${upload.file_name}`} title={`Review ${upload.file_name}`} disabled={upload.processed_pages === 0} onClick={() => void loadReview(upload, 0, [])} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-accent hover:text-primary disabled:cursor-not-allowed disabled:opacity-35"><FileSearch className="h-4 w-4" /></button>{upload.status === 'NEEDS_MANUAL_REVIEW' && <button type="button" aria-label={`Request OCR for ${upload.file_name}`} title={`Request OCR for ${upload.file_name}`} disabled={ocrRequestingId === upload.handbook_id} onClick={() => void requestOCR(upload)} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-accent hover:text-primary disabled:cursor-not-allowed disabled:opacity-35">{ocrRequestingId === upload.handbook_id ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ScanText className="h-4 w-4" />}</button>}</div></td></tr>)}</tbody></table></div>}

    {reviewUpload && <section className="border-y border-border py-6">
      <header className="flex items-start justify-between gap-4 border-b border-border pb-4">
        <div className="flex items-center gap-3"><FileSearch className="h-5 w-5 text-muted" /><div><h2 className="text-xl font-semibold">Source review</h2><p className="mt-1 text-sm text-muted">{reviewUpload.file_name}</p></div></div>
        <button type="button" aria-label="Close source review" title="Close source review" onClick={closeReview} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-accent hover:text-primary"><X className="h-4 w-4" /></button>
      </header>
      {reviewError && <div role="alert" className="mt-4 flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{reviewError}</div>}
      {reviewLoading && <div className="flex items-center gap-2 py-8 text-sm text-muted"><LoaderCircle className="h-4 w-4 animate-spin" />Loading source pages...</div>}
      {!reviewLoading && !reviewError && reviewPages.length === 0 && <p className="py-8 text-sm text-muted">No extracted pages are available yet.</p>}
      {!reviewLoading && reviewPages.length > 0 && <div className="divide-y divide-border">{reviewPages.map((page) => {
        const ocrReview = ocrReviews.find((item) => item.page_number === page.page_number);
        const pendingReview = ocrReview?.status === 'PENDING_REVIEW' || ocrReview?.status === 'REJECTED';
        return <article key={page.page_number} className="py-5"><div className="flex flex-wrap items-baseline justify-between gap-3"><h3 className="font-medium">Page {page.page_number}</h3><span className="font-mono text-xs text-muted">{reviewUpload.file_name}, page {page.page_number}</span></div><pre className="mt-3 max-h-96 overflow-y-auto whitespace-pre-wrap border-l-2 border-border pl-4 font-sans text-sm leading-6 text-primary">{page.text_content}</pre>{ocrReview && <div className="mt-4 border-l-2 border-primary pl-4"><div className="flex flex-wrap items-baseline justify-between gap-3"><p className="text-sm font-medium">OCR proposal</p><span className="text-xs text-muted">{ocrReview.provider_name}</span></div><textarea aria-label={`Reviewed OCR text for page ${page.page_number}`} value={ocrDrafts[page.page_number] || ''} disabled={!pendingReview || ocrUpdatingPage === page.page_number} onChange={(event) => setOcrDrafts((current) => ({ ...current, [page.page_number]: event.target.value }))} className="mt-3 min-h-32 w-full resize-y border border-border bg-white p-3 text-sm leading-6 outline-none focus:border-primary disabled:bg-accent" />{pendingReview && <div className="mt-3 flex items-center justify-end gap-2"><button type="button" aria-label={`Reject OCR text for page ${page.page_number}`} title={`Reject OCR text for page ${page.page_number}`} disabled={ocrUpdatingPage === page.page_number} onClick={() => void submitOCRDecision(page.page_number, 'REJECT')} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-rose-50 hover:text-rose-700 disabled:opacity-35"><X className="h-4 w-4" /></button><button type="button" aria-label={`Correct OCR text for page ${page.page_number}`} title={`Correct OCR text for page ${page.page_number}`} disabled={ocrUpdatingPage === page.page_number} onClick={() => void submitOCRDecision(page.page_number, 'CORRECT')} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-accent hover:text-primary disabled:opacity-35"><Pencil className="h-4 w-4" /></button><button type="button" aria-label={`Accept OCR text for page ${page.page_number}`} title={`Accept OCR text for page ${page.page_number}`} disabled={ocrUpdatingPage === page.page_number} onClick={() => void submitOCRDecision(page.page_number, 'ACCEPT')} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-emerald-50 hover:text-emerald-700 disabled:opacity-35">{ocrUpdatingPage === page.page_number ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}</button></div>} {!pendingReview && <p className="mt-3 text-xs text-muted">{ocrReview.status.replaceAll('_', ' ')}</p>}</div>}</article>;
      })}</div>}
      <footer className="mt-5 flex items-center justify-end gap-2"><button type="button" aria-label="Previous source pages" title="Previous source pages" disabled={reviewLoading || reviewHistory.length === 0} onClick={() => { const previous = reviewHistory[reviewHistory.length - 1]; void loadReview(reviewUpload, previous, reviewHistory.slice(0, -1)); }} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-accent hover:text-primary disabled:cursor-not-allowed disabled:opacity-35"><ChevronLeft className="h-4 w-4" /></button><button type="button" aria-label="Next source pages" title="Next source pages" disabled={reviewLoading || nextReviewPageAfter === null} onClick={() => { if (nextReviewPageAfter !== null) void loadReview(reviewUpload, nextReviewPageAfter, [...reviewHistory, reviewPageAfter]); }} className="inline-flex h-8 w-8 items-center justify-center rounded text-muted hover:bg-accent hover:text-primary disabled:cursor-not-allowed disabled:opacity-35"><ChevronRight className="h-4 w-4" /></button></footer>
    </section>}
  </div>;
}
