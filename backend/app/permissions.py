"""Per-company action catalog (Bloque 2, docs/BLOQUE_2_ROLES.md). Pure functions: no database access.

Reading a company's data is granted by any UserCompanyGrant (the `.ver` actions); the other actions are what
each role may do there. Everything is decided on the server from the stored role and grants.
"""

READ_ACTIONS = frozenset({'empresa.ver', 'documentos.ver', 'obligaciones.ver', 'tareas.ver', 'historial.ver'})
WRITE_ACTIONS = frozenset(
    {
        'empresa.editar',
        'empresa.archivar',
        'documentos.subir',
        'documentos.clasificar',
        'documentos.eliminar',
        'obligaciones.editar',
        'obligaciones.verificar',
        'calendario.gestionar',
        'tareas.editar',
        'recopila.usar',
        'cfdi.usar',
        'declara.usar',
        'recibos.usar',
        'carpeta.analizar',
        'carpeta.exportar',
        'trabajadores.ver',
    }
)
ACTIONS = READ_ACTIONS | WRITE_ACTIONS

# What a write grant allowed before roles existed. Applies to an auxiliar whose actions in that company were
# never set explicitly (accounts migrated by cs_0007 keep their previous reach; decision 6 of 14/11/2026).
LEGACY_WRITE_ACTIONS = frozenset({'documentos.subir', 'obligaciones.editar', 'calendario.gestionar', 'tareas.editar'})


# Quick templates for an auxiliar's actions in one company (always on top of the `.ver` actions).
# `carpeta.analizar`, `carpeta.exportar` and `trabajadores.ver` (personal data of workers) are never part of a
# template; they can only be chosen explicitly. A contador with a write grant has every action, like an administrator.
TEMPLATES = {
    'consulta': {'label': 'Solo consulta', 'actions': frozenset()},
    'captura': {'label': 'Captura de documentos', 'actions': frozenset({'documentos.subir', 'tareas.editar'})},
    'apoyo_fiscal': {
        'label': 'Apoyo fiscal',
        'actions': frozenset(
            {'obligaciones.editar', 'tareas.editar', 'recopila.usar', 'cfdi.usar', 'declara.usar', 'recibos.usar'}
        ),
    },
}

LABELS = {
    'empresa.ver': 'Ver la empresa',
    'documentos.ver': 'Ver documentos',
    'obligaciones.ver': 'Ver obligaciones',
    'tareas.ver': 'Ver tareas',
    'historial.ver': 'Ver historial',
    'empresa.editar': 'Editar datos de la empresa',
    'empresa.archivar': 'Archivar la empresa',
    'documentos.subir': 'Subir y adjuntar documentos',
    'documentos.clasificar': 'Clasificar documentos',
    'documentos.eliminar': 'Eliminar documentos',
    'obligaciones.editar': 'Capturar obligaciones y control fiscal',
    'obligaciones.verificar': 'Verificar evidencias',
    'calendario.gestionar': 'Gestionar fechas del calendario',
    'tareas.editar': 'Crear y editar tareas',
    'recopila.usar': 'Usar Recopila',
    'cfdi.usar': 'Usar CFDI',
    'declara.usar': 'Usar Declara',
    'recibos.usar': 'Usar Recibos',
    'carpeta.analizar': 'Analizar carpeta con el agente',
    'carpeta.exportar': 'Exportar una copia ordenada de la carpeta (escribe en tu equipo)',
    'trabajadores.ver': 'Ver expedientes de trabajadores (datos personales)',
}


def catalog():
    """Public description of the catalog for the account screens; carries no account data."""
    return {
        'read': sorted(READ_ACTIONS),
        'actions': [{'id': a, 'label': LABELS[a]} for a in sorted(WRITE_ACTIONS)],
        'templates': [{'id': k, 'label': v['label'], 'actions': sorted(v['actions'])} for k, v in TEMPLATES.items()],
    }


def company_actions(role, write, explicit=None):
    """Actions a non-admin account has in one company it holds a grant for.

    role: 'contador' or 'auxiliar'. write: the grant is 'write'. explicit: the auxiliar's stored actions for
    that company, or None when they were never set.
    """
    if role == 'contador':
        return ACTIONS if write else READ_ACTIONS
    if role == 'auxiliar':
        if explicit is None:
            return READ_ACTIONS | (LEGACY_WRITE_ACTIONS if write else frozenset())
        return READ_ACTIONS | (frozenset(explicit) & WRITE_ACTIONS)
    return frozenset()
