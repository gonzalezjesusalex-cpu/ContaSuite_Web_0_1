import { expect, test } from '@playwright/test';
import { login } from './helpers';

// Renovación del gestor, fase 1: the vault starts locked, the first time an administrator creates the master
// password and sees the recovery code once; «Bloquear ahora» hides every company and the code opens it again.
const master = 'Maestra-E2E-sintetica-2026';
const renewed = 'Otra-maestra-E2E-sintetica';

test('bóveda: crear, código de recuperación, bloquear y desbloquear', async ({ page }) => {
  await login(page);
  await page.goto('/gestor-contrasenas');
  const companies = page.getByRole('complementary', { name: 'Empresas del gestor' });
  await expect(page.getByRole('heading', { name: 'Crea la contraseña maestra' })).toBeVisible();
  await expect(companies).toHaveCount(0);
  await page.getByRole('textbox', { name: /^Contraseña maestra/ }).fill('corta');
  await expect(page.getByRole('button', { name: 'Crear la bóveda' })).toBeDisabled();
  await page.getByRole('textbox', { name: /^Contraseña maestra/ }).fill(master);
  await page.getByRole('textbox', { name: /^Confirma la contraseña/ }).fill(master);
  await page.getByRole('button', { name: 'Crear la bóveda' }).click();

  await expect(page.getByRole('heading', { name: 'Guarda tu código de recuperación' })).toBeVisible();
  const code = (await page.getByLabel('Código de recuperación', { exact: true }).textContent())!.trim();
  expect(code).toMatch(/^([A-Z2-9]{4}-){5}[A-Z2-9]{4}$/);
  await expect(page.getByRole('button', { name: 'Continuar al gestor' })).toBeDisabled();
  await page.getByLabel('Ya lo imprimí o lo guardé').check();
  await page.getByRole('button', { name: 'Continuar al gestor' }).click();

  await expect(page.getByText(/Desbloqueado · se bloquea en \d+:\d\d/)).toBeVisible();
  await expect(companies).toBeVisible();

  await page.getByRole('button', { name: 'Bloquear ahora' }).click();
  await expect(page.getByRole('heading', { name: 'La bóveda está bloqueada' })).toBeVisible();
  await expect(companies).toHaveCount(0);
  await page.getByLabel('Contraseña maestra').fill('no-es-la-maestra');
  await page.getByRole('button', { name: 'Desbloquear' }).click();
  await expect(page.getByRole('alert')).toContainText('no es correcta');

  await page.getByRole('button', { name: /código de recuperación/ }).click();
  await page.getByLabel('Código de recuperación', { exact: true }).fill(code.toLowerCase());
  await page.getByRole('button', { name: 'Desbloquear' }).click();
  await expect(page.getByRole('heading', { name: 'Elige tu contraseña maestra' })).toBeVisible();
  await page.getByRole('textbox', { name: /^Contraseña maestra/ }).fill(renewed);
  await page.getByRole('textbox', { name: /^Confirma la contraseña/ }).fill(renewed);
  await page.getByRole('button', { name: 'Guardar contraseña maestra' }).click();
  await expect(companies).toBeVisible();

  await page.getByRole('button', { name: 'Bloquear ahora' }).click();
  await page.getByLabel('Contraseña maestra').fill(renewed);
  await page.getByRole('button', { name: 'Desbloquear' }).click();
  await expect(page.getByText(/Desbloqueado · se bloquea en/)).toBeVisible();

  // Fase 3: «Agregar FIEL o CSD» asks whose signature it is and saves nothing until every check passes.
  await page.getByRole('button', { name: 'Agregar FIEL o CSD' }).click();
  const dialog = page.getByRole('dialog', { name: 'Agregar FIEL o CSD' });
  for (const option of ['FIEL de la empresa', 'FIEL del representante', 'Sello digital (CSD)'])
    await expect(dialog.getByRole('radio', { name: option })).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'Guardar' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Cancelar' }).click();
  await expect(dialog).toHaveCount(0);
});
