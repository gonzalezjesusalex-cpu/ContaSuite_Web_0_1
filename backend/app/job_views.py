"""How jobs are shown to the browser.

`/api/state` is polled every minute, so its jobs carry only a small summary of `result`; the full result of the latest
job of a company is served by `/api/companies/{id}/jobs/latest`.
"""

from .models import Job

KINDS = ('scan_folder', 'export_virtual', 'sat_declaraciones', 'write_cfdi')
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
    'escritos',
    'cancelado',
    'duplicados',
    'errores',
    'detalle',
    'destino',
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


def without_workers(result):
    """The result of an analysis without the workers' personal data (names, folders, file paths).

    For people without `trabajadores.ver`: the section is removed, the group of the summary keeps only its count and
    the plain file list drops what the classification places in the workers' group.
    """
    from .folder_groups import classify

    if not isinstance(result, dict):
        return result
    out = {k: v for k, v in result.items() if k != 'trabajadores'}
    summary = out.get('summary')
    if isinstance(summary, dict) and isinstance(summary.get('groups'), list):
        groups = [
            {**g, 'examples': [], 'subgroups': {}, 'sensitive': True} if g.get('key') == 'trabajadores' else g
            for g in summary['groups']
        ]
        out['summary'] = {**summary, 'groups': groups}
    if isinstance(out.get('files'), list):
        out['files'] = [
            f for f in out['files'] if classify(str(f.get('relative_path', '')))[0] != 'trabajadores'
        ]
    return out


def job_row(job, principal, result=None):
    """A job as the browser sees it. The payload (it carries the folder path) is only for administrators."""
    row = {c.name: getattr(job, c.name) for c in Job.__table__.columns if principal.admin or c.name != 'payload'}
    row['result'] = brief(job.result) if result is None else result
    return row
