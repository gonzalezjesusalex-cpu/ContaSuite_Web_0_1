import { useEffect, useState } from 'react';
import { api } from './api';
import type { Job, State } from './types';

/**
 * The latest job of a company by kind WITH its full result.
 *
 * `state.jobs` (polled) only carries a small summary of each result, and only the 50 most recent jobs of every company
 * together, so the full result comes from `/companies/{id}/jobs/latest`. It is loaded again when the job's state
 * changes in `state.jobs` (new job, new status, new progress) and on `contasuite-data-changed`.
 * While the full copy is not up to date, the summary from `state.jobs` is returned (status and errors are right).
 * `status` asks for the latest job in that status (for example the last completed analysis while a new one runs).
 */
export function useLatestJob(
  state: State,
  company: string | undefined,
  kind: string,
  status?: string,
  enabled = true,
): Job | undefined {
  const brief = state.jobs.find(
    (j) => j.company_id === company && j.kind === kind && (!status || j.status === status),
  );
  const [full, setFull] = useState<Job | null>(null);
  const signature = brief ? brief.id + ':' + brief.status + ':' + JSON.stringify(brief.result) : '-';
  useEffect(() => {
    if (!company || !enabled) {
      setFull(null);
      return;
    }
    const controller = new AbortController();
    const load = () => {
      const query = '?kind=' + kind + (status ? '&status=' + status : '');
      api<Job | null>('/companies/' + company + '/jobs/latest' + query, 'GET', undefined, controller.signal)
        .then(setFull)
        .catch(() => undefined); // the summary of the polled state is still shown
    };
    load();
    window.addEventListener('contasuite-data-changed', load);
    return () => {
      controller.abort();
      window.removeEventListener('contasuite-data-changed', load);
    };
  }, [company, kind, status, enabled, signature]);
  const mine = full && full.company_id === company && full.kind === kind ? full : undefined;
  if (mine && (!brief || (mine.id === brief.id && mine.status === brief.status))) return mine;
  // For «the last completed one» the previous full result is better than a summary while the new one loads.
  return status && mine ? mine : (brief ?? mine);
}
