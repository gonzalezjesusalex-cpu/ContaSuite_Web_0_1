import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
DATA = Path(os.getenv('DATA_DIR', str(ROOT / 'data'))).resolve()
URL = os.getenv('DATABASE_URL', '').strip()
if not URL:
    raise RuntimeError(
        'DATABASE_URL no está configurada. Defínela en el entorno del servicio o en el .env de la instancia; '
        'ContaSuite no usa credenciales por defecto.'
    )
parsed_url = make_url(URL)
# Example credentials (former built-in default and .env.example placeholder) are never accepted.
if parsed_url.password == 'CAMBIAR' or (parsed_url.username, parsed_url.password) == ('contasuite', 'contasuite'):
    raise RuntimeError(
        'DATABASE_URL usa credenciales de ejemplo. Configura una contraseña propia para la base de la instancia.'
    )
# PostgreSQL is mandatory outside tests (plan, point 19): the advisory locks that prevent duplicate
# documents and identities have no effect on SQLite. Test suites, the E2E server and the portable trial
# launcher opt in explicitly with CS_TEST_SQLITE=1.
SQLITE_TEST_FLAG = 'CS_TEST_SQLITE'
if parsed_url.get_backend_name() == 'sqlite' and os.getenv(SQLITE_TEST_FLAG, '').strip() != '1':
    raise RuntimeError(
        'SQLite sólo se admite en pruebas: no aplica los bloqueos que evitan duplicados. Configura '
        'DATABASE_URL con PostgreSQL; para un entorno de prueba define ' + SQLITE_TEST_FLAG + '=1.'
    )
if (
    parsed_url.get_backend_name() == 'sqlite'
    and parsed_url.database
    and parsed_url.database != ':memory:'
    and not Path(parsed_url.database).is_absolute()
):
    URL = parsed_url.set(database=str(ROOT / parsed_url.database)).render_as_string(hide_password=False)
engine = create_engine(
    URL, pool_pre_ping=True, **({'connect_args': {'check_same_thread': False}} if URL.startswith('sqlite') else {})
)
if URL.startswith('sqlite'):

    @event.listens_for(engine, 'connect')
    def foreign_keys(db, _):
        db.execute('PRAGMA foreign_keys=ON')


SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def session():
    with SessionLocal() as db:
        yield db
