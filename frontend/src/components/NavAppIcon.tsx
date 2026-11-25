import { Building2, CalendarClock, House, Settings, type LucideIcon } from 'lucide-react';

/** Íconos de app del panel para los módulos sin ícono original 0.6 (Inicio, Empresas, Tareas y
 *  Configuración). Siguen la construcción de los PNG originales: mosaico redondeado con degradado del tono
 *  del módulo (pálido en claro, profundo en oscuro), borde claro y glifo blanco con contorno del mismo tono.
 *  Sin insignia: la palomita de esquina es exclusiva de los módulos fiscales. */
export type NavAppTone = 'inicio' | 'empresas' | 'tareas' | 'configuracion';
const GLYPHS: Record<NavAppTone, LucideIcon> = {
  inicio: House,
  empresas: Building2,
  tareas: CalendarClock,
  configuracion: Settings,
};
export const navAppTones: Record<string, NavAppTone> = {
  '/': 'inicio',
  '/empresas': 'empresas',
  '/tareas': 'tareas',
  '/configuracion': 'configuracion',
};
export function NavAppIcon({ tone, size = 32 }: { tone: NavAppTone; size?: number }) {
  const Glyph = GLYPHS[tone];
  const glyph = Math.round(size * 0.53);
  return (
    <span className={'nav-app-icon tone-' + tone} style={{ width: size, height: size }} aria-hidden>
      <span className="nav-app-tile">
        <Glyph className="nav-app-halo" size={glyph} strokeWidth={4.5} />
        <Glyph className="nav-app-glyph" size={glyph} strokeWidth={2.1} />
      </span>
    </span>
  );
}
