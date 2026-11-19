"""«Importar > Vista previa» of the Excel «Control de obligaciones» (cambio 3A.6).

PREVIEW ONLY: the workbook is read in memory and discarded; no fiscal record, batch or row is written. The only writes
are the confirmed Excel-name equivalences (their own audited table). Administration only.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from . import fiscal_equivalence as equivalence
from .company_xlsx import InvalidWorkbook
from .database import session
from .fiscal_control import catalog, metadata as fiscal_metadata
from .fiscal_import import normalize, preview
from .fiscal_xlsx import MAX_BYTES, read_workbook
from .models import Company, CompanyRegime
from .schema_cache import tables_ready
from .security import Principal, auth

router = APIRouter(prefix='/api/fiscal-control/import', tags=['Control de obligaciones: importar'])
DETAIL_ROWS_PER_SHEET = 300


def _companies(db):
    regimes = {}
    for row in db.execute(select(CompanyRegime.company_id, CompanyRegime.label)):
        regimes.setdefault(row[0], []).append(row[1])
    return [
        dict(id=c.id, name=c.name, rfc=c.rfc, regimes=regimes.get(c.id) or ([c.regime] if c.regime else []))
        for c in db.scalars(select(Company).order_by(Company.name))
    ]


def _summarize(sheets, ignored, unknown, rows, companies, flags):
    by_sheet = {}
    names = {}
    for row in rows:
        stat = by_sheet.setdefault(
            row['sheet'], dict(rows=0, confirmed=0, proposed=0, ambiguous=0, unmatched=0, conflicts=0, detail=[])
        )
        stat['rows'] += 1
        key = {'rfc': 'confirmed', 'confirmed': 'confirmed', 'proposed': 'proposed', 'ambiguous': 'ambiguous'}.get(
            row['company_match'], 'unmatched'
        )
        stat[key] += 1
        cell_conflicts = sum(1 for c in row['cells'] if c['conflicts'])
        stat['conflicts'] += cell_conflicts + len(
            [c for c in row['conflicts'] if c not in {'company_not_confirmed', 'company_not_unique'}]
        )
        if len(stat['detail']) < DETAIL_ROWS_PER_SHEET:
            stat['detail'].append(row)
        if key in ('proposed', 'ambiguous', 'unmatched'):
            names.setdefault(
                normalize(row['excel_name']),
                dict(
                    excel_name=row['excel_name'],
                    status=key,
                    candidates=[c for c in companies if c['id'] in row['candidate_company_ids']],
                    sheets=[],
                ),
            )['sheets'].append(row['sheet'])
    empty = dict(rows=0, confirmed=0, proposed=0, ambiguous=0, unmatched=0, conflicts=0, detail=[])
    out = []
    for sheet in sheets:
        stat = by_sheet.get(sheet['name'], empty)
        counts = {k: v for k, v in stat.items() if k != 'detail'}
        detail = [{k: v for k, v in r.items() if k != 'original'} for r in stat['detail']]
        out.append(
            dict(
                name=sheet['name'],
                period=sheet['period'],
                **counts,
                truncated=stat['rows'] > DETAIL_ROWS_PER_SHEET,
                detail=detail,
            )
        )
    return dict(
        applied=False,
        sheets=out,
        ignored_sheets=ignored,
        unknown_columns=unknown,
        names_to_confirm=sorted(names.values(), key=lambda n: n['excel_name']),
        **flags,
    )


@router.post('/preview')
async def import_preview(
    request: Request,
    authorized_read: bool = False,
    principal: Principal = Depends(auth),
    db=Depends(session),
):
    principal.require_admin()
    if not authorized_read:
        raise HTTPException(
            423, 'Autoriza expresamente el análisis del archivo. No se escribirá ningún registro fiscal.'
        )
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > MAX_BYTES:
            raise HTTPException(413, 'Archivo superior a 15 MB.')
        payload.extend(chunk)
    try:
        workbook = read_workbook(bytes(payload))
    except InvalidWorkbook as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        payload.clear()
    catalog_ready = tables_ready(db, fiscal_metadata)
    definitions = [dict(r) for r in db.execute(select(catalog)).mappings()] if catalog_ready else []
    companies = _companies(db)
    rows = preview(workbook['sheets'], companies, definitions, equivalence.confirmed(db))
    flags = dict(
        catalog_available=catalog_ready,
        equivalences_available=equivalence.available(db),
        formula_cells_omitted=workbook['formula_cells_omitted'],
    )
    return _summarize(workbook['sheets'], workbook['ignored'], workbook['unknown_columns'], rows, companies, flags)


class EquivalenceIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    excel_name: str = Field(min_length=1, max_length=255)
    company_id: str = Field(min_length=1, max_length=36)
    action: Literal['confirm'] = 'confirm'


class RevokeIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    excel_name: str = Field(min_length=1, max_length=255)


@router.get('/equivalences')
def list_equivalences(principal: Principal = Depends(auth), db=Depends(session)):
    principal.require_admin()
    return dict(available=equivalence.available(db), items=equivalence.listing(db))


@router.put('/equivalences')
def confirm_equivalence(payload: EquivalenceIn, principal: Principal = Depends(auth), db=Depends(session)):
    principal.require_admin()
    return equivalence.confirm(db, principal, payload.excel_name, payload.company_id)


@router.post('/equivalences/revoke')
def revoke_equivalence(payload: RevokeIn, principal: Principal = Depends(auth), db=Depends(session)):
    principal.require_admin()
    return equivalence.revoke(db, principal, payload.excel_name)


@router.get('/equivalences/history')
def equivalence_history(excel_name: str, principal: Principal = Depends(auth), db=Depends(session)):
    principal.require_admin()
    return equivalence.trail(db, excel_name)
