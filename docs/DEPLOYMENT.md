# Despliegue en la VPS

## Requisitos

- Ubuntu 22.04 o posterior.
- Python 3.10 o posterior.
- Nginx y HTTPS ya operativos.
- Ejecución como root para instalar el servicio.

## Instalación

Clona el repositorio privado en la VPS y ejecuta desde su raíz:

```bash
sudo bash scripts/install-server.sh
```

El script:

1. crea el usuario de sistema `ghostlicense`;
2. instala la aplicación en `/opt/ghostdeveloper-license-server`;
3. genera token administrativo, secreto HMAC y par RSA-3072;
4. inicializa SQLite en modo WAL;
5. instala y activa `ghost-license-api.service`;
6. activa backups diarios;
7. publica la clave pública en `/var/www/ghostdeveloper/.well-known/`.

## Verificación interna

```bash
sudo systemctl status ghost-license-api --no-pager
curl http://127.0.0.1:8080/health
sudo journalctl -u ghost-license-api -n 100 --no-pager
```

## Integrar Nginx

Sigue `nginx/README.md`. Los endpoints administrativos deben permanecer limitados a localhost.

## Registrar el primer paquete

```bash
sudo scripts/register-release.sh /ruta/hextunnel-1.0.0.tar.gz 1.0.0
```

## Crear una licencia manual de prueba

```bash
sudo scripts/create-license.sh 240 123456789 cliente
```

## Actualización

Ejecuta de nuevo `sudo bash scripts/install-server.sh` desde la versión nueva. El script conserva secretos, base de datos, releases y archivo de entorno.
