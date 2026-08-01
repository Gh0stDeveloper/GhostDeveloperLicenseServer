from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.db import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Administración local de Ghost License API")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Crear o actualizar el esquema de la base de datos")
    subparsers.add_parser("show-config", help="Mostrar configuración no sensible")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = get_settings()
    if args.command == "init-db":
        database = Database(settings.database_url)
        database.initialize()
        database.check()
        print("Base de datos inicializada correctamente")
        return 0
    if args.command == "show-config":
        print(
            json.dumps(
                {
                    "environment": settings.environment,
                    "database_url": settings.database_url,
                    "release_root": str(settings.release_root),
                    "download_base_url": settings.download_base_url,
                    "public_install_url": settings.public_install_url,
                    "enforce_source_ip": settings.enforce_source_ip,
                },
                indent=2,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
