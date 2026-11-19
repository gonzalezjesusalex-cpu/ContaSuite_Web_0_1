import { useState, type ComponentType } from 'react';
import CfdiInventory from './CfdiInventory';
import TaxInventory from './TaxInventory';
import ImssInventory from './ImssInventory';
import ExpedienteInventory from './ExpedienteInventory';
import FinanceInventory from './FinanceInventory';
import { PayrollInventory, WorkersInventory } from './PayrollInventory';
import { PpdInventory, ReconcileInventory } from './ReconcileInventory';
import CertInventory from './CertInventory';
import ChangesInventory from './ChangesInventory';
import type { Job } from '../types';

type Section = {
  key: string;
  label: string;
  view: ComponentType<{ job?: Job; companyId: string }>;
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
    key: 'conciliacion',
    label: 'Conciliación SAT',
    view: ReconcileInventory,
    count: (r) => r.conciliacion?.con_reporte,
    alert: (r) => r.conciliacion?.revisar ?? 0,
  },
  {
    key: 'ppd',
    label: 'Pagos PPD',
    view: PpdInventory,
    count: (r) => r.ppd?.total,
    alert: (r) => (r.ppd?.parcial ?? 0) + (r.ppd?.sin_pago ?? 0),
  },
  {
    key: 'certificados',
    label: 'e.firma y sello',
    view: CertInventory,
    count: (r) => r.certificados?.total,
    alert: (r) => (r.certificados?.por_vencer ?? 0) + (r.certificados?.vencidos ?? 0) + (r.certificados?.revisar ?? 0),
  },
  {
    key: 'cambios',
    label: 'Cambios y faltantes',
    view: ChangesInventory,
    count: () => undefined,
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
export default function Inventory({ job, companyId }: { job?: Job; companyId: string }) {
  const [key, setKey] = useState('cfdi');
  // An analysis delivered without the workers' section (no «Ver expedientes de trabajadores»): the tab is hidden.
  const noWorkers = !!job?.result.summary && !job.result.trabajadores;
  const sections = noWorkers ? SECTIONS.filter((s) => s.key !== 'trabajadores') : SECTIONS;
  const current = sections.find((s) => s.key === key) ?? sections[0];
  const View = current.view;
  return (
    <>
      <div className="inventory-sections" role="group" aria-label="Grupo documental">
        {sections.map((s) => {
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
      <View job={job} companyId={companyId} />
    </>
  );
}
