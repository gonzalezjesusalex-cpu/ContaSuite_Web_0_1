import re
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


# CURP: 4 letters, birth date, sex (H, M or X for non-binary), state, 3 internal consonants, homoclave, digit.
CURP_PATTERN = r'[A-Z][AEIOUX][A-Z]{2}\d{6}[HMX][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z0-9]\d'


class CleanModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')


class CompanyIn(CleanModel):
    name: str = Field(min_length=2, max_length=220)
    rfc: str = Field(min_length=12, max_length=13)
    person_type: Literal['Moral', 'Física'] = 'Moral'
    trade_name: str = Field(default='', max_length=180)
    regime: str = Field(default='601 - General de Ley Personas Morales', max_length=100)
    accountant: str = Field(default='Sin asignar', max_length=150)
    email: str = Field(default='', max_length=180)
    phone: str = Field(default='', max_length=40)
    location: str = Field(default='', max_length=150)
    folder: str = Field(default='', max_length=1000)
    notes: str = Field(default='', max_length=10000)
    # Bloque 1: data of the Constancia de Situación Fiscal. Optional here (imports and older clients do not
    # send them); the registration form asks for them. Formats are always checked.
    idcif: str | None = Field(default=None, max_length=11)
    curp: str | None = Field(default=None, max_length=18)
    tax_postal_code: str | None = Field(default=None, max_length=5)
    tax_street_type: str | None = Field(default=None, max_length=80)
    tax_street: str | None = Field(default=None, max_length=200)
    tax_exterior_number: str | None = Field(default=None, max_length=40)
    tax_interior_number: str | None = Field(default=None, max_length=40)
    tax_neighborhood: str | None = Field(default=None, max_length=200)
    tax_locality: str | None = Field(default=None, max_length=200)
    tax_municipality: str | None = Field(default=None, max_length=200)
    tax_state: str | None = Field(default=None, max_length=80)
    tax_between_streets: str | None = Field(default=None, max_length=300)
    operations_start: date | None = None
    padron_status: str | None = Field(default=None, max_length=40)
    csf_issued_on: date | None = None
    # Every current regime, the main one first; None keeps the stored list when editing.
    regimes: list['RegimeIn'] | None = Field(default=None, max_length=20)

    @field_validator(
        'idcif',
        'curp',
        'tax_postal_code',
        'tax_street_type',
        'tax_street',
        'tax_exterior_number',
        'tax_interior_number',
        'tax_neighborhood',
        'tax_locality',
        'tax_municipality',
        'tax_state',
        'tax_between_streets',
        'padron_status',
        mode='before',
    )
    @classmethod
    def blank_is_none(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator('idcif')
    @classmethod
    def valid_idcif(cls, value):
        # The SAT prints 8 to 11 digits; never padded to 11.
        if value is not None and not re.fullmatch(r'\d{8,11}', value):
            raise ValueError('El idCIF debe tener de 8 a 11 dígitos')
        return value

    @field_validator('curp')
    @classmethod
    def valid_curp(cls, value):
        if value is None:
            return value
        value = value.upper()
        if not re.fullmatch(CURP_PATTERN, value):
            raise ValueError('La estructura de la CURP es incorrecta')
        return value

    @field_validator('tax_postal_code')
    @classmethod
    def valid_postal_code(cls, value):
        if value is not None and not re.fullmatch(r'\d{5}', value):
            raise ValueError('El código postal debe tener 5 dígitos')
        return value

    @field_validator('rfc', mode='before')
    @classmethod
    def normalize_rfc(cls, value):
        return ''.join(value.split()).upper() if isinstance(value, str) else value

    @field_validator('rfc')
    @classmethod
    def valid_rfc(cls, value):
        value = value.upper()
        if not re.fullmatch(r'[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}', value):
            raise ValueError('La estructura del RFC es incorrecta')
        prefix = len(value) - 9
        digits = value[prefix : prefix + 6]
        try:
            date(2000 + int(digits[:2]), int(digits[2:4]), int(digits[4:6]))
        except ValueError:
            raise ValueError('La fecha del RFC es inválida') from None
        return value

    @model_validator(mode='after')
    def person_length(self):
        if len(self.rfc) != (12 if self.person_type == 'Moral' else 13):
            raise ValueError('El tipo de persona no coincide con la longitud del RFC')
        # For individuals the first 10 characters of the RFC and the CURP are the same.
        if self.curp and self.person_type == 'Física' and self.rfc[:10] != self.curp[:10]:
            raise ValueError('Los primeros 10 caracteres del RFC y de la CURP no coinciden')
        return self


class RegimeIn(CleanModel):
    code: str | None = Field(default=None, pattern=r'^\d{3}$')
    label: str = Field(min_length=2, max_length=250)
    start_date: date | None = None
    end_date: date | None = None


CompanyIn.model_rebuild()


class TaskIn(CleanModel):
    company_id: str
    title: str = Field(min_length=2, max_length=250)
    category: str = Field(default='Operativa', max_length=80)
    responsible: str = Field(default='Sin asignar', max_length=150)
    due_date: date
    priority: Literal['Baja', 'Media', 'Alta', 'Crítica'] = 'Media'
    status: Literal['Pendiente', 'En proceso', 'Completada'] = 'Pendiente'
    notes: str = Field(default='', max_length=10000)


class ObligationIn(CleanModel):
    company_id: str
    title: str = Field(min_length=2, max_length=180)
    period: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    due_date: date
    status: Literal['Pendiente', 'En preparación', 'Presentada'] = 'Pendiente'
    reference: str = Field(default='', max_length=180)
    notes: str = Field(default='', max_length=10000)


class Heartbeat(CleanModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    capabilities: list[Literal['scan_folder']] = Field(default_factory=list, max_length=10)


class JobIn(CleanModel):
    company_id: str
    agent_id: str
    kind: Literal['scan_folder']


class JobResult(CleanModel):
    agent_id: str
    status: Literal['completed', 'failed']
    result: dict
