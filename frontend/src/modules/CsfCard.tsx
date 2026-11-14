import { useRef, useState, type DragEvent } from 'react';
import { FileText, UploadCloud } from 'lucide-react';
import { stitchButton } from '../components/stitch';
import { api } from '../api';

export type CsfRegime = { code: string | null; label: string; start_date: string | null; end_date: string | null };
export type CsfResult = {
  source: 'text' | 'ocr';
  fields: Record<string, string | CsfRegime[] | undefined> & { regimes?: CsfRegime[] };
  low_confidence: string[];
  warnings: string[];
  unmatched_regimes: string[];
  obligations: { description: string; start_date: string | null }[];
  pages: number[];
  page_count: number;
  existing_company?: { id: string | null; name?: string };
};

/** Sends the PDF to be read on the server (text layer first, local OCR for scans). Nothing is saved. */
export async function analyzeCsf(file: File, companyId?: string): Promise<CsfResult> {
  const body = new FormData();
  body.append('file', file);
  if (companyId) body.append('company_id', companyId);
  return api<CsfResult>('/companies/csf/analyze', 'POST', body);
}

/** Entry card of the registration form: drop the Constancia de Situación Fiscal or continue manually. */
export default function CsfCard({
  title = 'Registrar desde Constancia de Situación Fiscal',
  ocrAvailable,
  companyId,
  onResult,
  onManual,
}: {
  title?: string;
  ocrAvailable: boolean;
  companyId?: string;
  onResult: (result: CsfResult, file: File) => void;
  onManual?: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [over, setOver] = useState(false);
  async function read(file?: File | null) {
    if (!file) return;
    setError('');
    if (file.type && file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Carga la constancia en PDF.');
      return;
    }
    if (file.size > 15 * 1024 * 1024) {
      setError('El archivo supera el límite de 15 MB.');
      return;
    }
    setBusy(true);
    try {
      onResult(await analyzeCsf(file, companyId), file);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    void read(e.dataTransfer.files?.[0]);
  };
  return (
    <section className="csf-card wide" aria-busy={busy}>
      <div className="csf-card-head">
        <FileText size={20} />
        <div>
          <strong>{title}</strong>
          <p>
            Lee los datos de la constancia y los coloca en el formulario para que los revises. No se guarda nada hasta
            que confirmes el registro.{' '}
            {ocrAvailable
              ? 'Los escaneos se leen con OCR local en este equipo.'
              : 'Este equipo no tiene el OCR local: sólo se leen constancias descargadas del SAT (con texto).'}
          </p>
        </div>
      </div>
      <label
        className={'csf-drop' + (over ? ' over' : '')}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
      >
        <UploadCloud size={28} />
        <span>{busy ? 'Leyendo la constancia…' : 'Suelta aquí el PDF o haz clic para elegirlo'}</span>
        <small>PDF de hasta 15 MB. Si trae otros documentos, sólo se leen las páginas de la constancia.</small>
        <input
          ref={input}
          type="file"
          accept="application/pdf,.pdf"
          disabled={busy}
          aria-label="Constancia de Situación Fiscal en PDF"
          onChange={(e) => void read(e.target.files?.[0])}
        />
      </label>
      {busy && <p role="status">Leyendo la constancia; un escaneo puede tardar unos segundos.</p>}
      {error && (
        <p className="error-banner" role="alert">
          {error}
        </p>
      )}
      {onManual && (
        <button type="button" className={stitchButton + ' link-button'} onClick={onManual} disabled={busy}>
          Prefiero capturar manualmente
        </button>
      )}
    </section>
  );
}
