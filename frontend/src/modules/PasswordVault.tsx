import { useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { X } from 'lucide-react';
import { Heading } from '../components/ui';
import { PASSWORD_MANAGER_PATH } from '../companyNavigation';
import type { State } from '../types';
import Credentials from './Credentials';
import VaultGate from './VaultGate';

/** Gestor de contraseñas: módulo propio con el contenido de la antigua pestaña «Credenciales» del dashboard,
 *  detrás de la bóveda con contraseña maestra (VaultGate). `?company_id=` lo abre filtrado a una empresa. */
export default function PasswordVault({ state }: { state: State }) {
  const [params] = useSearchParams();
  const requested = params.get('company_id') || '';
  const company = state.companies.find((c) => c.id === requested);
  useEffect(() => {
    document.title = 'Gestor de contraseñas · ContaSuite';
    return () => {
      document.title = 'ContaSuite · Gestión contable inteligente';
    };
  }, []);
  return (
    <>
      <Heading
        title="Gestor de contraseñas"
        description="Contraseñas cifradas de tus empresas, archivos FIEL/CSD y vigencia de certificados."
      />
      {company && (
        <p className="v2-filter-chip" role="status">
          Mostrando sólo {company.name}
          <Link to={PASSWORD_MANAGER_PATH} aria-label="Quitar filtro de empresa">
            <X size={14} aria-hidden /> Ver todas las empresas
          </Link>
        </p>
      )}
      <VaultGate>
        <Credentials key={company?.id || 'all'} state={state} companyId={company?.id} />
      </VaultGate>
    </>
  );
}
