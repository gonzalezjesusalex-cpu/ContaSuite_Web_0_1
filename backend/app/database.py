import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')
DATA = Path(os.getenv('DATA_DIR', str(ROOT / 'data'))).resolve()
URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://contasuite:contasuite@127.0.0.1:5432/contasuite')
parsed_url = make_url(URL)
if parsed_url.get_backend_name() == 'sqlite' and parsed_url.database and parsed_url.database != ':memory:' and not Path(parsed_url.database).is_absolute():
    URL = parsed_url.set(database=str(ROOT / parsed_url.database)).render_as_string(hide_password=False)
engine = create_engine(URL, pool_pre_ping=True, **({'connect_args': {'check_same_thread': False}} if URL.startswith('sqlite') else {}))
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
