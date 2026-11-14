import { useSearchParams } from 'react-router-dom';
import { Heading } from '../components/ui';
import { today } from '../api';
import { confirmDiscard } from '../navigationGuard';
import { Records } from './Records';
import FiscalCalendar from './FiscalCalendar';
import type { State } from '../types';

export default function TasksAndDeadlines({
  state,
  refresh,
  notify,
}: {
  state: State;
  refresh: () => Promise<void>;
  notify: (message: string) => void;
}) {
  const [params, setParams] = useSearchParams();
  // Bloque 5: the fiscal calendar is the first and default tab; `tab=tareas` and `tab=calendario` still work.
  const calendar = params.get('tab') !== 'tareas';
  const requested = params.get('period') || '';
  const period = /^20\d{2}-(0[1-9]|1[0-2])$/.test(requested) ? requested : today().slice(0, 7);
  const createDate = /^\d{4}-\d{2}-\d{2}$/.test(params.get('nueva') || '') ? params.get('nueva')! : undefined;
  function select(tab: string, extra?: Record<string, string>) {
    if (!confirmDiscard()) return;
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('tab', tab);
      next.delete('nueva');
      for (const [k, v] of Object.entries(extra || {})) next.set(k, v);
      return next;
    });
  }
  return (
    <>
      <Heading
        title="Tareas y vencimientos"
        description="Organiza las fechas fiscales, las tareas y el seguimiento operativo del despacho."
      />
      <div className="tabs card" role="tablist">
        <button
          role="tab"
          aria-selected={calendar}
          className={calendar ? 'active' : ''}
          onClick={() => select('calendario')}
        >
          Calendario fiscal
        </button>
        <button
          role="tab"
          aria-selected={!calendar}
          className={!calendar ? 'active' : ''}
          onClick={() => select('tareas')}
        >
          Tareas
        </button>
      </div>
      {calendar ? (
        <FiscalCalendar state={state} period={period} onCreateTask={(day) => select('tareas', { nueva: day })} />
      ) : (
        <Records
          key={createDate || 'tareas'}
          state={state}
          refresh={refresh}
          notify={notify}
          kind="tasks"
          createDate={createDate}
        />
      )}
    </>
  );
}
