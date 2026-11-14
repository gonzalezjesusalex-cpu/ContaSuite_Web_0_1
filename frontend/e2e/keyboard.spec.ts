import { expect, test, type Page } from '@playwright/test';
import { company, login, password, sidebar, user } from './helpers';

// Keyboard operation (plan, point 24): skip link, visible focus, no focus on hidden elements, tabs,
// dialogs (focus inside, Escape, focus return) and complete flows without a mouse.

type Focused = { tag: string; label: string; visible: boolean; indicator: boolean; inDialog: boolean };

// Describes document.activeElement: whether it is rendered and whether it shows a focus indicator
// (outline or a focus ring drawn with box-shadow) different from its unfocused look.
function focused(page: Page) {
  return page.evaluate((): Focused => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body) return { tag: 'body', label: '', visible: true, indicator: true, inDialog: false };
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const outline = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0;
    const ring = style.boxShadow !== 'none' && el.matches(':focus-visible');
    // Date-like inputs: the second Tab stop is the browser's own calendar button inside the input's
    // shadow root (the input itself is then not :focus). Chromium draws its focus ring there
    // (checked visually); page styles cannot reach it, so it counts as the browser's indicator.
    const pickerButton =
      el instanceof HTMLInputElement &&
      /^(month|date|datetime-local|time|week)$/.test(el.type) &&
      !el.matches(':focus');
    return {
      tag: el.tagName.toLowerCase(),
      label: (el.getAttribute('aria-label') || el.textContent || (el as HTMLInputElement).name || '')
        .trim()
        .slice(0, 40),
      visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden',
      indicator: outline || ring || pickerButton,
      inDialog: !!el.closest('dialog[open]'),
    };
  });
}

// Tabs through the page and returns every stop (up to `limit`).
async function tabStops(page: Page, limit: number) {
  const stops: Focused[] = [];
  for (let i = 0; i < limit; i++) {
    await page.keyboard.press('Tab');
    stops.push(await focused(page));
  }
  return stops;
}

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
});

test('el enlace para saltar al contenido es el primer foco y lleva al contenido', async ({ page }) => {
  await login(page);
  await page.goto('/empresas');
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Saltar al contenido' });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();
});

for (const [screen, url] of [
  ['Inicio', '/'],
  ['Empresas', '/empresas?tab=Directorio'],
  ['Expediente', 'dossier'],
  ['Tareas', '/tareas'],
  ['Configuración', '/configuracion'],
] as const) {
  test('foco visible en cada parada de tabulación · ' + screen, async ({ page }) => {
    await login(page);
    if (url === 'dossier') {
      await page.goto('/empresas?tab=Directorio');
      await page.getByRole('link', { name: 'Abrir ' + company.name }).click();
      await expect(page.getByRole('heading', { level: 1, name: company.name })).toBeVisible();
    } else {
      await page.goto(url);
    }
    await page.waitForLoadState('networkidle');
    const stops = await tabStops(page, 45);
    const hidden = stops.filter((s) => !s.visible);
    const unmarked = stops.filter((s) => s.visible && !s.indicator);
    expect(hidden, 'Foco en elementos invisibles').toEqual([]);
    expect(unmarked, 'Foco sin indicador visible').toEqual([]);
  });
}

test('pestañas de secciones con Enter y Espacio', async ({ page }) => {
  await login(page);
  await page.goto('/empresas');
  const tabs = page.getByRole('group', { name: 'Secciones de Empresas' });
  await tabs.getByRole('button', { name: 'Obligaciones' }).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/tab=Obligaciones/);
  await tabs.getByRole('button', { name: /^Directorio/ }).focus();
  await page.keyboard.press('Space');
  await expect(page).toHaveURL(/tab=Directorio/);
  await expect(tabs.getByRole('button', { name: /^Directorio/ })).toHaveAttribute('aria-pressed', 'true');
});

test('diálogo: el foco entra, no sale con Tab y vuelve al cerrar con Escape', async ({ page }) => {
  await login(page);
  await page.goto('/empresas?tab=Directorio');
  await page.getByRole('link', { name: 'Abrir ' + company.name }).click();
  await page
    .getByRole('button', { name: /^Documentos/ })
    .first()
    .click();
  const trigger = page.getByRole('button', { name: 'Cargar documento' });
  // Enabled once the upload options (permissions) have loaded.
  await expect(trigger).toBeEnabled();
  await trigger.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', { name: 'Cargar documento' });
  await expect(dialog).toBeVisible();
  expect((await focused(page)).inDialog, 'El foco debe entrar al diálogo').toBe(true);
  const stops = await tabStops(page, 25);
  expect(
    stops.filter((s) => !s.inDialog && s.tag !== 'body'),
    'Foco fuera del diálogo abierto',
  ).toEqual([]);
  expect(
    stops.filter((s) => !s.indicator),
    'Foco sin indicador dentro del diálogo',
  ).toEqual([]);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('flujo completo sin ratón: iniciar sesión y abrir una sección', async ({ page }) => {
  await page.goto('/');
  // The username field has autofocus.
  await expect(page.getByLabel('Usuario')).toBeFocused();
  await page.keyboard.type(user);
  await page.keyboard.press('Tab');
  await page.keyboard.type(password());
  await page.keyboard.press('Enter');
  await expect(page.getByText('Bienvenido a ContaSuite')).toBeVisible();
  const empresas = page.getByRole('navigation').getByRole('link', { name: 'Empresas', exact: true });
  for (let i = 0; i < 15 && !(await empresas.evaluate((el) => el === document.activeElement)); i++)
    await page.keyboard.press('Tab');
  await expect(empresas).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Centro de Control Fiscal' })).toBeVisible();
  await sidebar(page, 'Inicio');
});
