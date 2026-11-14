"""Responsible accountant of a company, by user id (Bloque 2, point 5; docs/BLOQUE_2_ROLES.md).

- Only an administrator assigns, changes or removes it, and it is always an active `contador`.
- Assigning it creates or upgrades that accountant's write grant (the response says so).
- Changing it asks what to do with the previous accountant's access: nothing is removed implicitly.
- The old free text is reconciled by exact name in a list an administrator reviews; nothing is applied
  automatically, and the original text is kept until the administrator confirms its retirement.
Every change goes to the company history with its author and the previous and new values.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .database import session
from .models import Audit, Company, UserAccount, UserCompanyAction, UserCompanyGrant
from .security import Principal, admin_auth

router = APIRouter(prefix='/api/responsible', tags=['Contador responsable'])
UNASSIGNED = 'Sin asignar'


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AssignIn(Input):
    # Expected current responsible: a concurrent change makes the request fail instead of overwriting it.
    current_accountant_id: str | None = Field(None, max_length=36)
    accountant_id: str | None = Field(None, max_length=36)
    # Required whenever there is a previous responsible who is being replaced or removed.
    previous_access: Literal['keep', 'read', 'remove'] | None = None


class ApplyItem(Input):
    company_id: str = Field(min_length=1, max_length=36)
    accountant_id: str = Field(min_length=1, max_length=36)


class ApplyIn(Input):
    items: list[ApplyItem] = Field(min_length=1, max_length=500)


class RetireIn(Input):
    company_ids: list[str] = Field(min_length=1, max_length=500)


def person(user):
    return None if user is None else {'id': user.id, 'display_name': user.display_name, 'enabled': user.enabled}


def candidate(db, ident):
    user = db.get(UserAccount, ident)
    if user is None or user.role != 'contador' or not user.enabled:
        raise HTTPException(422, 'El responsable debe ser un contador activo.')
    return user


def text_unchanged(company, data):
    """Free-text edits of `accountant` stop once the company has a responsible user."""
    if company.accountant_id and data.accountant != company.accountant:
        raise HTTPException(422, 'Cambia el contador responsable desde su asignación, no como texto.')


def assign(db, actor, company, new_id, previous_access=None):
    """Set (or clear, with new_id None) the responsible. Returns notices for the administrator."""
    old_id = company.accountant_id
    if new_id == old_id:
        return []
    new = candidate(db, new_id) if new_id else None
    old = db.get(UserAccount, old_id) if old_id else None
    notices = []
    if old_id:
        if previous_access is None:
            raise HTTPException(422, 'Indica qué hacer con el acceso del responsable anterior.')
        grant = db.get(UserCompanyGrant, (old_id, company.id))
        if grant and previous_access == 'read':
            grant.access = 'read'
            notices.append('El responsable anterior conserva acceso de lectura.')
        elif grant and previous_access == 'remove':
            db.execute(
                delete(UserCompanyAction).where(
                    UserCompanyAction.user_id == old_id, UserCompanyAction.company_id == company.id
                )
            )
            db.delete(grant)
            notices.append('Se retiró el acceso del responsable anterior.')
        else:
            notices.append('El responsable anterior conserva su acceso.')
    if new:
        grant = db.get(UserCompanyGrant, (new.id, company.id))
        if grant is None:
            db.add(UserCompanyGrant(user_id=new.id, company_id=company.id, access='write'))
            notices.append('Se concedió acceso de escritura a ' + new.display_name + '.')
        elif grant.access != 'write':
            grant.access = 'write'
            notices.append('Se amplió a escritura el acceso de ' + new.display_name + '.')
    before = company.accountant
    company.accountant_id = new.id if new else None
    company.accountant = new.display_name if new else UNASSIGNED
    action = 'Responsable asignado' if not old_id else ('Responsable retirado' if not new else 'Responsable cambiado')
    changes = {
        'responsable': {'before': person(old) or {'name': before}, 'after': person(new)},
    }
    if old_id:
        changes['acceso_anterior'] = {'after': previous_access}
    db.add(Audit(company_id=company.id, action=action, actor_id=actor.subject, changes=changes))
    return notices


def company_or_404(db, cid):
    company = db.get(Company, cid)
    if company is None:
        raise HTTPException(404, 'Empresa no encontrada.')
    return company


@router.get('/candidates')
def candidates(principal: Principal = Depends(admin_auth), db: Session = Depends(session)):
    """Active accountants that can be assigned; disabled ones never appear here."""
    rows = db.scalars(
        select(UserAccount)
        .where(UserAccount.role == 'contador', UserAccount.enabled == True)  # noqa: E712
        .order_by(UserAccount.display_name)
    )
    return [{'id': u.id, 'display_name': u.display_name, 'username': u.username} for u in rows]


@router.put('/companies/{cid}')
def set_responsible(
    cid: str, payload: AssignIn, principal: Principal = Depends(admin_auth), db: Session = Depends(session)
):
    company = company_or_404(db, cid)
    if company.accountant_id != payload.current_accountant_id:
        raise HTTPException(409, 'El responsable cambió. Actualiza antes de guardar.')
    notices = assign(db, principal, company, payload.accountant_id, payload.previous_access)
    db.commit()
    return {
        'company_id': cid,
        'accountant_id': company.accountant_id,
        'accountant': company.accountant,
        'notices': notices,
    }


@router.get('/reconciliation')
def reconciliation(principal: Principal = Depends(admin_auth), db: Session = Depends(session)):
    """Old free text against active accountants by exact name. A proposal only: nothing is applied."""
    accountants = db.scalars(select(UserAccount).where(UserAccount.role == 'contador')).all()
    by_name = {}
    for u in accountants:
        by_name.setdefault(u.display_name.strip(), []).append(u)
    rows = []
    for c in db.scalars(select(Company).where(Company.accountant_legacy.is_not(None)).order_by(Company.name)):
        matches = by_name.get(c.accountant_legacy.strip(), [])
        active = [u for u in matches if u.enabled]
        status = (
            'assigned'
            if c.accountant_id
            else ('match' if len(active) == 1 else 'ambiguous' if len(active) > 1 else 'none')
        )
        rows.append(
            {
                'company_id': c.id,
                'company': c.name,
                'legacy_text': c.accountant_legacy,
                'accountant_id': c.accountant_id,
                'status': status,
                'candidates': [person(u) for u in active],
            }
        )
    return rows


@router.post('/reconciliation/apply')
def apply_reconciliation(payload: ApplyIn, principal: Principal = Depends(admin_auth), db: Session = Depends(session)):
    """Assign the matches the administrator confirmed, one by one; only companies without a responsible."""
    result = []
    for item in payload.items:
        company = company_or_404(db, item.company_id)
        if company.accountant_id:
            raise HTTPException(409, 'La empresa ' + company.name + ' ya tiene responsable.')
        result.append({'company_id': company.id, 'notices': assign(db, principal, company, item.accountant_id)})
    db.commit()
    return result


@router.post('/reconciliation/retire')
def retire_legacy(payload: RetireIn, principal: Principal = Depends(admin_auth), db: Session = Depends(session)):
    """Discard the original free text once the administrator confirms it is no longer needed."""
    for cid in dict.fromkeys(payload.company_ids):
        company = company_or_404(db, cid)
        if company.accountant_legacy is None:
            continue
        db.add(
            Audit(
                company_id=cid,
                action='Texto anterior de contador retirado',
                actor_id=principal.subject,
                changes={'accountant_legacy': {'before': company.accountant_legacy, 'after': None}},
            )
        )
        company.accountant_legacy = None
    db.commit()
    return {'ok': True}
