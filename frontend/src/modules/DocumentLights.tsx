import { FileBadge, HeartPulse, KeyRound, Landmark, ShieldCheck, type LucideIcon } from 'lucide-react';
import './v11.css';

/** Plan v1.1, Cambio 1: one company's document traffic light (FIEL, CSF, SAT, Infonavit, IMSS). */
export type Light = {
  kind: 'fiel' | 'csf' | 'sat' | 'infonavit' | 'imss';
  label: string;
  state: 'green' | 'amber' | 'red' | 'gray' | 'na';
  date?: string | null;
  days?: number | null;
  expires?: string | null;
  result?: string;
  folio?: string | null;
  workers?: number | null;
  official_valid_until?: string | null;
  source?: string;
  detail?: string;
  legal_rep?: string | null;
  omissions?: { name: string; year: number; obligation_id?: string | null }[];
  propose_not_applicable?: boolean;
};
export type CompanyLights = {
  company_id: string;
  name: string;
  rfc: string;
  person_type: string;
  workers: number | null;
  lights: Light[];
};

export const ICONS: Record<Light['kind'], LucideIcon> = {
  fiel: KeyRound,
  csf: FileBadge,
  sat: ShieldCheck,
  infonavit: Landmark,
  imss: HeartPulse,
};
const SHORT: Record<Light['kind'], string> = { fiel: 'FIEL', csf: 'CSF', sat: 'SAT', infonavit: 'Infonavit', imss: 'IMSS' };
export const STATE_TEXT: Record<Light['state'], string> = {
  green: 'Vigente',
  amber: 'Por vencer',
  red: 'Vencido',
  gray: 'Sin documento',
  na: 'No aplica',
};
const RESULT: Record<string, string> = {
  positive: 'positiva',
  negative: 'negativa',
  no_opinion: 'sin opinión',
  unreviewed: 'sin revisar',
  unavailable: 'no disponible',
};
const day = (iso?: string | null) => (iso ? new Date(iso.slice(0, 10) + 'T12:00:00').toLocaleDateString('es-MX') : '');

export function stateText(l: Light) {
  if (l.state === 'red' && l.result === 'negative') return 'Negativa';
  if (l.kind === 'fiel' && l.state === 'green') return 'Vigente';
  if (l.result === 'no_opinion') return 'Sin opinión';
  if (l.state === 'green' && l.result === 'positive') return l.kind === 'infonavit' ? 'Sin adeudo' : 'Positiva';
  return STATE_TEXT[l.state];
}

export function describe(l: Light) {
  const parts = [l.label + ': ' + stateText(l)];
  if (l.kind === 'fiel') {
    if (l.date) parts.push(`vence el ${day(l.date)} (${l.days} días)`);
    if (l.legal_rep) parts.push(`FIEL del representante: vence el ${day(l.legal_rep)}`);
  } else if (l.date) {
    parts.push(`emitida el ${day(l.date)}` + (l.days != null ? ` (hace ${l.days} días)` : ''));
  }
  if (l.result && l.kind !== 'csf') parts.push('resultado ' + (RESULT[l.result] || l.result));
  if (l.folio) parts.push('folio ' + l.folio);
  if (l.workers != null) parts.push(`${l.workers} trabajadores activos`);
  if (l.official_valid_until) parts.push(`vigencia oficial al ${day(l.official_valid_until)}`);
  if (l.omissions?.length) parts.push('omisiones: ' + l.omissions.map((o) => `${o.name} ${o.year}`).join('; '));
  if (l.source === 'document') parts.push('leída del documento, sin validación oficial');
  if (l.detail) parts.push(l.detail);
  return parts.join(' · ');
}

export default function DocumentLights({
  company,
  compact = false,
  onSelect,
}: {
  company: CompanyLights;
  compact?: boolean;
  onSelect?: (l: Light) => void;
}) {
  return (
    <ul className={'v11-lights' + (compact ? ' compact' : '')} aria-label={'Semáforo documental de ' + company.name}>
      {company.lights.map((l) => {
        const Icon = ICONS[l.kind];
        const text = describe(l);
        const content = (
          <>
            <Icon size={compact ? 15 : 18} aria-hidden />
            {!compact && (
              <span className="v11-light-text">
                <span>{SHORT[l.kind]}</span>
                <small>{stateText(l)}</small>
              </span>
            )}
            <span className="sr-only">{text}</span>
          </>
        );
        return (
          <li key={l.kind} className={'v11-light is-' + l.state} title={text}>
            {onSelect ? (
              <button type="button" onClick={() => onSelect(l)}>
                {content}
              </button>
            ) : (
              <span>{content}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
