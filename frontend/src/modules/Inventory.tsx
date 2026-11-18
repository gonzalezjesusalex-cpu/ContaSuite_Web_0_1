import { useState } from 'react';
import CfdiInventory from './CfdiInventory';
import TaxInventory from './TaxInventory';
import ImssInventory from './ImssInventory';
import type { Job } from '../types';

/** Virtual inventory of the last folder analysis, one section per document group. */
export default function Inventory({ job }: { job?: Job }) {
  const [section, setSection] = useState('cfdi');
  const sections = [
    { key: 'cfdi', label: 'CFDI', count: job?.result.cfdi?.total, alert: job?.result.cfdi?.revisar },
    {
      key: 'impuestos',
      label: 'Declaraciones y acuses',
      count: job?.result.impuestos?.total,
      alert: (job?.result.impuestos?.faltantes ?? 0) + (job?.result.impuestos?.revisar ?? 0),
    },
    {
      key: 'imss',
      label: 'IMSS',
      count: job?.result.imss?.total,
      alert: (job?.result.imss?.faltantes ?? 0) + (job?.result.imss?.revisar ?? 0),
    },
  ];
  return (
    <>
      <div className="inventory-sections" role="group" aria-label="Grupo documental">
        {sections.map((s) => (
          <button
            key={s.key}
            type="button"
            className={'chip' + (section === s.key ? ' on' : '')}
            aria-pressed={section === s.key}
            onClick={() => setSection(s.key)}
          >
            {s.label}
            {s.count !== undefined && ' ' + s.count.toLocaleString('es-MX')}
            {!!s.alert && <span className="inventory-alert"> · {s.alert} por atender</span>}
          </button>
        ))}
      </div>
      {section === 'cfdi' && <CfdiInventory job={job} />}
      {section === 'impuestos' && <TaxInventory job={job} />}
      {section === 'imss' && <ImssInventory job={job} />}
    </>
  );
}
