import { HardDrive, Palette, ScrollText, Server, ShieldCheck, UserRound, Users, type LucideIcon } from 'lucide-react';
import type { CurrentUser } from './types';

/** Configuración: una sección por ruta (/configuracion/<slug>). Fuera del módulo diferido porque el
 *  breadcrumb del encabezado también la nombra. */
export type SettingsSlug = 'perfil' | 'tema' | 'servicios' | 'almacenamiento' | 'seguridad' | 'equipo' | 'auditoria';
export const SETTINGS_SECTIONS: {
  slug: SettingsSlug;
  label: string;
  icon: LucideIcon;
  shown: (identity: CurrentUser | null) => boolean;
}[] = [
  { slug: 'perfil', label: 'Perfil', icon: UserRound, shown: () => true },
  { slug: 'tema', label: 'Tema y accesibilidad', icon: Palette, shown: () => true },
  { slug: 'servicios', label: 'Servicios y agentes', icon: Server, shown: () => true },
  { slug: 'almacenamiento', label: 'Almacenamiento', icon: HardDrive, shown: (i) => !!i?.admin && !i.bootstrap },
  { slug: 'seguridad', label: 'Cuenta y seguridad', icon: ShieldCheck, shown: (i) => !!i && !i.bootstrap },
  {
    slug: 'equipo',
    label: 'Equipo y permisos',
    icon: Users,
    shown: (i) => !!i && !i.bootstrap && i.role !== 'auxiliar',
  },
  { slug: 'auditoria', label: 'Auditoría', icon: ScrollText, shown: (i) => !!i?.admin && !i.bootstrap },
];
export function settingsSection(slug: string | undefined, identity: CurrentUser | null) {
  return SETTINGS_SECTIONS.find((s) => s.slug === slug && s.shown(identity));
}
