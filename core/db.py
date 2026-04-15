"""
Database setup for the SEO Content Engine.
Sets up the SQLAlchemy engine and provides a session factory context manager.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from core.config import CONFIG
from core.logging import get_logger

logger = get_logger("core.db")

# Create declarative base for models
Base = declarative_base()

# Configure engine
connect_args = {}
if CONFIG.database_url.startswith("sqlite"):
    # SQLite requires check_same_thread=False when passing sessions across threads
    connect_args["check_same_thread"] = False

engine = create_engine(
    CONFIG.database_url,
    connect_args=connect_args,
    # echo=True  # Uncomment to log all SQL queries (debug only)
)

# Configure session factory
session_factory = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)
Session = scoped_session(session_factory)


@contextmanager
def get_session() -> Generator[sessionmaker, None, None]:
    """
    Context manager for database sessions.
    Automatically commits on success and rolls back on exception.
    """
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as exc:
        logger.error("Session transaction failed, rolling back", extra_data={"error": str(exc)})
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Initialize the database schema."""
    logger.info("Initializing database schema...")
    try:
        from core import models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema created successfully.")
    except Exception as exc:
        logger.critical("Failed to create database schema", extra_data={"error": str(exc)})
        raise
