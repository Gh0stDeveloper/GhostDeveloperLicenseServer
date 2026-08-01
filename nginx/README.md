# Integración con Nginx existente

La API escucha únicamente en `127.0.0.1:8080`. Nginx publica los endpoints permitidos mediante los dominios HTTPS ya configurados.

## Dominio de keys

Dentro del bloque HTTPS de `ghostdeveloperkeys.duckdns.org`, elimina las respuestas JSON temporales y copia el contenido de `keys-locations.conf`.

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
curl -i https://ghostdeveloperkeys.duckdns.org/api/v1/admin/licenses
```

La última petición debe devolver `404`; TeleBotGen usará `http://127.0.0.1:8080/api/v1/admin/...` desde la misma VPS.
