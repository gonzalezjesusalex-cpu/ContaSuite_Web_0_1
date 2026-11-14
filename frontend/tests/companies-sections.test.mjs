import assert from 'node:assert/strict';
import { test } from 'node:test';
import { companiesSection, companiesSections, companiesUrl, companiesViews } from '../src/companyNavigation.ts';

const legacy = {
  'Dashboard general': ['Panel', 'General'],
  'Opiniones de cumplimiento': ['Panel', 'Opiniones de cumplimiento'],
  'Seguimiento CFDI': ['Panel', 'Seguimiento CFDI'],
  'Calidad de datos': ['Panel', 'Calidad de datos'],
  Directorio: ['Directorio', ''],
  'Importar y conciliar': ['Importar', ''],
  'Credenciales y Certificados': ['Credenciales', 'Certificados'],
  'Centro de Alertas': ['Credenciales', 'Centro de alertas'],
  'Control de obligaciones': ['Obligaciones', ''],
  'Obligaciones Fiscales': ['Obligaciones', ''],
  'Expedientes Digitales': ['Documentos', 'Expedientes por empresa'],
  Documentos: ['Documentos', 'Bandeja documental'],
  Reportes: ['Directorio', ''],
  'Resumen Ejecutivo': ['Panel', 'General'],
};

test('every former Empresas tab lands on its new section and view', () => {
  for (const [tab, [section, view]] of Object.entries(legacy))
    assert.deepEqual(companiesSection(tab), { section, view }, tab);
});

test('former operational tasks tab redirects to the tasks page', () => {
  assert.deepEqual(companiesSection('Tareas Operativas'), { redirect: '/tareas' });
});

test('old lowercase query aliases keep working', () => {
  assert.deepEqual(companiesSection('expedientes'), { section: 'Documentos', view: 'Expedientes por empresa' });
  assert.deepEqual(companiesSection('documentos'), { section: 'Documentos', view: 'Bandeja documental' });
});

test('new sections accept their own views and fall back to the first one', () => {
  assert.equal(companiesSections.length, 6);
  for (const section of companiesSections) {
    const views = companiesViews[section] || [''];
    for (const view of views) assert.deepEqual(companiesSection(section, view), { section, view });
    assert.deepEqual(companiesSection(section, 'invalid'), { section, view: views[0] });
  }
});

test('missing or unknown tab opens the panel', () => {
  assert.deepEqual(companiesSection(null), { section: 'Panel', view: 'General' });
  assert.deepEqual(companiesSection('invalid', 'Seguimiento CFDI'), { section: 'Panel', view: 'Seguimiento CFDI' });
});

test('section urls carry the view only when there is one', () => {
  assert.equal(companiesUrl('Obligaciones'), '/empresas?tab=Obligaciones');
  const url = new URL(companiesUrl('Documentos', 'Expedientes por empresa'), 'http://synthetic');
  assert.equal(url.searchParams.get('tab'), 'Documentos');
  assert.equal(url.searchParams.get('vista'), 'Expedientes por empresa');
});
