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
  const calendar = params.get('tab') === 'calendario';
  const requested = params.get('period') || '';
  const period = /^20\d{2}-(0[1-9]|1[0-2])$/.test(requested) ? requested : today().slice(0, 7);
  function select(tab: string) {
    if (!confirmDiscard()) return;
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('tab', tab);
      return next;
    });
  }
  return (
    <>
      <Heading
        title="Tareas y vencimientos"
        description="Organiza las tareas, las fechas fiscales y el seguimiento operativo del despacho."
      />
      <div className="tabs card">
        <button className={!calendar ? 'active' : ''} onClick={() => select('tareas')}>
          Tareas
        </button>
        <button className={calendar ? 'active' : ''} onClick={() => select('calendario')}>
          Calendario fiscal
        </button>
      </div>
      {calendar ? (
        <FiscalCalendar state={state} period={period} />
      ) : (
        <Records state={state} refresh={refresh} notify={notify} kind="tasks" />
      )}
    </>
  );
}
