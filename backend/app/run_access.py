"""Who may use Recopila, CFDI, Declara and Recibos, and which runs each account sees (Bloque 2, point 2b).

An administrator sees everything. Any other account needs the module action (`recopila.usar`, ...) in at
least one company; it then sees the runs it created and those of companies where it holds that action
(decision 5 of 14/11/2026, docs/BLOQUE_2_ROLES.md). Runs that predate `created_by` and have no company stay
visible to administrators only.
"""

from fastapi import Depends, HTTPException
from sqlalchemy import false, or_, true

from .security import Principal, auth


class ModuleAccess:
    def __init__(self, action, not_found='Registro no encontrado.'):
        self.action = action
        self.not_found = not_found

    def companies(self, p: Principal):
        return frozenset(c for c in p.company_ids if p.can(self.action, c))

    def dependency(self):
        """Router-level check: the account may open this module at all."""

        def check(principal: Principal = Depends(auth)):
            if not principal.admin and not self.companies(principal):
                raise HTTPException(403, 'Tu perfil no permite usar este módulo.')
            return principal

        return check

    def require_company(self, p: Principal, company_id):
        """For a new run: a chosen company needs the action there (404 outside the account's companies)."""
        if company_id:
            p.require(self.action, company_id)

    def visible(self, p: Principal, row):
        return p.admin or row.created_by == p.subject or bool(row.company_id and p.can(self.action, row.company_id))

    def check(self, p: Principal, row):
        if not self.visible(p, row):
            raise HTTPException(404, self.not_found)
        return row

    def scope(self, p: Principal, model):
        """WHERE clause limiting a listing to what check() would allow."""
        if p.admin:
            return true()
        companies = self.companies(p)
        return or_(model.created_by == p.subject, model.company_id.in_(companies) if companies else false())


RECOPILA = ModuleAccess('recopila.usar', 'Análisis no encontrado')
CFDI = ModuleAccess('cfdi.usar', 'Análisis no encontrado')
DECLARA = ModuleAccess('declara.usar', 'Análisis de Declara no encontrado')
RECIBOS = ModuleAccess('recibos.usar', 'Recibo no encontrado')
