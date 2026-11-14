import { writeFile } from 'node:fs/promises';
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { company, login, sidebar } from './helpers';

// WCAG AA text contrast (axe-core rule color-contrast) on the main screens in the three themes.
const themes = ['light', 'dark', 'contrast'] as const;

async function companyId(page: Page) {
  await sidebar(page, 'Empresas');
  await page.getByRole('button', { name: /^Directorio/ }).click();
  const href = await page.getByRole('link', { name: 'Abrir ' + company.name }).getAttribute('href');
  return href!.split('?')[0];
}

const screens: [string, (page: Page, dossier: string) => string][] = [
  ['Inicio', () => '/'],
  ['Empresas · Panel', () => '/empresas?tab=Panel'],
  ['Empresas · Directorio', () => '/empresas?tab=Directorio'],
  ['Empresas · Documentos', () => '/empresas?tab=Documentos'],
  ['Empresas · Expedientes', () => '/empresas?tab=Documentos&vista=Expedientes+por+empresa'],
  ['Empresas · Obligaciones', () => '/empresas?tab=Obligaciones'],
  ['Empresas · Credenciales', () => '/empresas?tab=Credenciales'],
  ['Empresas · Alertas', () => '/empresas?tab=Credenciales&vista=Centro+de+alertas'],
  ['Empresas · Importar', () => '/empresas?tab=Importar'],
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
