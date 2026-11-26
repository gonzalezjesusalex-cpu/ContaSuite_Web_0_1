export const dossierSections = ['Resumen', 'Obligaciones', 'Documentos', 'FIEL/CSD', 'Actividad'];
export function dossierSection(tab: string | null) {
  if (tab === 'Cumplimiento' || tab === 'Histórico fiscal') return 'Obligaciones';
  if (tab === 'Credenciales y Certificados' || tab === 'e.firma y CSD') return 'FIEL/CSD';
  if (tab === 'Tareas' || tab === 'Historial' || tab === 'Declaraciones') return 'Actividad';
  if (tab === 'Explorador documental') return 'Documentos';
  return dossierSections.includes(tab || '') ? tab! : 'Resumen';
}
export function dossierUrl(id: string, tab: string | null, period: string, context?: URLSearchParams) {
  const q = new URLSearchParams({ tab: dossierSection(tab), period });
  for (const key of ['query', 'responsible', 'status', 'archive', 'sort']) {
    const value = context?.get(key);
    if (value) q.set(key, value);
  }
  return '/empresas/' + encodeURIComponent(id) + '?' + q;
}
// Dashboard principal (Workspace Fiscal › Empresas): four tabs, three of them with sub-tabs, kept in the URL as
// `?tab=<tab>&sub=<sub>` so a reload or a shared link opens the same view.
export type DashboardTab = 'resumen' | 'empresas' | 'documentos' | 'obligaciones';
export type DashboardSection = {
  id: DashboardTab;
  label: string;
  subtitle: string;
  /** Only these tabs depend on the period and show its control. */
  period: boolean;
  subs: { id: string; label: string }[];
};
export const DASHBOARD_TABS: DashboardSection[] = [
  { id: 'resumen', label: 'Resumen', subtitle: 'Lo que requiere tu atención este periodo.', period: true, subs: [] },
  {
    id: 'empresas',
    label: 'Empresas',
    subtitle: 'Directorio y calidad de datos de tus empresas clientes.',
    period: false,
    subs: [
      { id: 'directorio', label: 'Directorio' },
      { id: 'calidad', label: 'Calidad de datos' },
    ],
  },
  {
    id: 'documentos',
    label: 'Documentos',
    subtitle: 'Vigencia y expedientes de FIEL, CSF y opiniones de cumplimiento.',
    period: false,
    subs: [
      { id: 'semaforo', label: 'Semáforo' },
      { id: 'opiniones', label: 'Opiniones' },
      { id: 'expedientes', label: 'Expedientes' },
    ],
  },
  {
    id: 'obligaciones',
    label: 'Obligaciones',
    subtitle: 'Obligaciones, CFDI y fechas límite del periodo.',
    period: true,
    subs: [
      { id: 'matriz', label: 'Matriz del mes' },
      { id: 'cfdi', label: 'Seguimiento CFDI' },
      { id: 'calendario', label: 'Calendario' },
    ],
  },
];
export const PASSWORD_MANAGER_PATH = '/gestor-contrasenas';
export const ALERTS_PATH = '/configuracion/alertas';
// Tabs and views before the Dashboard principal (and older names), kept so bookmarks and links still land.
const legacyTabs: Record<string, [DashboardTab, string] | string> = {
  Panel: ['resumen', ''],
  'Dashboard general': ['resumen', ''],
  'Resumen Ejecutivo': ['resumen', ''],
  'Opiniones de cumplimiento': ['documentos', 'opiniones'],
  'Seguimiento CFDI': ['obligaciones', 'cfdi'],
  'Calidad de datos': ['empresas', 'calidad'],
  Directorio: ['empresas', 'directorio'],
  Reportes: ['empresas', 'directorio'],
  Importar: ['empresas', 'importar'],
  'Importar y conciliar': ['empresas', 'importar'],
  Documentos: ['documentos', 'expedientes'],
  'Expedientes Digitales': ['documentos', 'expedientes'],
  expedientes: ['documentos', 'expedientes'],
  Obligaciones: ['obligaciones', 'matriz'],
  'Obligaciones Fiscales': ['obligaciones', 'matriz'],
  'Control de obligaciones': ['obligaciones', 'calendario'],
  Credenciales: PASSWORD_MANAGER_PATH,
  'Credenciales y Certificados': PASSWORD_MANAGER_PATH,
  'Centro de Alertas': ALERTS_PATH,
  'Tareas Operativas': '/tareas',
};
const legacyViews: Record<string, [DashboardTab, string] | string> = {
  General: ['resumen', ''],
  'Opiniones de cumplimiento': ['documentos', 'opiniones'],
  'Seguimiento CFDI': ['obligaciones', 'cfdi'],
  'Calidad de datos': ['empresas', 'calidad'],
  'Bandeja documental': ['documentos', 'expedientes'],
  'Expedientes por empresa': ['documentos', 'expedientes'],
  Certificados: PASSWORD_MANAGER_PATH,
  'Centro de alertas': ALERTS_PATH,
};
export type DashboardTarget = { tab: DashboardTab; sub: string; legacy?: boolean } | { redirect: string };
/** Tab and sub-tab of the URL. Old names land on their new place; an unknown tab or sub-tab falls to Resumen.
 *  `sub` is '' for Resumen and 'importar' for the importer opened from Empresas › Directorio. */
export function dashboardTarget(tab: string | null, sub?: string | null, vista?: string | null): DashboardTarget {
  const section = DASHBOARD_TABS.find((t) => t.id === tab);
  if (section) {
    if (!sub) return { tab: section.id, sub: section.subs[0]?.id || '' };
    if (section.id === 'empresas' && sub === 'importar') return { tab: 'empresas', sub };
    return section.subs.some((s) => s.id === sub) ? { tab: section.id, sub } : { tab: 'resumen', sub: '' };
  }
  if (!tab) return { tab: 'resumen', sub: '' };
  const fromView =
    vista && (tab === 'Panel' || tab === 'Documentos' || tab === 'Credenciales') ? legacyViews[vista] : undefined;
  const old = fromView || legacyTabs[tab];
  if (typeof old === 'string') return { redirect: old };
  if (old) return { tab: old[0], sub: old[1], legacy: true };
  return { tab: 'resumen', sub: '' };
}
export function dashboardUrl(tab: DashboardTab, sub = '', extra?: Record<string, string>) {
  const q = new URLSearchParams({ tab });
  if (sub) q.set('sub', sub);
  for (const [key, value] of Object.entries(extra || {})) if (value) q.set(key, value);
  return '/empresas?' + q;
}
export function dashboardCrumb(search: string) {
  const params = new URLSearchParams(search);
  const target = dashboardTarget(params.get('tab'), params.get('sub'), params.get('vista'));
  return 'redirect' in target ? '' : DASHBOARD_TABS.find((t) => t.id === target.tab)!.label;
}
export function directoryUrl(params: URLSearchParams) {
  const q = new URLSearchParams(params);
  q.set('tab', 'empresas');
  q.set('sub', 'directorio');
  q.delete('vista');
  return '/empresas?' + q;
}
