"""How jobs are shown to the browser.

`/api/state` is polled every minute, so its jobs carry only a small summary of `result`; the full result of the latest
job of a company is served by `/api/companies/{id}/jobs/latest`.
"""

from .models import Job

KINDS = ('scan_folder', 'export_virtual', 'sat_declaraciones')
# What the screens need from a job without loading its (possibly huge) result: failures, the SAT download's progress
# and cancellation, the outcome flags of an analysis and the small counters of a SAT download.
BRIEF_KEYS = (
    'error',
    'error_code',
    'progreso',
    'cancelar',
    'truncated',
    'incomplete',
    'warnings',
    'copia',
    'analisis_id',
    'cancelada',
    'interrumpida',
    'prueba_en_seco',
    'detectadas',
    'entregados',
    'mode',
)


def brief(result):
    """The small part of a job result that travels with the polled state."""
    if not isinstance(result, dict):
        return {}
    out = {key: result[key] for key in BRIEF_KEYS if key in result}
    summary = result.get('summary')
    if isinstance(summary, dict) and isinstance(summary.get('total'), int):
        out['total'] = summary['total']  # how many files the analysis classified
    elif isinstance(result.get('files'), list):
        out['total'] = len(result['files'])
    return out


def job_row(job, principal, result=None):
    """A job as the browser sees it. The payload (it carries the folder path) is only for administrators."""
    row = {c.name: getattr(job, c.name) for c in Job.__table__.columns if principal.admin or c.name != 'payload'}
    row['result'] = brief(job.result) if result is None else result
    return row
