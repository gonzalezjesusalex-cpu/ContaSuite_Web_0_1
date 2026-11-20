import { crc32 } from 'node:zlib';
import { expect, test } from '@playwright/test';
import { company, login, sidebar } from './helpers';

// Flujo CFDI con datos sintéticos: analizar un ZIP, contrastar con el expediente, guardar y ver Por revisar › CFDI.
// Todo el contenido lo inventa esta prueba (RFC y UUID ficticios). E2E_SHOTS (opcional) es una carpeta donde se
// guardan capturas para la revisión visual.
const shots = process.env.E2E_SHOTS;
const other = 'BBB020202BB2';
const uuid = (n: number) => '11111111-2222-3333-4444-5555555555' + String(n).padStart(2, '0');

function cfdi(id: string, emisor: string, receptor: string, fecha: string) {
  return Buffer.from(
    '<c:Comprobante xmlns:c="http://www.sat.gob.mx/cfd/4" xmlns:t="http://www.sat.gob.mx/TimbreFiscalDigital" ' +
      `TipoDeComprobante="I" Fecha="${fecha}T10:00:00" Folio="1" Total="10.00">` +
      `<c:Emisor Rfc="${emisor}"/><c:Receptor Rfc="${receptor}"/>` +
      `<c:Complemento><t:TimbreFiscalDigital UUID="${id}"/></c:Complemento></c:Comprobante>`,
  );
}

// PDF mínimo con una línea de texto extraíble (la prueba sólo necesita que el UUID aparezca en el texto).
function pdf(text: string) {
  const stream = `BT /F1 12 Tf 50 750 Td (${text}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ];
  let out = '%PDF-1.4\n';
  const offsets = objects.map((body, i) => {
    const at = out.length;
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
    return at;
  });
  const xref = out.length;
  out += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => String(o).padStart(10, '0') + ' 00000 n \n').join('');
  out += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, 'latin1');
}

// ZIP sin compresión (método 0): suficiente para la prueba y sin dependencias nuevas.
function zip(files: Record<string, Buffer>) {
  const parts: Buffer[] = [];
  const central: Buffer[] = [];
  let offset = 0;
  for (const [name, data] of Object.entries(files)) {
    const n = Buffer.from(name);
    const crc = crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(n.length, 26);
    const entry = Buffer.alloc(46);
    entry.writeUInt32LE(0x02014b50, 0);
    entry.writeUInt16LE(20, 4);
    entry.writeUInt16LE(20, 6);
    entry.writeUInt32LE(crc, 16);
    entry.writeUInt32LE(data.length, 20);
    entry.writeUInt32LE(data.length, 24);
    entry.writeUInt16LE(n.length, 28);
    entry.writeUInt32LE(offset, 42);
    central.push(Buffer.concat([entry, n]));
    parts.push(local, n, data);
    offset += 30 + n.length + data.length;
  }
  const dir = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(central.length, 8);
  end.writeUInt16LE(central.length, 10);
  end.writeUInt32LE(dir.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...parts, dir, end]);
}

test('CFDI: analizar, contrastar con el expediente, guardar y revisar bloqueados', async ({ page }) => {
  const emitidos = `Base/Emitidos/${company.rfc}/2026-04/`;
  const recibidos = `Base/Recibidos/${company.rfc}/2026-04/`;
  const buffer = zip({
    [emitidos + 'ok.xml']: cfdi(uuid(1), company.rfc, other, '2026-04-10'),
    [emitidos + 'ok.pdf']: pdf('Factura ' + uuid(1)),
    [emitidos + 'mes.xml']: cfdi(uuid(2), company.rfc, other, '2026-05-02'), // fechado en mayo, archivado en abril
    [recibidos + 'ajena.xml']: cfdi(uuid(3), other, other, '2026-04-10'), // el receptor no es la empresa
    [recibidos + 'sinpdf.xml']: cfdi(uuid(4), other, company.rfc, '2026-04-10'),
  });

  await login(page);
  await sidebar(page, 'CFDI');
  await page.getByLabel('Empresa (opcional)').selectOption({ label: `${company.name} · ${company.rfc}` });
  await page
    .locator('input[type=file][accept=".zip"]')
    .setInputFiles({ name: 'cfdi-sintetico.zip', mimeType: 'application/zip', buffer });
  await expect(page.getByLabel('RFC de origen')).toHaveValue(company.rfc);
  await page.getByLabel('Ejercicio').fill('2026');
  await page.getByRole('button', { name: 'Todos', exact: true }).click();
  await page.getByRole('button', { name: 'Analizar origen' }).click();
  const contrast = page.getByRole('button', { name: 'Revisar contra el expediente' });
  await expect(contrast).toBeEnabled({ timeout: 30_000 });
  await expect(page.getByText('Pareja XML–PDF identificada').first()).toBeVisible();
  await expect(page.getByText('Fecha fuera del mes de la carpeta')).toBeVisible();
  await expect(page.getByText('Receptor distinto a la empresa')).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/cfdi-1-analisis.png', fullPage: true });
  await contrast.click();
  await expect(page.getByRole('status').filter({ hasText: '2 bloqueados' })).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/cfdi-2-contraste.png', fullPage: true });
  await page.getByRole('button', { name: 'Guardar en expediente' }).click();
  await expect(page.getByText('Guardado en el expediente.')).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/cfdi-3-guardado.png', fullPage: true });

  await sidebar(page, 'Empresas');
  await page.getByRole('button', { name: /^Directorio/ }).click();
  await page.getByRole('link', { name: 'Abrir ' + company.name }).click();
  await page
    .getByRole('button', { name: /^Documentos/ })
    .first()
    .click();
  await page.getByRole('button', { name: /^Por revisar/ }).click();
  await page.getByRole('button', { name: /^CFDI 2$/ }).click();
  await expect(page.getByRole('heading', { name: 'CFDI', exact: true })).toBeVisible();
  await expect(page.getByText('CFDI Abr 2026: 2 XML · 1 PDF · 2 en revisión')).toBeVisible();
  if (shots) await page.screenshot({ path: shots + '/cfdi-4-por-revisar.png', fullPage: true });
});
