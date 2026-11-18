import { useState, type ComponentType } from 'react';
import CfdiInventory from './CfdiInventory';
import TaxInventory from './TaxInventory';
import ImssInventory from './ImssInventory';
import ExpedienteInventory from './ExpedienteInventory';
import FinanceInventory from './FinanceInventory';
import { PayrollInventory, WorkersInventory } from './PayrollInventory';
import type { Job } from '../types';

type Section = {
  key: string;
  label: string;
  view: ComponentType<{ job?: Job }>;
  count: (r: Job['result']) => number | undefined;
  alert: (r: Job['result']) => number;
};

// One entry per document group: its view, how many files it holds and how many items need attention.
const SECTIONS: Section[] = [
  { key: 'cfdi', label: 'CFDI', view: CfdiInventory, count: (r) => r.cfdi?.total, alert: (r) => r.cfdi?.revisar ?? 0 },
  {
    key: 'impuestos',
    label: 'Declaraciones y acuses',
    view: TaxInventory,
    count: (r) => r.impuestos?.total,
    alert: (r) => (r.impuestos?.faltantes ?? 0) + (r.impuestos?.revisar ?? 0),
  },
  {
    key: 'imss',
    label: 'IMSS',
    view: ImssInventory,
    count: (r) => r.imss?.total,
    alert: (r) => (r.imss?.faltantes ?? 0) + (r.imss?.revisar ?? 0),
  },
  {
    key: 'nomina',
    label: 'Nómina',
    view: PayrollInventory,
    count: (r) => r.nomina?.total,
    alert: (r) => r.nomina?.faltantes ?? 0,
  },
  {
    key: 'expediente',
    label: 'Expediente de la empresa',
    view: ExpedienteInventory,
    count: (r) => r.expediente?.total,
    alert: (r) => (r.expediente?.faltan.length ?? 0) + (r.expediente?.revisar ?? 0),
  },
  {
    key: 'finanzas',
    label: 'Estados financieros',
    view: FinanceInventory,
    count: (r) => r.finanzas?.total,
    alert: () => 0,
  },
  {
    key: 'trabajadores',
    label: 'Trabajadores',
    view: WorkersInventory,
    count: (r) => r.trabajadores?.total,
    alert: (r) => r.trabajadores?.incompletos ?? 0,
  },
];

/** Virtual inventory of the last folder analysis, one section per document group. */
export default function Inventory({ job }: { job?: Job }) {
  const [key, setKey] = useState('cfdi');
  const current = SECTIONS.find((s) => s.key === key) ?? SECTIONS[0];
  const View = current.view;
  return (
    <>
      <div className="inventory-sections" role="group" aria-label="Grupo documental">
        {SECTIONS.map((s) => {
          const count = job ? s.count(job.result) : undefined;
          const alert = job ? s.alert(job.result) : 0;
          return (
            <button
              key={s.key}
              type="button"
              className={'chip' + (key === s.key ? ' on' : '')}
              aria-pressed={key === s.key}
              onClick={() => setKey(s.key)}
            >
              {s.label}
              {count !== undefined && ' ' + count.toLocaleString('es-MX')}
              {!!alert && <span className="inventory-alert"> · {alert} por atender</span>}
            </button>
          );
        })}
      </div>
      <View job={job} />
    </>
  );
}
