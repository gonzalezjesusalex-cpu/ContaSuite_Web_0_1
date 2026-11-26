import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  ALERT_TYPES,
  alertHref,
  alertText,
  alertType,
  dossierHref,
  relativeTime,
  severityOf,
} from '../src/alertTypes.ts';

test('the documented alert types have their Spanish text and direct action', () => {
  assert.deepEqual(alertType('missing_responsible'), {
    text: 'Sin responsable asignado',
    action: 'Asignar',
    target: 'editar',
  });
  assert.deepEqual(alertType('document_pending_classification'), {
    text: 'Documento sin clasificar',
    action: 'Clasificar',
    target: 'documentos',
  });
  assert.deepEqual(alertType('evidence_review'), {
    text: 'Evidencia por revisar',
    action: 'Revisar',
    target: 'obligaciones',
  });
});

test('every known type is in Spanish and never repeats its internal code', () => {
  for (const [code, type] of Object.entries(ALERT_TYPES)) {
    assert.notEqual(type.text, code);
    assert.doesNotMatch(type.text, /_/, code);
    assert.ok(type.action.length > 0, code);
  }
});

test('certificate kinds are translated from their pattern', () => {
  assert.equal(alertText('fiel_expired_0'), 'FIEL vencida');
  assert.equal(alertText('csd_expired_0'), 'Sello digital (CSD) vencido');
  assert.equal(alertText('fiel_expiring_15'), 'FIEL por vencer (15 días o menos)');
  assert.equal(alertType('csd_expiring_30').action, 'Renovar');
  assert.equal(alertText('unknown_unknown_0'), 'Certificado sin fechas de vigencia');
  assert.equal(alertText('fiel_pending_verification_0'), 'FIEL con vigencia aún no iniciada');
});

test('an unknown type shows a generic text and opens the dossier, never the code', () => {
  for (const code of ['nuevo_codigo_interno', '', 'fiel_expired']) {
    assert.deepEqual(alertType(code), {
      text: 'Alerta del expediente',
      action: 'Abrir expediente',
      target: 'expediente',
    });
  }
  const alert = { kind: 'nuevo_codigo_interno', source: 'quality', company_id: 'c 1', reference: 'r' };
  assert.equal(alertHref(alert), '/empresas/c%201');
  assert.equal(dossierHref({ ...alert, kind: 'missing_responsible' }), '/empresas/c%201');
});

test('direct actions lead to the screen that fixes the condition', () => {
  const at = (kind) => alertHref({ kind, source: 'quality', company_id: 'c1', reference: 'r' });
  assert.equal(at('missing_responsible'), '/empresas/c1/editar');
  assert.equal(at('document_pending_classification'), '/empresas/c1?tab=Documentos');
  assert.equal(at('overdue'), '/empresas/c1?tab=Obligaciones');
  assert.equal(at('fiel_expired_0'), '/empresas/c1?tab=FIEL/CSD');
});

test('severity maps low, medium and high to Baja, Media and Alta', () => {
  assert.deepEqual(severityOf('low'), { label: 'Baja', tone: 'neutral' });
  assert.deepEqual(severityOf('medium'), { label: 'Media', tone: 'amber' });
  assert.deepEqual(severityOf('high'), { label: 'Alta', tone: 'red' });
  assert.equal(severityOf('otra').label, 'Baja');
});

test('detection time is relative in Spanish', () => {
  const now = Date.parse('2026-11-26T12:00:00Z');
  assert.equal(relativeTime('2026-11-24T12:00:00Z', now), 'anteayer');
  assert.equal(relativeTime('2026-11-19T12:00:00', now), 'la semana pasada');
  assert.equal(relativeTime('2026-11-26T11:59:40Z', now), 'hace un momento');
  assert.equal(relativeTime(null, now), 'Sin fecha');
});
