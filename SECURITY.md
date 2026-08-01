# Seguridad

## Principios

- La API escucha exclusivamente en `127.0.0.1:8080`.
- Los endpoints administrativos no se exponen mediante Nginx.
- Las keys se almacenan como HMAC-SHA256.
- La clave privada RSA permanece fuera del repositorio.
- Las autorizaciones se firman con RSA/SHA-256.
- Los nonces impiden repetición de solicitudes.
- Los enlaces de descarga son temporales, de un solo uso y ligados a IP.
- SQLite utiliza WAL, claves foráneas y timeout de bloqueo.

## Archivos sensibles

```text
/etc/ghostdeveloper-license/secrets/admin-token
/etc/ghostdeveloper-license/secrets/key-hmac-secret
/etc/ghostdeveloper-license/secrets/license-private.pem
```

Deben pertenecer a `root:ghostlicense` con modo `0640`. Nunca deben subirse a GitHub ni enviarse por Telegram.

## Reporte privado

Reporta vulnerabilidades directamente al propietario del repositorio. No publiques keys, tokens, claves privadas, dumps de base de datos ni enlaces temporales en issues públicos.
