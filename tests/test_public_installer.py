from __future__ import annotations

import subprocess
from pathlib import Path


def test_public_installer_supports_failed_install_recovery() -> None:
    root = Path(__file__).resolve().parents[1]
    installer = root / "public" / "install.sh"
    text = installer.read_text(encoding="utf-8")

    syntax = subprocess.run(
        ["bash", "-n", str(installer)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr

    assert '[[ "$action" == install && -s "$TOKEN_FILE" ]]' in text
    assert "request_action=upgrade" in text
    assert "Reanudando instalación con la activación existente" in text
    assert 'export HEXTUNNEL_OPERATION="$action"' in text
