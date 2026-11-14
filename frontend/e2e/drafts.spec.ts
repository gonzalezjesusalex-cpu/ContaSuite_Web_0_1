import { expect, test } from '@playwright/test';
import { answerNextConfirm, company, forbidDialogs, login, sidebar } from './helpers';

// Unsaved-changes guards in the real browser (plan, point 24): cancelling keeps the user and the typed
// values where they were; accepting discards and continues without asking again.
test.beforeEach(async ({ page }) => {
  await login(page);
});

test('enlace del menú con un formulario de alta modificado', async ({ page }) => {
  await sidebar(page, 'Empresas');
  await page.getByRole('link', { name: 'Registrar empresa' }).first().click();
  const name = page.getByLabel('Razón social / Nombre completo *');
  await name.fill('Borrador sin guardar');

  const asked = answerNextConfirm(page, false);
  await sidebar(page, 'Inicio');
  await expect.poll(() => asked.length).toBe(1);
  await expect(page).toHaveURL(/\/empresas\/nueva$/);
  await expect(name).toHaveValue('Borrador sin guardar');

  const accepted = answerNextConfirm(page, true);
  await sidebar(page, 'Inicio');
  await expect.poll(() => accepted.length).toBe(1);
  await expect(page.getByText('Bienvenido a ContaSuite')).toBeVisible();
  const stop = forbidDialogs(page);
  await sidebar(page, 'Empresas');
  await expect(page.getByRole('heading', { name: 'Centro de Control Fiscal' })).toBeVisible();
  stop();
});

test('botón Atrás del navegador', async ({ page }) => {
  await sidebar(page, 'Empresas');
  await page.getByRole('link', { name: 'Registrar empresa' }).first().click();
  const rfc = page.getByLabel('RFC *');
  await rfc.fill('BOR010101AB1');

  const asked = answerNextConfirm(page, false);
  await page.goBack();
  await expect.poll(() => asked.length).toBe(1);
  await expect(page).toHaveURL(/\/empresas\/nueva$/);
  await expect(rfc).toHaveValue('BOR010101AB1');

  const accepted = answerNextConfirm(page, true);
  await page.goBack();
  await expect.poll(() => accepted.length).toBe(1);
  await expect(page).toHaveURL(/\/empresas(\?|$)/);
});

test('cambio de sección con un formulario fijo modificado', async ({ page }) => {
  await sidebar(page, 'Tareas y vencimientos');
  await page.getByRole('button', { name: 'Calendario fiscal' }).click();
  // The manual-date form appears once an authorized company is chosen.
  await page.getByLabel('Empresa autorizada').selectOption({ label: company.name });
  const title = page.getByRole('textbox', { name: 'Título' }).first();
  await title.fill('Fecha manual sin guardar');

  const asked = answerNextConfirm(page, false);
  await page.getByRole('button', { name: 'Tareas', exact: true }).click();
  await expect.poll(() => asked.length).toBe(1);
  await expect(page).toHaveURL(/tab=calendario/);
  await expect(title).toHaveValue('Fecha manual sin guardar');

  const accepted = answerNextConfirm(page, true);
  await page.getByRole('button', { name: 'Tareas', exact: true }).click();
  await expect.poll(() => accepted.length).toBe(1);
  await expect(page).toHaveURL(/tab=tareas/);
});

test('cierre de un diálogo con cambios: Escape, botón Cerrar y clic fuera', async ({ page }) => {
  await sidebar(page, 'Empresas');
  await page.getByRole('button', { name: /^Directorio/ }).click();
  await page.getByRole('link', { name: 'Abrir ' + company.name }).click();
  await page
    .getByRole('button', { name: /^Documentos/ })
    .first()
    .click();
  await page.getByRole('button', { name: 'Cargar documento' }).click();
  const dialog = page.getByRole('dialog', { name: 'Cargar documento' });
  const period = dialog.getByLabel('Periodo (opcional)');
  await period.fill('2026-10');

  for (const close of [
    () => page.keyboard.press('Escape'),
    () => dialog.getByRole('button', { name: 'Cerrar' }).click(),
  ]) {
    const asked = answerNextConfirm(page, false);
    await close();
    await expect.poll(() => asked.length).toBe(1);
    await expect(dialog).toBeVisible();
    await expect(period).toHaveValue('2026-10');
  }

  const accepted = answerNextConfirm(page, true);
  // A click on the backdrop (the <dialog> element itself, outside its content box).
  await dialog.click({ position: { x: 2, y: 2 } });
  await expect.poll(() => accepted.length).toBe(1);
  await expect(dialog).toBeHidden();
});

test('recargar o cerrar la página con cambios pide confirmación del navegador', async ({ page }) => {
  await sidebar(page, 'Empresas');
  await page.getByRole('link', { name: 'Registrar empresa' }).first().click();
  await page.getByLabel('Razón social / Nombre completo *').fill('Borrador antes de cerrar');
  const types: string[] = [];
  page.on('dialog', async (dialog) => {
    types.push(dialog.type());
    await dialog.dismiss();
  });
  await page.close({ runBeforeUnload: true });
  await expect.poll(() => types).toEqual(['beforeunload']);
});
