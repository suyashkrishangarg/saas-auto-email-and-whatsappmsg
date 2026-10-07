from typing import Any, AsyncGenerator, Tuple
import ssl as ssl_mod
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Params that libpq accepts in a URL but asyncpg.connect() rejects as kwargs.
_TLS_URL_PARAMS = ("sslmode", "channel_binding")


def prepare_engine_args(url: str) -> Tuple[str, dict[str, Any]]:
    """Make a Postgres URL safe for SQLAlchemy's asyncpg dialect.

    asyncpg.connect() takes ``ssl=SSLContext`` - it does NOT accept ``sslmode=``.
    Providers like Neon hand you URLs ending in ``?sslmode=require&...`` which
    would explode with "unexpected keyword argument 'sslmode'". This helper
    strips those params and translates them into a proper SSLContext instead.
    Local URLs without sslmode (sqlite, localhost postgres) pass through untouched.
    """
    if "://" not in url or "sslmode=" not in url:
        return url, {}
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    mode = next((v for k, v in pairs if k == "sslmode"), "require")
    kept = urlencode([(k, v) for k, v in pairs if k not in _TLS_URL_PARAMS])
    clean = urlunparse(parsed._replace(query=kept))
    if mode == "disable":
        return clean, {}
    # require / verify-ca / verify-full / prefer / allow -> encrypt the channel.
    # Default context also verifies the server cert (Neon certs are valid).
    return clean, {"ssl": ssl_mod.create_default_context()}


class Base(DeclarativeBase):
    pass


_engine_url, _engine_connect_args = prepare_engine_args(settings.DATABASE_URL)
engine = create_async_engine(
    _engine_url, connect_args=_engine_connect_args, pool_pre_ping=True, future=True
)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    from app import models  # noqa: F401  (registers all models)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
