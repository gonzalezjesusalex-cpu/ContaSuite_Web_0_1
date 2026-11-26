import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  ALERTS_PATH,
  DASHBOARD_TABS,
  PASSWORD_MANAGER_PATH,
  dashboardCrumb,
  dashboardTarget,
  dashboardUrl,
  directoryUrl,
} from '../src/companyNavigation.ts';

test('the Dashboard principal has four tabs with their sub-tabs, Resumen first', () => {
  assert.deepEqual(
    DASHBOARD_TABS.map((t) => [t.id, t.subs.map((s) => s.id)]),
    [
      ['resumen', []],
      ['empresas', ['directorio', 'calidad']],
      ['documentos', ['semaforo', 'opiniones', 'expedientes']],
      ['obligaciones', ['matriz', 'cfdi', 'calendario']],
    ],
  );
  // Only Resumen and Obligaciones depend on the period.
  assert.deepEqual(
    DASHBOARD_TABS.filter((t) => t.period).map((t) => t.id),
    ['resumen', 'obligaciones'],
  );
});

test('every tab and sub-tab of the URL opens itself; a missing sub-tab opens the first one', () => {
  for (const tab of DASHBOARD_TABS) {
    for (const sub of tab.subs) assert.deepEqual(dashboardTarget(tab.id, sub.id), { tab: tab.id, sub: sub.id });
    assert.deepEqual(dashboardTarget(tab.id, null), { tab: tab.id, sub: tab.subs[0]?.id || '' });
  }
  assert.deepEqual(dashboardTarget('empresas', 'importar'), { tab: 'empresas', sub: 'importar' });
});

test('an invalid tab or sub-tab falls back to Resumen', () => {
  // The new ids are lower case: the old «documentos» alias is now the Documentos tab itself.
  assert.deepEqual(dashboardTarget('documentos'), { tab: 'documentos', sub: 'semaforo' });
  assert.deepEqual(dashboardTarget(null), { tab: 'resumen', sub: '' });
  assert.deepEqual(dashboardTarget('inexistente'), { tab: 'resumen', sub: '' });
  assert.deepEqual(dashboardTarget('obligaciones', 'inexistente'), { tab: 'resumen', sub: '' });
  assert.deepEqual(dashboardTarget('resumen', 'matriz'), { tab: 'resumen', sub: '' });
  assert.deepEqual(dashboardTarget('documentos', 'importar'), { tab: 'resumen', sub: '' });
});

const legacy = [
  [
    ['Panel', 'General'],
    ['resumen', ''],
  ],
  [
    ['Panel', 'Opiniones de cumplimiento'],
    ['documentos', 'opiniones'],
  ],
  [
    ['Panel', 'Seguimiento CFDI'],
    ['obligaciones', 'cfdi'],
  ],
  [
    ['Panel', 'Calidad de datos'],
    ['empresas', 'calidad'],
  ],
  [
    ['Panel', null],
    ['resumen', ''],
  ],
  [
    ['Directorio', null],
    ['empresas', 'directorio'],
  ],
  [
    ['Documentos', 'Bandeja documental'],
    ['documentos', 'expedientes'],
  ],
  [
    ['Documentos', 'Expedientes por empresa'],
    ['documentos', 'expedientes'],
  ],
  [
    ['Obligaciones', null],
    ['obligaciones', 'matriz'],
  ],
  [
    ['Importar', null],
    ['empresas', 'importar'],
  ],
  [
    ['Dashboard general', null],
    ['resumen', ''],
  ],
  [
    ['Resumen Ejecutivo', null],
    ['resumen', ''],
  ],
  [
    ['Opiniones de cumplimiento', null],
    ['documentos', 'opiniones'],
  ],
  [
    ['Seguimiento CFDI', null],
    ['obligaciones', 'cfdi'],
  ],
  [
    ['Calidad de datos', null],
    ['empresas', 'calidad'],
  ],
  [
    ['Reportes', null],
    ['empresas', 'directorio'],
  ],
  [
    ['Importar y conciliar', null],
    ['empresas', 'importar'],
  ],
  [
    ['Control de obligaciones', null],
    ['obligaciones', 'calendario'],
  ],
  [
    ['Obligaciones Fiscales', null],
    ['obligaciones', 'matriz'],
  ],
  [
    ['Expedientes Digitales', null],
    ['documentos', 'expedientes'],
  ],
  [
    ['expedientes', null],
    ['documentos', 'expedientes'],
  ],
];

test('every former tab and view lands on its new tab and sub-tab', () => {
  for (const [[tab, vista], [next, sub]] of legacy)
    assert.deepEqual(dashboardTarget(tab, null, vista), { tab: next, sub, legacy: true }, `${tab} › ${vista}`);
});

test('Credenciales, alerts and tasks leave the dashboard', () => {
  assert.deepEqual(dashboardTarget('Credenciales'), { redirect: PASSWORD_MANAGER_PATH });
  assert.deepEqual(dashboardTarget('Credenciales', null, 'Certificados'), { redirect: PASSWORD_MANAGER_PATH });
  assert.deepEqual(dashboardTarget('Credenciales y Certificados'), { redirect: PASSWORD_MANAGER_PATH });
  assert.deepEqual(dashboardTarget('Credenciales', null, 'Centro de alertas'), { redirect: ALERTS_PATH });
  assert.deepEqual(dashboardTarget('Centro de Alertas'), { redirect: ALERTS_PATH });
  assert.deepEqual(dashboardTarget('Tareas Operativas'), { redirect: '/tareas' });
  assert.equal(PASSWORD_MANAGER_PATH, '/gestor-contrasenas');
  assert.equal(ALERTS_PATH, '/configuracion/alertas');
});

test('urls keep the tab and sub-tab in the query and the breadcrumb names the tab', () => {
  assert.equal(dashboardUrl('obligaciones', 'cfdi'), '/empresas?tab=obligaciones&sub=cfdi');
  assert.equal(dashboardUrl('resumen'), '/empresas?tab=resumen');
  const url = new URL(dashboardUrl('documentos', 'semaforo', { doc: 'csf', estado: 'red', vacio: '' }), 'http://x');
  assert.deepEqual(Object.fromEntries(url.searchParams), {
    tab: 'documentos',
    sub: 'semaforo',
    doc: 'csf',
    estado: 'red',
  });
  assert.equal(dashboardCrumb('?tab=obligaciones&sub=cfdi'), 'Obligaciones');
  assert.equal(dashboardCrumb(''), 'Resumen');
  assert.equal(dashboardCrumb('?tab=Panel&vista=Calidad+de+datos'), 'Empresas');
  assert.equal(dashboardCrumb('?tab=Credenciales'), '');
  const back = new URL(directoryUrl(new URLSearchParams('tab=Panel&vista=General&query=ark')), 'http://x');
  assert.deepEqual(Object.fromEntries(back.searchParams), { tab: 'empresas', query: 'ark', sub: 'directorio' });
});
