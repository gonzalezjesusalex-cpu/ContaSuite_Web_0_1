import { expect, test } from '@playwright/test';
import { company, login, sidebar } from './helpers';
import { cfdi, pdf, uuid, zip } from './synthetic';

// Flujo Recopila con datos sintéticos: analizar pólizas y CFDI, generar archivos y guardarlos en el expediente.
// Todo el contenido lo inventa esta prueba. E2E_SHOTS (opcional) guarda capturas para la revisión visual.
const shots = process.env.E2E_SHOTS;

test('Recopila: analizar, generar y guardar en el expediente', async ({ page }) => {
  const buffer = zip({
    'Polizas/compra.pdf': pdf(
      'IMPRESO DE POLIZAS',
      'Compra (Egreso)',
      'Fecha 05/10/2026',
      'Descripcion Compra prueba',
      'CFDI asociados a la poliza',
      uuid(1),
    ),
    'Polizas/diario.pdf': pdf('IMPRESO DE POLIZAS', 'Diario (Manual)', 'Fecha 03/11/2026', 'Descripcion Ajuste prueba'),
    [`CFDI/${uuid(1)}.xml`]: cfdi(uuid(1), 'BBB020202BB2', company.rfc, '2026-10-01'),
    [`CFDI/${uuid(1)}.pdf`]: pdf('Comprobante relacionado'),
    [`CFDI/${uuid(2)}.xml`]: cfdi(uuid(2), 'BBB020202BB2', company.rfc, '2026-10-02'),
    [`CFDI/${uuid(2)}.pdf`]: pdf('Comprobante sobrante'),
  });

  await login(page);
  await sidebar(page, 'Recopila');
  await page.getByLabel('Empresa (opcional)').selectOption({ label: `${company.name} · ${company.rfc}` });
  await page
    .locator('input[type=file][accept=".zip"]')
    .setInputFiles({ name: 'documentos.zip', mimeType: 'application/zip', buffer });
  await page.getByRole('button', { name: 'Analizar documentos' }).click();
  await expect(page.getByRole('heading', { name: 'Revisión de pólizas' })).toBeVisible({ timeout: 30_000 });
  if (shots) await page.screenshot({ path: shots + '/recopila-1-revision.png', fullPage: true });

  await page.getByRole('button', { name: 'Generar archivos' }).click();
  await expect(page.getByRole('button', { name: 'Descargar todos (ZIP)' })).toBeVisible({ timeout: 60_000 });
  if (shots) await page.screenshot({ path: shots + '/recopila-2-generado.png', fullPage: true });

  page.once('dialog', (dialog) => void dialog.accept());
  await page.getByRole('button', { name: 'Guardar en expediente' }).click();
  await expect(page.getByText('Guardado en el expediente.')).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/recopila-3-guardado.png', fullPage: true });

  await sidebar(page, 'Empresas');
  await page.getByRole('button', { name: /^Directorio/ }).click();
  await page.getByRole('link', { name: 'Abrir ' + company.name }).click();
  await page
    .getByRole('button', { name: /^Documentos/ })
    .first()
    .click();
  await page.getByRole('button', { name: /^Por revisar/ }).click();
  await expect(page.getByRole('button', { name: /^Recopila \d+$/ })).toBeVisible();
  await expect(page.getByText(/1 factura sin póliza/)).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/recopila-4-expediente.png', fullPage: true });
});
