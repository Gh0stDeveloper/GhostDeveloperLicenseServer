# Integración con Nginx existente

La API escucha únicamente en `127.0.0.1:8080`. Nginx publica los endpoints permitidos mediante los dominios HTTPS ya configurados.

## Dominio público del instalador

Dentro del bloque HTTPS de `ghostdeveloper.duckdns.org`, conserva la página y `install.sh`, y añade el contenido de `public-installer-location.conf`.

Este dominio publica:

- `/` para la página pública;
- `/install.sh` para el bootstrap;
- `/i/<token>` para los enlaces temporales generados por TeleBotGen.

El endpoint `/i/<token>` valida el token en LicenseServer y redirige a `/install.sh`. No valida ni consume la key.

## Dominio de keys

Dentro del bloque HTTPS de `ghostdeveloperkeys.duckdns.org`, elimina las respuestas JSON temporales y copia el contenido de `keys-locations.conf`.

Este dominio publica únicamente:

- la clave pública RSA;
- `/api/v1/install/authorize` para validar y activar la key;
- `/api/v1/licenses/lease` para renovar la activación;
- `/health`.

No debe utilizarse como dominio del enlace temporal del instalador.

## Dominio de descargas

Dentro del bloque HTTPS de `ghostdeveloperdownloads.duckdns.org`, elimina las respuestas JSON temporales y copia el contenido de `downloads-locations.conf`.

Antes de recargar:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Pruebas:

```bash
curl https://ghostdeveloperkeys.duckdns.org/health
curl https://ghostdeveloperdownloads.duckdns.org/health
curl -I https://ghostdeveloper.duckdns.org/install.sh
curl -i https://ghostdeveloper.duckdns.org/i/token-invalido-de-al-menos-32-caracteres
curl -i https://ghostdeveloperkeys.duckdns.org/api/v1/admin/licenses
```

La prueba del enlace temporal inválido debe alcanzar LicenseServer y devolver `404` o `410`; no debe responder con la página estática. La última petición debe devolver `404`; TeleBotGen usa `http://127.0.0.1:8080/api/v1/admin/...` desde la misma VPS.
