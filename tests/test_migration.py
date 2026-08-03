from __future__ import annotations

from pathlib import Path

from app.db import Database


def test_migration_marks_redeemed_legacy_rows_as_activated(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'legacy.db'}")
    with database.engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE licenses ("
            "id VARCHAR(36) PRIMARY KEY, "
            "status VARCHAR(24) NOT NULL, "
            "activation_count INTEGER NOT NULL, "
            "activated_at INTEGER, "
            "created_at INTEGER NOT NULL"
            ")"
        )
        connection.exec_driver_sql(
            "INSERT INTO licenses (id,status,activation_count,activated_at,created_at) VALUES "
            "('legacy-active','active',1,200,100),"
            "('legacy-expired','expired',1,300,100),"
            "('legacy-revoked','revoked',1,400,100),"
            "('unused','active',0,NULL,100)"
        )

    database._migrate_sqlite()

    with database.engine.connect() as connection:
        rows = {
            str(row[0]): (str(row[1]), row[2])
            for row in connection.exec_driver_sql(
                "SELECT id,status,key_redeemed_at FROM licenses ORDER BY id"
            ).fetchall()
        }

    assert rows["legacy-active"] == ("activated", 200)
    assert rows["legacy-expired"] == ("activated", 300)
    assert rows["legacy-revoked"] == ("revoked", None)
    assert rows["unused"] == ("active", None)
