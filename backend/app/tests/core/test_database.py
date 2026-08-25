from sqlalchemy import text

from app.core.database import create_session_factory, create_sqlalchemy_engine


def test_create_sqlalchemy_engine_and_session_factory_with_sqlite() -> None:
    engine = create_sqlalchemy_engine("sqlite+pysqlite:///:memory:")
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        result = session.execute(text("select 1")).scalar_one()

    assert result == 1

