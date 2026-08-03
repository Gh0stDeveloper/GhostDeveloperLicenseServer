from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        connect_args: dict[str, object] = {}
        if url.startswith("sqlite:"):
            connect_args["check_same_thread"] = False
        self.engine = create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        if url.startswith("sqlite:"):
            self._configure_sqlite(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
            autoflush=False,
            future=True,
        )

    @staticmethod
    def _configure_sqlite(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    def _migrate_sqlite(self) -> None:
        if not self.url.startswith("sqlite:"):
            return
        additions = {
            "issued_by_telegram_id": "VARCHAR(32)",
            "source_chat_id": "VARCHAR(32)",
            "notification_chat_id": "VARCHAR(32)",
            "reseller_name": "VARCHAR(128)",
            "key_redeemed_at": "INTEGER",
        }
        with self.engine.begin() as connection:
            columns = {
                str(row[1])
                for row in connection.exec_driver_sql("PRAGMA table_info(licenses)").fetchall()
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE licenses ADD COLUMN {name} {definition}"
                    )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_licenses_issued_by_telegram_id "
                "ON licenses (issued_by_telegram_id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_licenses_source_chat_id "
                "ON licenses (source_chat_id)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_licenses_notification_chat_id "
                "ON licenses (notification_chat_id)"
            )

            # Before 0.3.0, a redeemed key normally remained in status=active
            # while activation_count/activated_at represented the real install.
            # Convert every non-revoked redeemed row so the new permanent lease
            # contract does not interrupt installations that already exist.
            connection.exec_driver_sql(
                "UPDATE licenses "
                "SET status = 'activated', "
                "    key_redeemed_at = COALESCE(key_redeemed_at, activated_at, created_at) "
                "WHERE activation_count > 0 AND status != 'revoked'"
            )

    def initialize(self) -> None:
        from app import models  # noqa: F401

        Base.metadata.create_all(self.engine)
        self._migrate_sqlite()

    def check(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def sessions(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()
