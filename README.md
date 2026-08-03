# GhostDeveloperLicenseServer

Servidor privado de autorización, releases y distribución segura para Hex Tunnel, integrado con TeleBotGen.

## Estado

Versión API: `0.3.0`

Incluye:

- FastAPI en `127.0.0.1:8080`;
- SQLite con WAL y migración compatible de columnas nuevas;
- keys almacenadas únicamente mediante HMAC-SHA256;
- códigos de activación transferibles y de un solo uso;
- vencimiento de key aplicado solo antes de la primera activación;
- instalaciones permanentes hasta revocación administrativa;
- activaciones vinculadas a IP;
- reseller incorporado a la autorización firmada;
- protección contra replay por nonce y timestamp;
- autorización RSA/SHA-256 para instalación y upgrade;
- upgrades autenticados mediante `activation.token`, no mediante la key original;
- descargas privadas temporales y de un solo uso;
- leases firmados que continúan después de vencer la key utilizada;
- eventos pendientes para notificaciones de activación en Telegram;
- enlaces temporales del instalador;
- filtros por propietario, emisor y grupo de origen;
- despliegue versionado con health check y rollback automático;
- bootstrap AMD64/ARM64.

## Semántica de la key

`expires_at` representa la fecha límite para utilizar una key que todavía no fue canjeada. Después de una autorización correcta:

- la licencia cambia a `activated`;
- queda ligada a la IP pública;
- se registra `key_redeemed_at`;
- el vencimiento de la key deja de bloquear leases y upgrades;
- la instalación continúa hasta que un administrador la revoque.

La API nunca conserva la key completa. TeleBotGen la retiene temporalmente en almacenamiento protegido para poder incluirla en el aviso de activación y la elimina después de confirmar la entrega.

## Reseller firmado

Cada licencia puede incluir:

```text
issued_by_telegram_id
source_chat_id
notification_chat_id
reseller_name
```

`reseller_name` forma parte del payload RSA de autorización. Hex Tunnel lo guarda en su estado local y lo muestra en el menú sin depender de texto suministrado localmente.

## Eventos de activación

TeleBotGen utiliza:

```text
GET  /api/v1/admin/activation-events?pending_only=true
POST /api/v1/admin/activation-events/{event_id}/delivered
```

El evento contiene la IP pública, fecha de activación, reseller y chat de destino. No contiene la key completa.

## Enlaces temporales

```text
POST /api/v1/admin/installer-links
GET  /i/{token}
```

El enlace temporal redirige al instalador público con `Cache-Control: no-store`. La key continúa siendo obligatoria para autorizar la descarga privada.

## Arquitectura

```text
TeleBotGen
  └─ localhost + token administrativo
     ├─ licencias
     ├─ enlaces temporales
     └─ eventos de activación

VPS del cliente
  └─ HTTPS
     ├─ instalador público
     ├─ autorización firmada
     ├─ lease renovable
     └─ descarga privada de un solo uso
```

Los endpoints administrativos permanecen accesibles únicamente desde localhost mediante la configuración de despliegue.

## Instalación del cliente

```bash
curl -fsSL https://ghostdeveloper.duckdns.org/install.sh -o /tmp/hextunnel-install.sh
sudo bash /tmp/hextunnel-install.sh install
```

La primera instalación solicita una key. Las actualizaciones posteriores usan:

```bash
sudo hextunnel-upgrade
```

El actualizador reutiliza el token permanente guardado en `/etc/hextunnel/activation.token`. La key original no se guarda.

## Operación

```bash
sudo ghostctl status
sudo ghostctl smoke
sudo ghostctl create-key 240 123456789 usuario
sudo ghostctl releases hextunnel
sudo ghostctl deploy-server
sudo ghostctl deploy-bot
sudo ghostctl publish-hextunnel <COMMIT_SHA> [VERSION]
sudo ghostctl release-all <COMMIT_SHA> [VERSION] [SERVER_REF] [BOT_REF]
sudo ghostctl rollback-server
```

## Despliegue

```bash
sudo bash scripts/install-server.sh
```

El instalador construye una release versionada, respalda SQLite, cambia `current` atómicamente, reinicia, espera `/health` y restaura la versión anterior si la comprobación falla.

## GitHub Actions

Las pruebas automatizadas validan:

- keys múltiples para un mismo emisor;
- rechazo de una key ya utilizada;
- firma RSA del reseller y la activación permanente;
- evento de activación y confirmación de entrega;
- enlaces temporales;
- descarga de un solo uso;
- upgrade y lease después de vencer artificialmente la key;
- revocación y reset;
- integridad de releases.

El smoke integral por SSH sigue siendo opcional hasta disponer de una VPS de pruebas. No bloquea el funcionamiento actual.

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
make check
bash -n public/install.sh
```
