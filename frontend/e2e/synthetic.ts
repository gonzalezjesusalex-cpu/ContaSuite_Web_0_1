import { crc32 } from 'node:zlib';

// Archivos sintéticos para las pruebas E2E: todo el contenido lo inventa la prueba (RFC y UUID ficticios).

export const other = 'BBB020202BB2';
export const uuid = (n: number) => '11111111-2222-3333-4444-5555555555' + String(n).padStart(2, '0');

export function cfdi(id: string, emisor: string, receptor: string, fecha: string) {
  return Buffer.from(
    '<c:Comprobante xmlns:c="http://www.sat.gob.mx/cfd/4" xmlns:t="http://www.sat.gob.mx/TimbreFiscalDigital" ' +
      `TipoDeComprobante="I" Fecha="${fecha}T10:00:00" Folio="1" Total="10.00">` +
      `<c:Emisor Rfc="${emisor}"/><c:Receptor Rfc="${receptor}"/>` +
      `<c:Complemento><t:TimbreFiscalDigital UUID="${id}"/></c:Complemento></c:Comprobante>`,
  );
}

// PDF mínimo con una línea de texto extraíble por línea recibida.
export function pdf(...lines: string[]) {
  const escape = (t: string) => t.replace(/[\\()]/g, (c) => '\\' + c);
  const stream = lines.map((t, i) => `BT /F1 12 Tf 50 ${750 - i * 20} Td (${escape(t)}) Tj ET`).join('\n');
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
export function zip(files: Record<string, Buffer>) {
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
