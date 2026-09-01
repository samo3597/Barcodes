"""Declarative base shared by SQLAlchemy models."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Server1Base(DeclarativeBase):
    """Declarative base for private ingestion and processing data."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Server2Base(DeclarativeBase):
    """Declarative base for the independent public read model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
