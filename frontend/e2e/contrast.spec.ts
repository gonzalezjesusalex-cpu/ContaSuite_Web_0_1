import { writeFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { company, login, sidebar, openDirectory } from './helpers';

// WCAG AA text contrast (axe-core rule color-contrast) on the main screens in the three themes.
const themes = ['light', 'dark', 'contrast'] as const;

async function companyId(page: Page) {
  await sidebar(page, 'Empresas');
  await openDirectory(page);
  const href = await page.getByRole('link', { name: 'Abrir ' + company.name }).getAttribute('href');
  return href!.split('?')[0];
}

const screens: [string, (page: Page, dossier: string) => string][] = [
  ['Inicio', () => '/'],
  ['Dashboard · Resumen', () => '/empresas?tab=resumen'],
  ['Dashboard · Directorio', () => '/empresas?tab=empresas&sub=directorio'],
  ['Dashboard · Calidad de datos', () => '/empresas?tab=empresas&sub=calidad'],
  ['Dashboard · Importar', () => '/empresas?tab=empresas&sub=importar'],
  ['Dashboard · Semáforo', () => '/empresas?tab=documentos&sub=semaforo'],
  ['Dashboard · Opiniones', () => '/empresas?tab=documentos&sub=opiniones'],
  ['Dashboard · Expedientes', () => '/empresas?tab=documentos&sub=expedientes'],
  ['Dashboard · Matriz del mes', () => '/empresas?tab=obligaciones&sub=matriz'],
  ['Dashboard · Seguimiento CFDI', () => '/empresas?tab=obligaciones&sub=cfdi'],
  ['Dashboard · Calendario', () => '/empresas?tab=obligaciones&sub=calendario'],
  ['Gestor de contraseñas', () => '/gestor-contrasenas'],
  ['Configuración · Alertas', () => '/configuracion/alertas'],
  ['Configuración · Alertas · Historial', () => '/configuracion/alertas?sub=historial'],
  ['Alta de empresa', () => '/empresas/nueva'],
  ['Expediente · Resumen', (_, d) => d],
  ['Expediente · Documentos', (_, d) => d + '?tab=Documentos'],
  ['Tareas', () => '/tareas'],
  ['Calendario', () => '/tareas?tab=calendario'],
  ['Recopila', () => '/recopilador-cfdi'],
  ['CFDI', () => '/organizador-cfdi'],
  ['Declara', () => '/declara'],
  ['Recibos', () => '/recibos'],
  ['Configuración', () => '/configuracion'],
];

for (const theme of themes) {
  test('contraste AA · tema ' + theme, async ({ page }, info) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.addInitScript((t) => localStorage.setItem('contasuite-theme', t), theme);
    const findings: { screen: string; impact: string | null | undefined; target: string; summary: string }[] = [];
    const check = async (screen: string, p: Page) => {
      await p.waitForLoadState('networkidle');
      const result = await new AxeBuilder({ page: p }).withRules(['color-contrast']).analyze();
      for (const v of result.violations)
        for (const node of v.nodes)
          findings.push({
            screen,
            impact: node.impact,
            target: node.target.join(' '),
            summary: (node.any[0]?.message || node.failureSummary || '').replace(/\s+/g, ' '),
          });
    };
    // Login screen, signed out.
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Iniciar sesión' })).toBeVisible();
    await check('Login', page);

    await login(page);
    const dossier = await companyId(page);
    for (const [screen, url] of screens) {
      await page.goto(url(page, dossier));
      await expect(page.locator('#main-content h1, #main-content h2').first()).toBeVisible();
      await check(screen, page);
    }
    // Full report next to the test results, then fail with a readable list.
    await writeFile(info.outputPath('contrast-' + theme + '.json'), JSON.stringify(findings, null, 2));
    expect(
      findings.map((f) => f.screen + ' · ' + f.target + ' · ' + f.summary),
      'Contraste insuficiente en el tema ' + theme,
    ).toEqual([]);
  });
}
