# GhostDeveloperLicenseServer

Servidor privado de licencias y distribución segura para **Hex Tunnel**, diseñado para integrarse con **TeleBotGen** y el bootstrap privado del proyecto.

## Estado

Versión inicial: `0.1.0`

Incluye:

- API FastAPI en `127.0.0.1:8080`;
- SQLite con WAL y transacciones;
- generación de keys opacas;
- almacenamiento HMAC-SHA256;
- activaciones ligadas a IP;
- límites de activación y reinicio administrativo;
- revocación de licencias;
- prevención de replay mediante nonce;
- autorización firmada RSA/SHA-256;
- releases privadas con SHA-256;
- enlaces temporales de descarga de un solo uso;
- leases firmados para validación periódica del menú;
- scripts de instalación, backup, registro de releases y creación manual de keys;
- servicio systemd endurecido;
- configuración de Nginx compatible con los dominios DuckDNS;
- pruebas automatizadas y GitHub Actions.

## Arquitectura

```text
TeleBotGen
  └─ localhost + Bearer token
     └─ POST /api/v1/admin/licenses

VPS del cliente
  └─ HTTPS
     ├─ POST ghostdeveloperkeys.duckdns.org/api/v1/install/authorize
     ├─ POST ghostdeveloperkeys.duckdns.org/api/v1/licenses/lease
     └─ GET  ghostdeveloperdownloads.duckdns.org/releases/<token>
```

Los endpoints administrativos permanecen en localhost. Nginx solo publica autorización, lease, health, clave pública y descargas.

## Instalación rápida en la VPS

```bash
sudo bash scripts/install-server.sh
```

Después integra las ubicaciones de `nginx/README.md` y comprueba:

```bash
curl http://127.0.0.1:8080/health
curl https://ghostdeveloperkeys.duckdns.org/health
curl https://ghostdeveloperdownloads.duckdns.org/health
```

## Primer flujo manual

1. Copia un paquete a la VPS y regístralo:

```bash
sudo scripts/register-release.sh /ruta/hextunnel-1.0.0.tar.gz 1.0.0
```

2. Genera una licencia:

```bash
sudo scripts/create-license.sh 240 123456789 cliente
```

3. Usa la key resultante con el bootstrap de Hex Tunnel.

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
make check
```

## Documentación

- `docs/API.md`: contrato de endpoints.
- `docs/DEPLOYMENT.md`: despliegue y operación.
- `SECURITY.md`: modelo de seguridad.
- `nginx/README.md`: integración con Nginx existente.

## Próximas integraciones

- reemplazar el generador heredado de TeleBotGen por llamadas a la API administrativa;
- guardar `activation_token` y lease firmado en Hex Tunnel;
- publicar el paquete privado reproducible de Hex Tunnel;
- añadir migraciones versionadas antes de la primera versión estable;
- ejecutar pruebas de aceptación con una VPS cliente limpia `x86_64`.
