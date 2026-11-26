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
    // A field whose ring is drawn on its immediate container (the global search, A4 / P3).
    const host = el.parentElement ? getComputedStyle(el.parentElement) : null;
    const hostRing =
      !!host && el.matches(':focus-visible') && host.outlineStyle !== 'none' && parseFloat(host.outlineWidth) > 0;
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
      indicator: outline || ring || hostRing || pickerButton,
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
  const skip = page.getByRole('link', { name: 'Saltar al contenido' });
  // The shell renders after the session check («Consultando sesión…»); press Tab once it exists.
  await expect(skip).toBeAttached();
  await page.keyboard.press('Tab');
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
  await expect(page.getByRole('heading', { name: 'Dashboard principal' })).toBeVisible();
  await expect(page.getByText('Lo que requiere tu atención este periodo.')).toBeVisible();
  const tabs = page.getByRole('navigation', { name: 'Pestañas del Dashboard principal' });
  await expect(tabs.getByRole('link', { name: 'Resumen' })).toHaveAttribute('aria-current', 'page');
  await tabs.getByRole('link', { name: 'Obligaciones' }).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/tab=obligaciones&sub=matriz/);
  await expect(page.getByLabel('Periodo')).toBeVisible();
  await tabs.getByRole('link', { name: /^Empresas/ }).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/tab=empresas&sub=directorio/);
  await expect(tabs.getByRole('link', { name: /^Empresas/ })).toHaveAttribute('aria-current', 'page');
  // Empresas does not depend on the period: no period control there.
  await expect(page.getByLabel('Periodo')).toHaveCount(0);
  // The view survives a reload.
  await page.reload();
  await expect(
    page.getByRole('navigation', { name: 'Subpestañas de Empresas' }).getByRole('link', { name: 'Directorio' }),
  ).toHaveAttribute('aria-current', 'page');
});

test('campana de alertas: se abre, se cierra con Escape y lleva a Configuración › Alertas', async ({ page }) => {
  await login(page);
  await page.goto('/empresas');
  const bell = page.getByRole('button', { name: /^Alertas:/ });
  await bell.click();
  const menu = page.getByRole('region', { name: 'Alertas activas más recientes' });
  await expect(menu).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
  await expect(bell).toBeFocused();
  await bell.click();
  await menu.getByRole('link', { name: 'Ver todas' }).click();
  await expect(page).toHaveURL(/\/configuracion\/alertas/);
  await expect(page.getByRole('heading', { name: /^Alertas/ })).toBeVisible();
  // Never the internal code nor the identifier in the list.
  await expect(page.locator('.v2-alerts-table')).not.toContainText(
    /missing_responsible|document_pending_classification|evidence_review/,
  );
});

test('enlaces viejos del dashboard llegan a su nuevo destino', async ({ page }) => {
  await login(page);
  await page.goto('/empresas?tab=Panel&vista=Seguimiento+CFDI');
  await expect(page).toHaveURL(/tab=obligaciones&sub=cfdi/);
  await page.goto('/empresas?tab=Credenciales');
  await expect(page).toHaveURL(/\/gestor-contrasenas$/);
  await expect(page.getByRole('heading', { name: 'Gestor de contraseñas' })).toBeVisible();
  await page.goto('/empresas?tab=Credenciales&vista=Centro+de+alertas');
  await expect(page).toHaveURL(/\/configuracion\/alertas$/);
  await page.goto('/empresas?tab=Importar');
  await expect(page).toHaveURL(/tab=empresas&sub=importar/);
  await page.goto('/empresas?tab=obligaciones&sub=inexistente');
  await expect(page).toHaveURL(/tab=resumen/);
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
  await expect(page.getByRole('heading', { name: 'Dashboard principal' })).toBeVisible();
  await sidebar(page, 'Inicio');
});
