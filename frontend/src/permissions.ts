import type { Company, CurrentUser, Responsible } from './types';

// The server decides every permission; these helpers only choose what to show. A hidden control never
// replaces the server check (backend/app/permissions.py).

export type Action =
  | 'empresa.editar'
  | 'empresa.archivar'
  | 'documentos.subir'
  | 'documentos.clasificar'
  | 'documentos.eliminar'
  | 'obligaciones.editar'
  | 'obligaciones.verificar'
  | 'calendario.gestionar'
  | 'tareas.editar'
  | 'recopila.usar'
  | 'cfdi.usar'
  | 'declara.usar'
  | 'recibos.usar'
  | 'carpeta.analizar'
  | 'historial.ver';

type User = Pick<CurrentUser, 'admin' | 'actions'> & Partial<Pick<CurrentUser, 'role'>>;

export function can(user: User | null | undefined, action: Action, companyId?: string | null): boolean {
  if (!user) return false;
  if (user.admin) return true;
  if (!companyId) return false;
  return !!user.actions?.[companyId]?.includes(action);
}

/** The action in at least one company (opens a module such as Recopila). */
export function canAnywhere(user: User | null | undefined, action: Action): boolean {
  if (!user) return false;
  return user.admin || Object.values(user.actions || {}).some((list) => list.includes(action));
}

export const canRegisterCompanies = (user: User | null | undefined) =>
  !!user && (user.admin || user.role === 'contador');

export const canManageUsers = (user: User | null | undefined) => !!user && (user.admin || user.role === 'contador');

export const ROLE_LABELS: Record<CurrentUser['role'], string> = {
  admin: 'Administrador',
  contador: 'Contador',
  auxiliar: 'Auxiliar',
};

/** Name of the responsible accountant, marked when the account is disabled. */
export function responsibleName(company: Company, responsibles: Responsible[] | undefined): string {
  if (!company.accountant_id) return 'Sin responsable';
  const user = responsibles?.find((r) => r.id === company.accountant_id);
  if (!user) return company.accountant || 'Sin responsable';
  return user.display_name + (user.enabled ? '' : ' (inactivo)');
}
