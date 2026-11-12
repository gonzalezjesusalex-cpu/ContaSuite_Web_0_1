import re
from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class CleanModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
class CompanyIn(CleanModel):
    name: str = Field(min_length=2, max_length=220)
    rfc: str = Field(min_length=12, max_length=13)
    person_type: Literal['Moral','Física'] = 'Moral'
    trade_name: str = Field(default='', max_length=180)
    regime: str = Field(default='601 - General de Ley Personas Morales', max_length=100)
    accountant: str = Field(default='Sin asignar', max_length=150)
    email: str = Field(default='', max_length=180)
    phone: str = Field(default='', max_length=40)
    location: str = Field(default='', max_length=150)
    folder: str = Field(default='', max_length=1000)
    notes: str = Field(default='', max_length=10000)
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
        digits = value[prefix:prefix+6]
        try: date(2000 + int(digits[:2]), int(digits[2:4]), int(digits[4:6]))
        except ValueError: raise ValueError('La fecha del RFC es inválida')
        return value
    @model_validator(mode='after')
    def person_length(self):
        if len(self.rfc) != (12 if self.person_type == 'Moral' else 13):
            raise ValueError('El tipo de persona no coincide con la longitud del RFC')
        return self

class TaskIn(CleanModel):
    company_id: str
    title: str = Field(min_length=2,max_length=250)
    category: str = Field(default='Operativa',max_length=80)
    responsible: str = Field(default='Sin asignar',max_length=150)
    due_date: date
    priority: Literal['Baja','Media','Alta','Crítica'] = 'Media'
    status: Literal['Pendiente','En proceso','Completada'] = 'Pendiente'
    notes: str = Field(default='',max_length=10000)

class ObligationIn(CleanModel):
    company_id: str
    title: str = Field(min_length=2,max_length=180)
    period: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    due_date: date
    status: Literal['Pendiente','En preparación','Presentada'] = 'Pendiente'
    reference: str = Field(default='',max_length=180)
    notes: str = Field(default='',max_length=10000)

class Heartbeat(CleanModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    capabilities: list[Literal['scan_folder']] = Field(default_factory=list, max_length=10)
class JobIn(CleanModel):
    company_id: str
    agent_id: str
    kind: Literal['scan_folder']
class JobResult(CleanModel):
    agent_id: str
    status: Literal['completed','failed']
    result: dict
