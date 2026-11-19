"""A walk with inaccessible folders must not be recorded as complete (it would invent «ya no están» files)."""

from sqlalchemy import select

from test_virtual_copy import (  # noqa: F401
    analyze,
    beat,
    client,
    files,
    folder,
    load_agent,
    login,
    office,
    pair,
    summary,
)
from app.database import SessionLocal
from app.models import Audit
from app.storage.local import LocalFolderProvider
from app.storage.providers import ScanIssue


def with_issues(monkeypatch, *issues):
    """Make the provider report the given ScanIssue after the real entries, as an unreadable folder would."""
    real = LocalFolderProvider.enumerate

    def enumerate_(self):
        yield from real(self)
        for issue in issues:
            yield issue

    monkeypatch.setattr(LocalFolderProvider, 'enumerate', enumerate_)


def test_access_denied_marks_the_walk_incomplete(folder, monkeypatch):  # noqa: F811
    root, company = folder
    agent = load_agent()
    with_issues(monkeypatch, ScanIssue('X', 'access_denied'))
    result = agent.safe_inventory(str(company), [str(root)], 'AAA010101AAA', with_index=True)
    assert result['_complete'] is False and result['incomplete'] is True
    assert result['truncated'] is False  # «límite alcanzado» stays a different thing


def test_linked_path_is_an_intentional_exclusion(folder, monkeypatch):  # noqa: F811
    root, company = folder
    with_issues(monkeypatch, ScanIssue('enlace', 'linked_path'))
    result = load_agent().safe_inventory(str(company), [str(root)], 'AAA010101AAA', with_index=True)
    assert result['_complete'] is True and result['incomplete'] is False


def test_scan_limit_is_truncated_and_incomplete(folder, monkeypatch):  # noqa: F811
    root, company = folder
    with_issues(monkeypatch, ScanIssue('', 'scan_limit'))
    result = load_agent().safe_inventory(str(company), [str(root)], 'AAA010101AAA', with_index=True)
    assert result['truncated'] is True and result['_complete'] is False


def test_incomplete_ingest_reports_no_missing_files(office, folder, monkeypatch):  # noqa: F811
    c, companies, _ = office
    root, company = folder
    agent = load_agent()
    login(c, 'ana')
    _, token = pair(c)
    beat(c, token)
    a = companies['a']
    analyze(c, token, a, agent, root, company, copy=None)
    assert summary(c, a)['scans'][0]['complete'] is True

    (company / 'notas.txt').unlink()  # would be «ya no está» after a complete walk…
    with_issues(monkeypatch, ScanIssue('X', 'access_denied'))  # …but the walk could not enter X
    analyze(c, token, a, agent, root, company, copy=None)

    last = summary(c, a)['scans'][0]
    assert last['complete'] is False and last['missing'] == 0
    assert all(f.get('missing_since') is None for f in files(c, a)['rows'])
    with SessionLocal() as db:
        texts = [r.action for r in db.scalars(select(Audit))]
    assert any('recorrido incompleto' in t for t in texts)
