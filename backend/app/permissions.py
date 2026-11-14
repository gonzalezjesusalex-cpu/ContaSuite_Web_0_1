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
    }
)
ACTIONS = READ_ACTIONS | WRITE_ACTIONS

# What a write grant allowed before roles existed. Applies to an auxiliar whose actions in that company were
# never set explicitly (accounts migrated by cs_0007 keep their previous reach; decision 6 of 14/11/2026).
LEGACY_WRITE_ACTIONS = frozenset({'documentos.subir', 'obligaciones.editar', 'calendario.gestionar', 'tareas.editar'})


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
