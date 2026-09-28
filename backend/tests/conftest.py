from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from moody.store import init_db, session_factory


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = init_db(f"sqlite:///{tmp_path / 'moody.db'}")
    yield engine
    engine.dispose()


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return session_factory(engine)
