import { expect, test } from '@playwright/test';
import { company, login, sidebar } from './helpers';
import { cfdi, other, pdf, uuid, zip } from './synthetic';

// Recopila con datos sintéticos, parte 2: ajustes manuales, aviso de formato no compatible y «Usar documentos de la
// empresa». Todo el contenido lo inventa esta prueba. E2E_SHOTS (opcional) guarda capturas para la revisión visual.
const shots = process.env.E2E_SHOTS;

test('Recopila: asociar un sobrante, deshacer el ajuste y avisar de un formato no compatible', async ({ page }) => {
  const buffer = zip({
    // La póliza cita el UUID 1, pero su comprobante no viene en la carga: queda parcial.
    'Polizas/compra.pdf': pdf(
      'IMPRESO DE POLIZAS',
      'Compra (Egreso)',
      'Fecha 05/10/2026',
      'Descripcion Compra ajustes',
      'CFDI asociados a la poliza',
      uuid(1),
    ),
    // Comprobante completo que ninguna póliza cita: sobrante que se puede asociar a mano.
    [`CFDI/${uuid(2)}.xml`]: cfdi(uuid(2), other, company.rfc, '2026-10-02'),
    [`CFDI/${uuid(2)}.pdf`]: pdf('Comprobante sobrante'),
    // Páginas con aspecto de póliza en un formato que el motor no lee: sólo se detectan, nunca se interpretan.
    'Otros/contalink.pdf': pdf('Contalink', 'Poliza de diario', 'Cuenta Debe Haber'),
  });

  await login(page);
  await sidebar(page, 'Recopila');
  await page.getByLabel('Empresa (opcional)').selectOption({ label: `${company.name} · ${company.rfc}` });
  await page
    .locator('input[type=file][accept=".zip"]')
    .setInputFiles({ name: 'ajustes.zip', mimeType: 'application/zip', buffer });
  await page.getByRole('button', { name: 'Analizar documentos' }).click();
  await expect(page.getByRole('heading', { name: 'Revisión de pólizas' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/^1 página parece una póliza en un formato no compatible/)).toBeVisible();
  await expect(page.getByText(/Aún no se leen/)).toBeVisible();

  await page.getByRole('button', { name: /Compra ajustes/ }).click();
  await expect(page.getByRole('heading', { name: 'Detalle de la póliza' })).toBeVisible();
  await page.getByText('Asociar un sobrante a esta póliza').click();
  await page.getByRole('button', { name: 'Asociar', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Ajustes manuales' })).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/recopila-5-ajuste.png', fullPage: true });

  await page.getByRole('button', { name: 'Revertir' }).click();
  await expect(page.getByText(/· revertido/)).toBeVisible();
});

test('Recopila: usar documentos de la empresa registrados en el Centro Documental', async ({ page }) => {
  await login(page);
  // Registra dos originales sintéticos de octubre 2026 por la API de almacenamiento, como lo haría la pantalla.
  const base = new URL(page.url()).origin;
  const csrf = decodeURIComponent(
    (await page.context().cookies()).find((c) => c.name === 'contasuite_csrf')?.value ?? '',
  );
  const state = await (await page.request.get('/api/state')).json();
  const mine = state.companies.find((c: { rfc: string }) => c.rfc === company.rfc);
  for (const [name, mimeType, buffer] of [
    ['empresa-oct.xml', 'application/xml', cfdi(uuid(7), other, company.rfc, '2026-10-03')],
    ['empresa-oct.pdf', 'application/pdf', pdf('Factura ' + uuid(7))],
  ] as const) {
    const reply = await page.request.post('/api/storage/documents', {
      headers: { Origin: base, 'X-CSRF-Token': csrf },
      multipart: { company_id: mine.id, period: '2026-10', file: { name, mimeType, buffer } },
    });
    expect(reply.ok(), await reply.text()).toBeTruthy();
  }

  await sidebar(page, 'Recopila');
  await page.getByLabel('Empresa (opcional)').selectOption({ label: `${company.name} · ${company.rfc}` });
  await page.getByLabel('Periodo de los documentos de la empresa').fill('2026-10');
  await page.getByRole('button', { name: 'Usar documentos de la empresa' }).click();
  await expect(page.getByText('Documentos de la empresa cargados. Comenzó el análisis.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Revisión de pólizas' })).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/recopila-6-documentos-empresa.png', fullPage: true });
});
