import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';
import { company, password as passwordOf, sidebar, user } from './helpers';

// Minimal end-to-end smoke test against a throwaway synthetic server (scripts/e2e_server.py):
// first access, login, companies, dossier, and document upload/download. No real data is involved.
const password = passwordOf();
const pdf = Buffer.from('%PDF-1.4\nContaSuite E2E sintético\n%%EOF\n');

test('primer acceso, sesión, empresas, expediente y documentos', async ({ page }) => {
  await test.step('primer acceso crea la cuenta administradora', async () => {
    await page.goto('/');
    await expect(page.getByText('Crea la cuenta administradora del despacho.')).toBeVisible();
    await page.getByLabel('Clave de instalación').fill(process.env.E2E_APP_TOKEN!);
    await page.getByLabel('Nombre').fill('QA E2E');
    await page.getByLabel('Usuario').fill(user);
    await page.getByLabel('Contraseña').fill(password);
    await page.getByRole('button', { name: 'Crear cuenta e ingresar' }).click();
    await expect(page.getByText('Bienvenido a ContaSuite')).toBeVisible();
  });

  await test.step('cerrar sesión e iniciar de nuevo', async () => {
    await page.getByRole('button', { name: 'Cerrar sesión' }).click();
    await expect(page.getByText('Inicia sesión con tu cuenta.')).toBeVisible();
    await page.getByLabel('Usuario').fill(user);
    await page.getByLabel('Contraseña').fill('contraseña-incorrecta');
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();
    await expect(page.getByRole('alert')).toBeVisible();
    await page.getByLabel('Contraseña').fill(password);
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();
    await expect(page.getByText('Bienvenido a ContaSuite')).toBeVisible();
  });

  await test.step('registrar una empresa y verla en el directorio', async () => {
    await sidebar(page, 'Empresas');
    await expect(page.getByRole('heading', { name: 'Centro de Control Fiscal' })).toBeVisible();
    await page.getByRole('link', { name: 'Registrar empresa' }).first().click();
    await page.getByLabel('RFC *').fill(company.rfc);
    await page.getByLabel('Razón social / Nombre completo *').fill(company.name);
    await page.getByRole('button', { name: 'Siguiente →' }).click();
    await page.getByRole('button', { name: 'Siguiente →' }).click();
    await page.getByRole('button', { name: 'Guardar y dar de alta' }).click();
    // The form's summary card already shows the name, so wait for the dossier route itself.
    await expect(page).toHaveURL(/\/empresas\/[0-9a-f-]{36}(\?|$)/);
    await expect(page.getByRole('heading', { level: 1, name: company.name })).toBeVisible();
    await sidebar(page, 'Empresas');
    await page.getByRole('button', { name: /^Directorio/ }).click();
    await expect(page.getByRole('cell', { name: company.rfc })).toBeVisible();
  });

  await test.step('abrir el expediente desde el directorio', async () => {
    await page.getByRole('link', { name: 'Abrir ' + company.name }).click();
    await expect(page.getByRole('heading', { level: 1, name: company.name })).toBeVisible();
    await page
      .getByRole('button', { name: /^Documentos/ })
      .first()
      .click();
    await expect(page.getByRole('button', { name: 'Cargar documento' })).toBeVisible();
  });

  await test.step('subir un PDF y descargarlo íntegro', async () => {
    await page.getByRole('button', { name: 'Cargar documento' }).click();
    const dialog = page.getByRole('dialog', { name: 'Cargar documento' });
    await dialog
      .locator('input[type=file]')
      .setInputFiles({ name: 'acuse-e2e.pdf', mimeType: 'application/pdf', buffer: pdf });
    await dialog.getByRole('button', { name: 'Guardar documento' }).click();
    await expect(dialog).toBeHidden();
    const downloadButton = page.getByRole('button', { name: 'Descargar acuse-e2e.pdf' }).first();
    await expect(downloadButton).toBeVisible();
    const [download] = await Promise.all([page.waitForEvent('download'), downloadButton.click()]);
    expect(download.suggestedFilename()).toBe('acuse-e2e.pdf');
    expect(Buffer.compare(await readFile(await download.path()), pdf)).toBe(0);
  });
});
