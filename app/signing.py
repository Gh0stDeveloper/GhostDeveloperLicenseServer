from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


@dataclass(slots=True)
class AuthorizationSigner:
    private_key: rsa.RSAPrivateKey

    @classmethod
    def from_file(cls, path: Path) -> "AuthorizationSigner":
        try:
            key_data = path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"No se pudo leer la clave privada: {path}") from exc
        key = serialization.load_pem_private_key(key_data, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise RuntimeError("La clave privada de licencias debe ser RSA")
        if key.key_size < 3072:
            raise RuntimeError("La clave RSA debe tener al menos 3072 bits")
        return cls(private_key=key)

    def sign(self, payload: str) -> str:
        signature = self.private_key.sign(
            payload.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("ascii")


def canonical_authorization(
    *,
    status: str,
    key_expires_at: str,
    activated_at: str,
    installation_permanent: bool,
    reseller_name: str,
    download_expires_at: str,
    nonce: str,
    subject: str,
    version: str,
    download_url: str,
    package_sha256: str,
    entrypoint: str,
) -> str:
    return (
        f"status={status}\n"
        f"key_expires_at={key_expires_at}\n"
        f"activated_at={activated_at}\n"
        f"installation_permanent={'true' if installation_permanent else 'false'}\n"
        f"reseller_name={reseller_name}\n"
        f"download_expires_at={download_expires_at}\n"
        f"nonce={nonce}\n"
        f"subject={subject}\n"
        f"version={version}\n"
        f"download_url={download_url}\n"
        f"package_sha256={package_sha256.lower()}\n"
        f"entrypoint={entrypoint}\n"
    )


def canonical_lease(
    *,
    status: str,
    lease_expires_at: str,
    subject: str,
    product: str,
    activation_id: str,
) -> str:
    return (
        f"status={status}\n"
        f"lease_expires_at={lease_expires_at}\n"
        f"subject={subject}\n"
        f"product={product}\n"
        f"activation_id={activation_id}\n"
    )
