import { expect, test } from '@playwright/test';
import { company, login, sidebar } from './helpers';

// Prompt Maestro, Bloques 3, 5 and 6: dossier header, fiscal calendar as the default view, motion rules.

test('encabezado del expediente: empresa, vistas y menú de más acciones', async ({ page }) => {
  await login(page);
  await sidebar(page, 'Empresas');
  await page.getByRole('button', { name: /^Directorio/ }).click();
  await page.getByRole('link', { name: 'Abrir ' + company.name }).click();

  const switcher = page.getByRole('combobox', { name: 'Cambiar empresa' });
  await expect(switcher.locator('option:checked')).toHaveText(company.name);
  const views = page.getByRole('navigation', { name: 'Vistas de la empresa' });
  await expect(views.getByRole('link', { name: 'Expediente' })).toHaveAttribute('aria-current', 'page');

  const more = page.getByRole('button', { name: 'Más acciones de la empresa' });
  await more.click();
  await expect(more).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('menuitem').first()).toBeFocused(); // focus moves into the menu
  await expect(page.getByRole('menuitem', { name: 'Editar' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('menu')).toHaveCount(0);
  await expect(more).toBeFocused();
});

test('tareas y vencimientos abre en el calendario fiscal', async ({ page }) => {
  await login(page);
  await sidebar(page, 'Tareas y vencimientos');
  await expect(page.getByRole('tab', { name: 'Calendario fiscal' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('combobox', { name: 'Vista del calendario' })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Empresa del calendario' })).toBeVisible();
});

test('movimiento: variables comunes y movimiento reducido sin desplazamientos', async ({ page }) => {
  await login(page);
  const tokens = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    return ['--ease-out', '--ease-drawer', '--motion-fast', '--motion-base', '--motion-slow'].map((t) =>
      root.getPropertyValue(t).trim(),
    );
  });
  expect(tokens.every(Boolean), tokens.join(' | ')).toBe(true);

  // With reduced motion, buttons keep their color transition but do not scale when pressed (C7, A6).
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await sidebar(page, 'Empresas');
  const button = page.locator('#main-content .btn:not(:disabled)').first();
  const style = await button.evaluate((el) => {
    const s = getComputedStyle(el);
    return { property: s.transitionProperty, duration: s.transitionDuration };
  });
  expect(style.property).toContain('background-color');
  expect(style.duration).not.toBe('0s');
  const box = await button.boundingBox();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  const pressed = await button.evaluate((el) => getComputedStyle(el).transform);
  await page.mouse.up();
  expect(pressed === 'none' || pressed === 'matrix(1, 0, 0, 1, 0, 0)').toBe(true);
});
