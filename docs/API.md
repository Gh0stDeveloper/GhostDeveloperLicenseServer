# Contrato de API

## Autenticación administrativa

Los endpoints bajo `/api/v1/admin/` exigen:

```http
Authorization: Bearer <token>
```

El token se almacena en `/etc/ghostdeveloper-license/secrets/admin-token`. Estos endpoints no deben publicarse mediante Nginx.

## Crear licencia

`POST /api/v1/admin/licenses`

```json
{
  "product": "hextunnel",
  "owner_telegram_id": "123456789",
  "owner_username": "cliente",
  "expires_in_minutes": 240,
  "activation_limit": 1,
  "metadata": {}
}
```

La key completa solo aparece en la respuesta de creación. La base de datos conserva un HMAC-SHA256, no la key en texto plano.

## Registrar release

`POST /api/v1/admin/releases`

```json
{
  "product": "hextunnel",
  "version": "1.0.0",
  "relative_path": "hextunnel-1.0.0.tar.gz",
  "entrypoint": "bin/hextunnel-private-install",
  "activate": true
}
```

El paquete debe existir previamente dentro de `/var/lib/ghostdeveloper-license/releases`.

## Autorizar instalación

`POST /api/v1/install/authorize`

```json
{
  "key": "HT-....",
  "ip": "203.0.113.10",
  "nonce": "48-caracteres-hex",
  "timestamp": 1785580000,
  "product": "hextunnel",
  "action": "install"
}
```

La respuesta contiene la autorización firmada compatible con el bootstrap de Hex Tunnel, un enlace temporal de un solo uso y un `activation_token` para futuras renovaciones del menú.

## Renovar lease

`POST /api/v1/licenses/lease`

```json
{
  "activation_token": "token-entregado-al-instalar",
  "ip": "203.0.113.10",
  "product": "hextunnel"
}
```

## Descargar release

`GET /releases/{token}`

El token expira, se vincula a la IP autorizada y se consume en la primera descarga.
