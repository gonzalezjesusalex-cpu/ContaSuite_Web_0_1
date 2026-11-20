import { expect, test } from '@playwright/test';
import { login } from './helpers';

// El botón de tema de la barra recorre claro → oscuro → alto contraste → claro y recuerda la elección.
test('el botón de la barra recorre los tres temas y recuerda el elegido', async ({ page }) => {
  await login(page);
  const theme = () => page.evaluate(() => document.documentElement.dataset.theme);
  const button = () => page.getByRole('button', { name: /^Cambiar tema/ });
  await expect(button()).toHaveAccessibleName('Cambiar tema (actual: Claro)');
  expect(await theme()).toBe('light');
  await button().click();
  await expect(button()).toHaveAccessibleName('Cambiar tema (actual: Oscuro)');
  expect(await theme()).toBe('dark');
  await button().click();
  await expect(button()).toHaveAccessibleName('Cambiar tema (actual: Alto contraste)');
  expect(await theme()).toBe('contrast');
  await page.reload();
  await expect(button()).toHaveAccessibleName('Cambiar tema (actual: Alto contraste)');
  expect(await theme()).toBe('contrast');
  await button().click();
  await expect(button()).toHaveAccessibleName('Cambiar tema (actual: Claro)');
  expect(await theme()).toBe('light');
});
