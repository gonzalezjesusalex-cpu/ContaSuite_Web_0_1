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
  for (const key of ['query', 'accountant', 'status', 'archive', 'sort']) {
    const value = context?.get(key);
    if (value) q.set(key, value);
  }
  return '/empresas/' + encodeURIComponent(id) + '?' + q;
}
// Office-wide Empresas page: six sections, some with internal views (`vista` query parameter).
export const companiesSections = ['Panel', 'Directorio', 'Documentos', 'Obligaciones', 'Credenciales', 'Importar'];
export const companiesViews: Record<string, string[]> = {
  Panel: ['General', 'Opiniones de cumplimiento', 'Seguimiento CFDI', 'Calidad de datos'],
  Documentos: ['Bandeja documental', 'Expedientes por empresa'],
  Credenciales: ['Certificados', 'Centro de alertas'],
};
// Tab names used before the reorganization, kept so bookmarks and existing links still land.
const legacyCompaniesTabs: Record<string, [string, string]> = {
  'Dashboard general': ['Panel', 'General'],
  'Resumen Ejecutivo': ['Panel', 'General'],
  'Opiniones de cumplimiento': ['Panel', 'Opiniones de cumplimiento'],
  'Seguimiento CFDI': ['Panel', 'Seguimiento CFDI'],
  'Calidad de datos': ['Panel', 'Calidad de datos'],
  Reportes: ['Directorio', ''],
  'Importar y conciliar': ['Importar', ''],
  'Credenciales y Certificados': ['Credenciales', 'Certificados'],
  'Centro de Alertas': ['Credenciales', 'Centro de alertas'],
  'Control de obligaciones': ['Obligaciones', ''],
  'Obligaciones Fiscales': ['Obligaciones', ''],
  documentos: ['Documentos', 'Bandeja documental'],
  'Expedientes Digitales': ['Documentos', 'Expedientes por empresa'],
  expedientes: ['Documentos', 'Expedientes por empresa'],
};
export type CompaniesTarget = { section: string; view: string } | { redirect: string };
export function companiesSection(tab: string | null, vista?: string | null): CompaniesTarget {
  if (tab === 'Tareas Operativas') return { redirect: '/tareas' };
  const legacy = tab ? legacyCompaniesTabs[tab] : undefined;
  const section = legacy ? legacy[0] : companiesSections.includes(tab || '') ? tab! : 'Panel';
  const views = companiesViews[section] || [];
  const view = legacy?.[1] || (views.includes(vista || '') ? vista! : views[0] || '');
  return { section, view };
}
export function companiesUrl(section: string, view = '') {
  const q = new URLSearchParams({ tab: section });
  if (view) q.set('vista', view);
  return '/empresas?' + q;
}
export function directoryUrl(params: URLSearchParams) {
  const q = new URLSearchParams(params);
  q.set('tab', 'Directorio');
  return '/empresas?' + q;
}
