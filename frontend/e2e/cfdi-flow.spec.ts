import { expect, test } from '@playwright/test';
import { company, expectNoOverflow, login, sidebar } from './helpers';
import { cfdi, other, pdf, uuid, zip } from './synthetic';

// Flujo CFDI con datos sintéticos: analizar un ZIP, contrastar con el expediente, guardar y ver Por revisar › CFDI.
// Todo el contenido lo inventa esta prueba (RFC y UUID ficticios). E2E_SHOTS (opcional) es una carpeta donde se
// guardan capturas para la revisión visual.
const shots = process.env.E2E_SHOTS;
test('CFDI: analizar, contrastar con el expediente, guardar y revisar bloqueados', async ({ page }) => {
  const emitidos = `Base/Emitidos/${company.rfc}/2026-04/`;
  const recibidos = `Base/Recibidos/${company.rfc}/2026-04/`;
  const buffer = zip({
    [emitidos + 'ok.xml']: cfdi(uuid(1), company.rfc, other, '2026-04-10'),
    [emitidos + 'ok.pdf']: pdf('Factura ' + uuid(1)),
    [emitidos + 'mes.xml']: cfdi(uuid(2), company.rfc, other, '2026-05-02'), // fechado en mayo, archivado en abril
    [recibidos + 'ajena.xml']: cfdi(uuid(3), other, other, '2026-04-10'), // el receptor no es la empresa
    [recibidos + 'sinpdf.xml']: cfdi(uuid(4), other, company.rfc, '2026-04-10'),
  });

  await login(page);
  await sidebar(page, 'CFDI');
  await page.getByLabel('Empresa (opcional)').selectOption({ label: `${company.name} · ${company.rfc}` });
  await page
    .locator('input[type=file][accept=".zip"]')
    .setInputFiles({ name: 'cfdi-sintetico.zip', mimeType: 'application/zip', buffer });
  await expect(page.getByLabel('RFC de origen')).toHaveValue(company.rfc);
  await page.getByLabel('Ejercicio').fill('2026');
  await page.getByRole('button', { name: 'Todos', exact: true }).click();
  await page.getByRole('button', { name: 'Analizar origen' }).click();
  const contrast = page.getByRole('button', { name: 'Revisar contra el expediente' });
  await expect(contrast).toBeEnabled({ timeout: 30_000 });
  await expect(page.getByText('Pareja XML–PDF identificada').first()).toBeVisible();
  await expect(page.getByText('Fecha fuera del mes de la carpeta')).toBeVisible();
  await expect(page.getByText('Receptor distinto a la empresa')).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/cfdi-1-analisis.png', fullPage: true });
  await contrast.click();
  await expect(page.getByRole('status').filter({ hasText: '2 bloqueados' })).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/cfdi-2-contraste.png', fullPage: true });
  await expectNoOverflow(page, 'cfdi-contraste');
  await page.getByRole('button', { name: 'Guardar en expediente' }).click();
  await expect(page.getByText('Guardado en el expediente.')).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/cfdi-3-guardado.png', fullPage: true });

  await sidebar(page, 'Empresas');
  await page.getByRole('button', { name: /^Directorio/ }).click();
  await page.getByRole('link', { name: 'Abrir ' + company.name }).click();
  await page
    .getByRole('button', { name: /^Documentos/ })
    .first()
    .click();
  await page.getByRole('button', { name: /^Por revisar/ }).click();
  await page.getByRole('button', { name: /^CFDI 2$/ }).click();
  await expect(page.getByRole('heading', { name: 'CFDI', exact: true })).toBeVisible();
  await expect(page.getByText('CFDI Abr 2026: 2 XML · 1 PDF · 2 en revisión')).toBeVisible();
  await expectNoOverflow(page, 'cfdi-por-revisar');
  if (shots) await page.screenshot({ path: shots + '/cfdi-4-por-revisar.png', fullPage: true });
});
