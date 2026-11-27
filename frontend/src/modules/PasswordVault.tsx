import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { X } from 'lucide-react';
import { PASSWORD_MANAGER_PATH } from '../companyNavigation';
import type { State } from '../types';
import PasswordManager from './PasswordManager';
import VaultGate from './VaultGate';

/** Gestor de contraseñas: módulo propio (renovación del gestor, fase 5) con las pantallas del lienzo: Principal
 *  (bóveda abierta) y Bloqueado (VaultGate). Ya no muestra los menús sueltos de régimen y empresa ni el aviso largo
 *  sobre el cifrado de la antigua sección «Credenciales y Certificados». `?company_id=` lo abre en una empresa. */
export default function PasswordVault({ state }: { state: State }) {
  const [params] = useSearchParams();
  const requested = params.get('company_id') || '';
  const company = state.companies.find((c) => c.id === requested);
  const [message, setMessage] = useState('');
  useEffect(() => {
    document.title = 'Gestor de contraseñas · ContaSuite';
    return () => {
      document.title = 'ContaSuite · Gestión contable inteligente';
    };
  }, []);
  const users = Object.fromEntries([
    ...(state.responsibles || []).map((r) => [r.id, r.display_name]),
    [state.current_user.id, state.current_user.display_name],
  ]);
  return (
    <div className="v2-vault-page">
      {company && (
        <p className="v2-filter-chip" role="status">
          Mostrando sólo {company.name}
          <Link to={PASSWORD_MANAGER_PATH} aria-label="Quitar filtro de empresa">
            <X size={14} aria-hidden /> Ver todas las empresas
          </Link>
        </p>
      )}
      {message && (
        <p role="status" className="v2-vault-message">
          {message}
        </p>
      )}
      <VaultGate
        header={
          <header className="v2-vault-header">
            <div>
              <span className="v2-eyebrow">MÓDULO</span>
              <h1>Gestor de contraseñas</h1>
            </div>
          </header>
        }
      >
        <PasswordManager
          key={company?.id || 'all'}
          standalone
          companyId={company?.id}
          notify={setMessage}
          users={users}
        />
      </VaultGate>
    </div>
  );
}
