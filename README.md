# GhostDeveloperLicenseServer

Servidor privado de licencias y distribución segura para **Hex Tunnel**, integrado con **TeleBotGen**, Nginx y el bootstrap público firmado.

## Estado

Versión API: `0.1.0`

Incluye:

- API FastAPI en `127.0.0.1:8080`;
- SQLite con WAL y transacciones;
- keys opacas almacenadas mediante HMAC-SHA256;
- activaciones ligadas a IP, límites, revocación y reinicio administrativo;
- prevención de replay mediante nonce;
- autorización de instalación y actualización firmada con RSA/SHA-256;
- releases privadas con verificación SHA-256;
- enlaces temporales de descarga de un solo uso;
- leases firmados para validación periódica;
- página pública de Hex Tunnel;
- bootstrap público con instalación de dependencias y validación amd64/x86_64;
- scripts de instalación, backup, releases y licencias;
- servicio systemd endurecido;
- configuración Nginx y pruebas automatizadas.

## Arquitectura

```text
TeleBotGen
  └─ localhost + Bearer token
     └─ /api/v1/admin/

VPS del cliente
  └─ HTTPS
     ├─ GET  ghostdeveloper.duckdns.org/
     ├─ GET  ghostdeveloper.duckdns.org/install.sh
     ├─ POST ghostdeveloperkeys.duckdns.org/api/v1/install/authorize
     ├─ POST ghostdeveloperkeys.duckdns.org/api/v1/licenses/lease
     └─ GET  ghostdeveloperdownloads.duckdns.org/releases/<token>
```

Los endpoints administrativos permanecen en localhost. Nginx solo publica la web, el instalador, autorización, lease, health, clave pública y descargas temporales.

## Instalación o actualización en la VPS

```bash
sudo bash scripts/install-server.sh
```

El script conserva la base de datos, los secretos RSA/HMAC, los releases y el archivo de entorno. También publica:

```text
/var/www/ghostdeveloper/index.html
/var/www/ghostdeveloper/install.sh
```

Verificación:

```bash
curl http://127.0.0.1:8080/health
curl https://ghostdeveloperkeys.duckdns.org/health
curl https://ghostdeveloperdownloads.duckdns.org/health
curl -I https://ghostdeveloper.duckdns.org/
curl -I https://ghostdeveloper.duckdns.org/install.sh
```

## Registrar una release

```bash
sudo scripts/register-release.sh \
  /ruta/hextunnel-1.0.0-rc.2.tar.gz \
  1.0.0-rc.2 \
  hextunnel \
  bin/hextunnel-private-install
```

## Generar una licencia manual

```bash
sudo scripts/create-license.sh 240 123456789 cliente hextunnel
```

En producción, TeleBotGen realiza esta operación mediante la API administrativa local.

## Instalación del cliente

```bash
sudo bash -c 'command -v curl >/dev/null 2>&1 || { apt-get update -y && apt-get install -y curl ca-certificates; }; curl -fsSL https://ghostdeveloper.duckdns.org/install.sh -o /tmp/hextunnel-install.sh && chmod 700 /tmp/hextunnel-install.sh && exec /tmp/hextunnel-install.sh install'
```

Después de instalar:

```bash
sudo hextunnel-license status
sudo hextunnel-upgrade
```

Hex Tunnel debe ejecutarse en una VPS dedicada Debian 12 o Ubuntu 22.04/24.04, arquitectura amd64/x86_64. No debe instalarse en la VPS que aloja el bot y la API.

## Desarrollo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
make check
bash -n public/install.sh
```

## Documentación

- `docs/API.md`: contrato de endpoints.
- `docs/DEPLOYMENT.md`: despliegue y operación.
- `SECURITY.md`: modelo de seguridad.
- `nginx/README.md`: integración con Nginx.

## Desarrolladores

- `@Gh0stDeveloper`: integración, licencias e infraestructura.
- `@Jotchua_DevzZ`: proyecto original y desarrollo base.
