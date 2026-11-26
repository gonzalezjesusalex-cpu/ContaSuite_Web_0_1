import { expect, type Dialog, type Page } from '@playwright/test';

// Shared synthetic identities for the E2E projects. The smoke project creates the administrator and the
// company through the UI; the other projects depend on it (see playwright.config.ts).
export const user = 'qa.e2e';
export const password = () => process.env.E2E_PASSWORD!;
export const company = { name: 'Empresa Sintética E2E', rfc: 'ESE010101AB1' };
export const discardMessage = 'Hay cambios sin guardar. ¿Descartarlos y continuar?';

export const sidebar = (page: Page, name: string) =>
  page.getByRole('navigation').getByRole('link', { name, exact: true }).click();

/** Dashboard principal › Empresas › Directorio (tab and sub-tab links). */
export async function openDirectory(page: Page) {
  await page
    .getByRole('navigation', { name: 'Pestañas del Dashboard principal' })
    .getByRole('link', { name: /^Empresas/ })
    .click();
  await page
    .getByRole('navigation', { name: 'Subpestañas de Empresas' })
    .getByRole('link', { name: 'Directorio' })
    .click();
}
export async function login(page: Page) {
  await page.goto('/');
  await page.getByLabel('Usuario').fill(user);
  await page.getByLabel('Contraseña').fill(password());
  await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  await expect(page.getByText('Bienvenido a ContaSuite')).toBeVisible();
}

// Answers the next native confirm() and records it, so a test can assert that the guard actually asked.
export function answerNextConfirm(page: Page, accept: boolean) {
  const seen: Dialog[] = [];
  page.once('dialog', async (dialog) => {
    seen.push(dialog);
    expect(dialog.type()).toBe('confirm');
    expect(dialog.message()).toBe(discardMessage);
    if (accept) await dialog.accept();
    else await dialog.dismiss();
  });
  return seen;
}

// Fails the test if any confirm() appears (used after discarding, when nothing should be pending).
export function forbidDialogs(page: Page) {
  const handler = async (dialog: Dialog) => {
    await dialog.dismiss();
    throw new Error('Diálogo inesperado: ' + dialog.message());
  };
  page.on('dialog', handler);
  return () => page.off('dialog', handler);
}

// Revisión visual automática con resultados en pantalla: sin desborde horizontal en los tres temas (claro, oscuro y
// alto contraste) y los anchos 320, 768 y 1280. Con E2E_SHOTS guarda una captura por combinación.
export async function expectNoOverflow(page: Page, label: string) {
  const shots = process.env.E2E_SHOTS;
  for (const width of [320, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ['light', 'dark', 'contrast']) {
      await page.evaluate((t) => (document.documentElement.dataset.theme = t), theme);
      const sizes = await page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth,
      }));
      expect(sizes.scroll, `${label} · ${theme} · ${width}px desborda horizontalmente`).toBeLessThanOrEqual(
        sizes.client,
      );
      if (shots) await page.screenshot({ path: `${shots}/${label}-${theme}-${width}.png` });
    }
  }
  await page.evaluate(() => (document.documentElement.dataset.theme = 'light'));
  await page.setViewportSize({ width: 1280, height: 720 });
}
