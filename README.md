# GhostDeveloperLicenseServer

Servidor privado de licencias, despliegue y distribución segura para **Hex Tunnel**, integrado con **TeleBotGen**, Nginx y GitHub Actions.

## Estado

Versión API: `0.2.0`

Incluye:

- FastAPI en `127.0.0.1:8080`;
- SQLite con WAL y respaldos previos al despliegue;
- keys almacenadas mediante HMAC-SHA256;
- activaciones ligadas a IP, revocación y reset;
- protección contra replay por nonce y timestamp;
- autorización RSA/SHA-256 para instalación y upgrade;
- descargas privadas temporales y de un solo uso;
- leases firmados;
- filtros de licencias por Telegram ID y estado activo;
- promoción o rollback de releases existentes sin volver a subir el archivo;
- despliegue versionado con health check y rollback automático;
- bootstrap AMD64/ARM64;
- pruebas reales de producción mediante GitHub Actions.

## Arquitectura

```text
TeleBotGen
  └─ localhost + Bearer token
     └─ /api/v1/admin/

VPS del cliente
  └─ HTTPS
     ├─ GET  ghostdeveloper.duckdns.org/install.sh
     ├─ POST ghostdeveloperkeys.duckdns.org/api/v1/install/authorize
     ├─ POST ghostdeveloperkeys.duckdns.org/api/v1/licenses/lease
     └─ GET  ghostdeveloperdownloads.duckdns.org/releases/<token>
```

Los endpoints administrativos permanecen en localhost.

## Operación simplificada

Después del primer despliegue se instala:

```bash
sudo ghostctl
```

Comandos principales:

```bash
sudo ghostctl status
sudo ghostctl smoke
sudo ghostctl create-key 240 123456789 usuario
sudo ghostctl releases hextunnel
sudo ghostctl activate hextunnel 1.0.0-rc.3
sudo ghostctl deploy-server
sudo ghostctl deploy-bot
sudo ghostctl publish-hextunnel <COMMIT_SHA> [VERSION]
sudo ghostctl release-all <COMMIT_SHA> [VERSION] [SERVER_REF] [BOT_REF]
sudo ghostctl rollback-server
```

`release-all` actualiza el servidor, publica Hex Tunnel, actualiza TeleBotGen y ejecuta las comprobaciones de salud.

## Documentación operativa

- [Actualizaciones independientes de Hex Tunnel, LicenseServer y TeleBotGen](docs/ACTUALIZACIONES.md)

La guía explica los comandos por componente, validaciones posteriores, rollback, diagnóstico y la diferencia entre publicar Hex Tunnel e instalarlo en una VPS cliente.

## Despliegue del servidor

```bash
sudo bash scripts/install-server.sh
```

El instalador:

1. crea una release versionada de la aplicación;
2. construye un entorno virtual aislado;
3. respalda SQLite;
4. cambia el enlace `current` de forma atómica;
5. reinicia la API y espera `/health`;
6. restaura automáticamente la release anterior si la API falla;
7. conserva base de datos, secretos, paquetes y configuración.

## Publicar Hex Tunnel

La versión se obtiene automáticamente desde el archivo `VERSION` del commit:

```bash
sudo ghostctl publish-hextunnel <COMMIT_SHA_COMPLETO>
```

También puede especificarse explícitamente:

```bash
sudo ghostctl publish-hextunnel <COMMIT_SHA_COMPLETO> <VERSION>
```

Antes de registrar el paquete se ejecuta el gate completo de producción, se resuelve el component lock y se valida el TAR.GZ. Registrar nuevamente el mismo archivo y versión es idempotente; una versión existente con otro hash se rechaza.

## GitHub Actions

`Production operations` permite desde la interfaz de Actions:

- desplegar servidor;
- desplegar bot;
- publicar Hex Tunnel;
- actualizar los tres componentes;
- ejecutar smoke tests;
- hacer rollback del servidor.

`Live production smoke` valida los dominios públicos. Con secretos SSH configurados también:

- genera una key real de 15 minutos;
- autoriza la instalación desde la IP del runner;
- verifica la firma RSA;
- descarga y valida el paquete;
- confirma que el enlace sea de un solo uso;
- renueva el lease;
- prueba `upgrade` sin aumentar las activaciones;
- revoca la key de prueba al finalizar.

Secretos requeridos para el ciclo integral:

```text
GHOST_VPS_HOST
GHOST_VPS_USER
GHOST_VPS_SSH_PRIVATE_KEY
GHOST_VPS_KNOWN_HOSTS
GHOST_VPS_PORT                # opcional
```

## Instalación del cliente

```bash
curl -fsSL https://ghostdeveloper.duckdns.org/install.sh -o /tmp/hextunnel-install.sh
sudo bash /tmp/hextunnel-install.sh install
```

Hex Tunnel funciona en Debian 12 y Ubuntu 22.04/24.04 sobre AMD64 o ARM64. Debe instalarse en una VPS distinta a la VPS del bot y la API.

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
make check
bash -n scripts/ghostctl.sh
bash -n scripts/live-production-smoke.sh
```

## Desarrolladores

- `@Gh0stDeveloper`: integración, licencias e infraestructura.
- `@Jotchua_DevzZ`: proyecto original y desarrollo base.
