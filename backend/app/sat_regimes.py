"""SAT tax regime catalog (c_RegimenFiscal) for companies and the Constancia de Situación Fiscal (Bloque 1).

`match` maps the wording printed on a constancia to a catalog code. It never guesses: no match, or more than one
possible match, returns None and the caller leaves the regime empty with a notice.
"""

import re
import unicodedata

# code, label, applies to individuals (Física), applies to legal entities (Moral)
REGIMES = [
    ('601', 'General de Ley Personas Morales', False, True),
    ('603', 'Personas Morales con Fines no Lucrativos', False, True),
    ('605', 'Sueldos y Salarios e Ingresos Asimilados a Salarios', True, False),
    ('606', 'Arrendamiento', True, False),
    ('607', 'Régimen de Enajenación o Adquisición de Bienes', True, False),
    ('608', 'Demás ingresos', True, False),
    ('610', 'Residentes en el Extranjero sin Establecimiento Permanente en México', True, True),
    ('611', 'Ingresos por Dividendos (socios y accionistas)', True, False),
    ('612', 'Personas Físicas con Actividades Empresariales y Profesionales', True, False),
    ('614', 'Ingresos por intereses', True, False),
    ('615', 'Régimen de los ingresos por obtención de premios', True, False),
    ('616', 'Sin obligaciones fiscales', True, False),
    ('620', 'Sociedades Cooperativas de Producción que optan por diferir sus ingresos', False, True),
    ('621', 'Incorporación Fiscal', True, False),
    ('622', 'Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras', False, True),
    ('623', 'Opcional para Grupos de Sociedades', False, True),
    ('624', 'Coordinados', False, True),
    ('625', 'Régimen de las Actividades Empresariales con ingresos a través de Plataformas Tecnológicas', True, False),
    ('626', 'Régimen Simplificado de Confianza', True, True),
]

# Other wordings seen on constancias and in common use for the same regime.
ALIASES = {
    '605': ['Sueldos y Salarios', 'Régimen de Sueldos y Salarios e Ingresos Asimilados a Salarios'],
    '606': ['Régimen de Arrendamiento', 'Arrendamiento de inmuebles'],
    '612': [
        'Régimen de las Personas Físicas con Actividades Empresariales y Profesionales',
        'Actividades Empresariales y Profesionales',
    ],
    '601': ['Régimen General de Ley Personas Morales', 'Régimen General de Ley de Personas Morales'],
    '603': ['Régimen de las Personas Morales con Fines no Lucrativos'],
    '611': ['Ingresos por Dividendos', 'Régimen de los Ingresos por Dividendos'],
    '614': ['Régimen de los Ingresos por Intereses'],
    '621': ['Régimen de Incorporación Fiscal'],
    '625': ['Plataformas Tecnológicas', 'Actividades Empresariales con ingresos a través de Plataformas Tecnológicas'],
    '608': ['Régimen de los demás ingresos'],
    '622': ['Régimen de Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras'],
}

_PREFIX = re.compile(r'^(regimen|régimen)( de)?( (las|los|la|el))? ')


def normalize(text):
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower()
    text = re.sub(r'[^a-z0-9 ]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return _PREFIX.sub('', text)


_INDEX = {}
for _code, _label, *_ in REGIMES:
    for _name in [_label, *ALIASES.get(_code, [])]:
        _INDEX.setdefault(normalize(_name), set()).add(_code)


def label(code):
    return next((code + ' - ' + name for c, name, *_ in REGIMES if c == code), None)


def match(text):
    """Catalog code for a wording printed on a constancia, or None when there is no single exact match."""
    found = _INDEX.get(normalize(text), set())
    return next(iter(found)) if len(found) == 1 else None


def catalog():
    return [{'code': c, 'label': c + ' - ' + n, 'fisica': f, 'moral': m} for c, n, f, m in REGIMES]
