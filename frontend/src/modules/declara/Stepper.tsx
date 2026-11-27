import { Check, Lock } from 'lucide-react';

export type StepState = 'current' | 'done' | 'available' | 'locked';
export type Step = { n: number; label: string; state: StepState };

const STATE_TEXT: Record<StepState, string> = {
  current: 'En curso',
  done: 'Completo',
  available: 'Disponible',
  locked: 'Bloqueado',
};

/** Pasos de Declara: número, nombre y estado. Los bloqueados no se pueden abrir. */
export default function Stepper({ steps, onSelect }: { steps: Step[]; onSelect: (n: number) => void }) {
  return (
    <ol className="declara-stepper" aria-label="Pasos de Declara">
      {steps.map((s) => (
        <li key={s.n} className={'declara-step ' + s.state}>
          <button
            type="button"
            disabled={s.state === 'locked'}
            aria-current={s.state === 'current' ? 'step' : undefined}
            onClick={() => onSelect(s.n)}
          >
            <span className="declara-step-number" aria-hidden="true">
              {s.state === 'done' ? <Check size={15} /> : s.state === 'locked' ? <Lock size={13} /> : s.n}
            </span>
            <span className="declara-step-text">
              <strong>
                {s.n} · {s.label}
              </strong>
              <small>{STATE_TEXT[s.state]}</small>
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
