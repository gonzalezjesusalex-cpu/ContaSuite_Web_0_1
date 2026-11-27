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
    capabilities: list[
        Literal['scan_folder', 'export_virtual', 'sat_declaraciones', 'write_cfdi', 'declara_carpeta']
    ] = Field(
        default_factory=list, max_length=10
    )
    # The job the agent is working on right now (optional: agents that do not send it keep the old behavior).
    job_id: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9_-]{1,80}$')


class JobIn(CleanModel):
    company_id: str
    # Bloque 4: the server uses the requester's linked agent; an id is only read for the legacy shared token.
    agent_id: str | None = None
    kind: Literal['scan_folder', 'export_virtual', 'sat_declaraciones'] = 'scan_folder'
    # Only for `sat_declaraciones`: the fiscal year to download. The address of the portal is never sent by the client.
    ejercicio: int | None = Field(default=None, ge=2000, le=2100)
    # Only for `export_virtual`: where the copy goes (a new folder inside an authorized root), whether to write it
    # (false = preview only) and which sections to include (none = the default set, without workers' personal data).
    destination: str | None = Field(default=None, max_length=400)
    apply: bool = False
    include: list[str] | None = Field(default=None, max_length=12)
    # Only for `scan_folder`: also store an internal copy of the content of these sections (cs_0015).
    copy: list[str] | None = Field(default=None, max_length=12)

    @model_validator(mode='after')
    def _export_needs_destination(self):
        if self.kind == 'export_virtual' and not self.destination:
            raise ValueError('La exportación necesita una carpeta de destino.')
        if self.kind == 'export_virtual' and self.copy:
            raise ValueError('La copia interna sólo se pide al analizar la carpeta.')
        if self.kind == 'scan_folder' and (self.destination or self.apply or self.include):
            raise ValueError('Esos datos sólo aplican a la exportación.')
        if self.kind == 'sat_declaraciones' and (self.destination or self.apply or self.include or self.copy):
            raise ValueError('Esos datos no aplican a la descarga de declaraciones.')
        if self.kind != 'sat_declaraciones' and self.ejercicio is not None:
            raise ValueError('El ejercicio sólo aplica a la descarga de declaraciones.')
        return self


class BlobHashes(CleanModel):
    """The SHA-256 of files the agent wants to copy; the server answers which ones it does not have yet."""

    agent_id: str
    hashes: list[str] = Field(max_length=500)

    @field_validator('hashes')
    @classmethod
    def _hex(cls, values):
        if any(not re.fullmatch(r'[0-9a-f]{64}', v) for v in values):
            raise ValueError('Huella inválida.')
        return values


class BlobCommit(CleanModel):
    """Closes the copy of a scan: mark which files of those sections now have their internal copy."""

    agent_id: str
    sections: list[str] = Field(max_length=12)


class IndexRow(CleanModel):
    """One file of the scan for the persistent virtual index. Secrets are never sent (the agent only counts them)."""

    p: str = Field(min_length=1, max_length=1000)  # original relative path
    s: int = Field(ge=0)  # size in bytes
    m: int | None = None  # modification time (ns), only to explain a change
    h: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')  # SHA-256 when the file could be read
    g: str = Field(min_length=1, max_length=30)  # classification group
    sec: str = Field(min_length=1, max_length=30)  # virtual section
    v: str = Field(min_length=1, max_length=1200)  # virtual path
    st: Literal['ok', 'revisar'] = 'ok'


class IndexBatch(CleanModel):
    """A slice of a scan's files. `last` closes the scan; `complete` is false if the walk hit its limit."""

    agent_id: str
    seq: int = Field(ge=0)
    rows: list[IndexRow] = Field(max_length=400)
    last: bool = False
    complete: bool = True


class JobResult(CleanModel):
    agent_id: str
    status: Literal['completed', 'failed']
    result: dict
