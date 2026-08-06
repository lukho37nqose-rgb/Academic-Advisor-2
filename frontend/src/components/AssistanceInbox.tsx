import { useEffect, useState } from 'react';
import { AlertTriangle, Inbox, LoaderCircle } from 'lucide-react';
import {
  fetchAdminDomains,
  fetchSupportRequests,
  updateSupportRequestStatus,
  type AdminDomain,
  type SupportRequest,
  type SupportRequestStatus,
} from '../api/client';

const categoryLabels: Record<SupportRequest['category'], string> = {
  missing_information: 'Information access',
  unique_circumstance: 'Unique circumstance',
  accessibility: 'Accessibility',
  other: 'Other',
};

function errorMessage(error: unknown) {
  const maybeAxios = error as { response?: { data?: { detail?: unknown } }; message?: string };
  const detail = maybeAxios.response?.data?.detail;
  return typeof detail === 'string' ? detail : maybeAxios.message || 'Requests could not be loaded.';
}

function formatCreatedAt(value?: string | null) {
  if (!value) return 'Unknown time';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatDueAt(value?: string | null) {
  if (!value) return 'No target';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function AssistanceInbox({ canManage }: { canManage: boolean }) {
  const [domains, setDomains] = useState<AdminDomain[]>([]);
  const [domainId, setDomainId] = useState('');
  const [requests, setRequests] = useState<SupportRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      setRequests([]);
      return;
    }
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        setRequests(await fetchSupportRequests(domainId));
      } catch (requestError) {
        setError(errorMessage(requestError));
      } finally {
        setLoading(false);
      }
    })();
  }, [domainId]);

  const updateStatus = async (requestId: string, status: SupportRequestStatus) => {
    if (!domainId) return;
    setUpdatingId(requestId);
    setError(null);
    try {
      const updated = await updateSupportRequestStatus(requestId, domainId, status);
      setRequests((current) => current.map((request) => request.id === requestId ? updated : request));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 py-4">
      <section className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div className="flex items-center gap-3">
          <Inbox className="h-5 w-5 text-muted" />
          <div>
            <h2 className="text-2xl font-semibold">Assistance inbox</h2>
            <p className="mt-1 text-sm text-muted">Human follow-up requests</p>
          </div>
        </div>
        <label className="grid gap-1 text-sm font-medium">
          Domain
          <select
            aria-label="Assistance domain"
            value={domainId}
            onChange={(event) => setDomainId(event.target.value)}
            disabled={domains.length === 0}
            className="min-w-60 rounded border border-border bg-white px-3 py-2 font-normal outline-none focus:border-primary disabled:bg-accent"
          >
            {domains.length === 0 && <option value="">No assigned domains</option>}
            {domains.map((domain) => <option key={domain.domain_id} value={domain.domain_id}>{domain.domain_name}</option>)}
          </select>
        </label>
      </section>

      {!canManage && <p className="border-l-2 border-border pl-3 text-sm text-muted">This account may inspect assistance casework but cannot change its status.</p>}

      {error && <div role="alert" className="flex items-start gap-2 border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{error}</div>}
      {loading && <div className="flex items-center gap-2 py-8 text-sm text-muted"><LoaderCircle className="h-4 w-4 animate-spin" />Loading requests...</div>}
      {!loading && !error && !domainId && <p className="py-8 text-sm text-muted">No domains are assigned to this account.</p>}
      {!loading && !error && domainId && requests.length === 0 && <p className="py-8 text-sm text-muted">No assistance requests in this domain.</p>}

      {!loading && requests.length > 0 && (
        <div className="overflow-x-auto border-y border-border">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="border-b border-border bg-accent text-xs font-medium uppercase tracking-wide text-muted">
              <tr>
                <th scope="col" className="px-3 py-3">Received</th>
                <th scope="col" className="px-3 py-3">Category</th>
                <th scope="col" className="px-3 py-3">Request</th>
                <th scope="col" className="px-3 py-3">Contact</th>
                <th scope="col" className="px-3 py-3">Response due</th>
                <th scope="col" className="px-3 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {requests.map((request) => (
                <tr key={request.id} className="align-top hover:bg-accent/50">
                  <td className="whitespace-nowrap px-3 py-4 text-muted">{formatCreatedAt(request.created_at)}</td>
                  <td className="whitespace-nowrap px-3 py-4 font-medium">{categoryLabels[request.category]}</td>
                  <td className="max-w-[460px] px-3 py-4 leading-relaxed">{request.message}</td>
                  <td className="max-w-[240px] break-words px-3 py-4 text-muted">{request.contact_details || 'Not provided'}</td>
                  <td className={`whitespace-nowrap px-3 py-4 ${request.is_overdue ? 'font-medium text-rose-700' : 'text-muted'}`}>{request.is_overdue ? 'Overdue · ' : ''}{formatDueAt(request.response_due_at)}</td>
                  <td className="px-3 py-4">
                    {request.responsible_group && <p className={`mb-2 text-xs ${request.is_escalated ? 'font-medium text-rose-700' : 'text-muted'}`}>{request.is_escalated ? 'Escalation due: ' : 'Responsible: '}{request.is_escalated ? request.fallback_group || request.responsible_group : request.responsible_group}</p>}
                    <select
                      aria-label={`Status for request ${request.id}`}
                      value={request.status}
                      disabled={!canManage || updatingId === request.id}
                      onChange={(event) => void updateStatus(request.id, event.target.value as SupportRequestStatus)}
                      className="w-36 rounded border border-border bg-white px-2 py-1.5 outline-none focus:border-primary disabled:bg-accent"
                    >
                      <option value="OPEN">Open</option>
                      <option value="IN_PROGRESS">In progress</option>
                      <option value="CLOSED">Closed</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
