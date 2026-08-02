# Guía de actualizaciones independientes

Esta guía explica cómo actualizar por separado los tres componentes de la plataforma:

- **Hex Tunnel**: paquete comercial que se construye y publica desde la VPS de control.
- **GhostDeveloperLicenseServer**: API, licencias, descargas y operaciones.
- **TeleBotGen**: bot de Telegram para administración y generación de licencias.

> La VPS de control publica Hex Tunnel, pero no debe usarse como VPS cliente para instalar el producto completo. El cliente de Hex Tunnel debe instalarse en otra VPS compatible.

## Regla principal

Cada actualización debe desplegarse usando el **SHA completo e inmutable del commit** que ya pasó sus GitHub Actions.

Ejemplo de SHA válido:

```text
0123456789abcdef0123456789abcdef01234567
```

No se recomienda desplegar directamente una rama mutable como `main`, porque su contenido puede cambiar entre una comprobación y el despliegue.

Antes de comenzar:

```bash
sudo -i

ghostctl status
ghostctl smoke
```

---

## 1. Actualizar solamente Hex Tunnel

### Qué hace

`publish-hextunnel`:

1. descarga el commit exacto del repositorio de Hex Tunnel;
2. ejecuta las pruebas y el gate de producción;
3. realiza una instalación simulada mediante `DRY-RUN`;
4. construye el archivo `hextunnel-<version>.tar.gz`;
5. calcula y valida su SHA-256;
6. registra el paquete en LicenseServer;
7. marca la nueva versión como activa.

Este proceso **no instala Hex Tunnel en la VPS de control**, no reemplaza nginx y no modifica TeleBotGen ni LicenseServer.

### Comando

```bash
HEX_SHA="COMMIT_SHA_COMPLETO"
HEX_VERSION="1.0.0-rc.4"

ghostctl publish-hextunnel "$HEX_SHA" "$HEX_VERSION"
```

La versión puede omitirse si el commit contiene un archivo `VERSION` correcto:

```bash
ghostctl publish-hextunnel "COMMIT_SHA_COMPLETO"
```

### Validación

```bash
ghostctl releases hextunnel
ghostctl smoke
ghostctl status
```

La versión recién publicada debe aparecer como `ACTIVE`:

```text
1.0.0-rc.4    ACTIVE      <sha256>    hextunnel-1.0.0-rc.4.tar.gz
1.0.0-rc.3    inactive    <sha256>    hextunnel-1.0.0-rc.3.tar.gz
```

### Volver a una release anterior

No es necesario recompilar. Activa una versión ya registrada:

```bash
ghostctl activate hextunnel 1.0.0-rc.3
ghostctl releases hextunnel
```

Esto cambia el paquete que entrega LicenseServer. No desinstala ni modifica clientes que ya tengan otra versión instalada.

---

## 2. Actualizar solamente GhostDeveloperLicenseServer

### Qué hace

`deploy-server` realiza un despliegue versionado y transaccional:

1. descarga el commit o referencia solicitada;
2. valida el instalador;
3. crea una release nueva bajo `/opt/ghostdeveloper-license-server/releases`;
4. prepara el entorno virtual y las dependencias;
5. respalda la base de datos antes del cambio;
6. cambia el enlace `current` de forma atómica;
7. reinicia `ghost-license-api.service`;
8. comprueba `/health`;
9. conserva la release anterior para rollback.

Las licencias, secretos, paquetes publicados y configuración persistente no deben eliminarse durante el despliegue.

### Comando

```bash
SERVER_SHA="COMMIT_SHA_COMPLETO"

ghostctl deploy-server "$SERVER_SHA"
```

También puede desplegarse la referencia configurada por defecto:

```bash
ghostctl deploy-server
```

Para producción se prefiere el SHA exacto.

### Validación

```bash
curl -fsS http://127.0.0.1:8080/health | jq .
systemctl is-active ghost-license-api.service
ghostctl smoke
ghostctl status
```

El endpoint debe responder con `status: online` y la versión esperada.

### Rollback

```bash
ghostctl rollback-server

curl -fsS http://127.0.0.1:8080/health | jq .
ghostctl status
```

`rollback-server` intercambia las referencias `current` y `previous`, reinicia la API y exige que la release restaurada supere el health check.

---

## 3. Actualizar solamente TeleBotGen

### Qué hace

`deploy-bot`:

1. descarga el commit exacto de TeleBotGen;
2. valida sintaxis, versión y archivos requeridos;
3. crea un respaldo en `/var/backups/telebotgen`;
4. conserva token, administradores, revendedores, grupos permitidos y duración configurada;
5. reemplaza los scripts de forma controlada;
6. actualiza las unidades systemd;
7. ejecuta el bot como usuario limitado `telebotgen`;
8. reinicia y valida `telebotgen.service`;
9. restaura el respaldo automáticamente si falla.

### Comando

```bash
BOT_SHA="COMMIT_SHA_COMPLETO"

ghostctl deploy-bot "$BOT_SHA"
```

También puede desplegarse la referencia configurada por defecto:

```bash
ghostctl deploy-bot
```

Para producción se prefiere el SHA exacto.

### Validación

```bash
systemctl is-active telebotgen.service
systemctl is-active telebotgen-update.path
cat /etc/ADM-db/vercion
systemctl show telebotgen.service -p User --value
journalctl -u telebotgen.service -n 80 --no-pager
```

Resultado esperado:

```text
active
active
V<version>
telebotgen
```

El servicio no debe ejecutarse como `root`.

### Volver a un commit anterior

TeleBotGen no necesita un comando separado de rollback. Se vuelve a desplegar el último commit estable conocido:

```bash
ghostctl deploy-bot "COMMIT_ESTABLE_ANTERIOR"
```

El despliegue también conserva respaldos recientes en `/var/backups/telebotgen`.

---

## 4. Actualizar los tres componentes

Cuando los tres proyectos deben avanzar juntos:

```bash
HEX_SHA="COMMIT_HEX_COMPLETO"
HEX_VERSION="1.0.0-rc.4"
SERVER_SHA="COMMIT_LICENSESERVER_COMPLETO"
BOT_SHA="COMMIT_TELEBOTGEN_COMPLETO"

ghostctl release-all \
  "$HEX_SHA" \
  "$HEX_VERSION" \
  "$SERVER_SHA" \
  "$BOT_SHA"
```

Orden ejecutado:

1. LicenseServer;
2. publicación de Hex Tunnel;
3. TeleBotGen;
4. smoke test;
5. estado general.

Cuando solo cambió un componente, no debe usarse `release-all`; usa su comando individual.

---

## 5. Resumen rápido

| Objetivo | Comando |
|---|---|
| Publicar una nueva versión de Hex Tunnel | `ghostctl publish-hextunnel COMMIT VERSION` |
| Ver releases de Hex Tunnel | `ghostctl releases hextunnel` |
| Activar una release anterior de Hex Tunnel | `ghostctl activate hextunnel VERSION` |
| Actualizar LicenseServer | `ghostctl deploy-server COMMIT` |
| Rollback de LicenseServer | `ghostctl rollback-server` |
| Actualizar TeleBotGen | `ghostctl deploy-bot COMMIT` |
| Actualizar los tres componentes | `ghostctl release-all HEX_COMMIT VERSION SERVER_COMMIT BOT_COMMIT` |
| Estado general | `ghostctl status` |
| Pruebas públicas y locales | `ghostctl smoke` |

---

## 6. Procedimiento recomendado antes de cada despliegue

1. Terminar los cambios en el repositorio correspondiente.
2. Crear el commit.
3. Copiar su SHA completo de 40 caracteres.
4. Confirmar que las GitHub Actions importantes estén en verde.
5. Ejecutar únicamente el comando del componente modificado.
6. Ejecutar sus comprobaciones específicas.
7. Finalizar con:

```bash
ghostctl smoke
ghostctl status
```

No usar `--force` para ocultar fallos de preflight o conflictos de puertos. Un error debe diagnosticarse antes de publicar o desplegar.

---

## 7. Diagnóstico básico

### LicenseServer

```bash
systemctl --no-pager --full status ghost-license-api.service
journalctl -u ghost-license-api.service -n 150 --no-pager
curl -fsS http://127.0.0.1:8080/health | jq .
```

### TeleBotGen

```bash
systemctl --no-pager --full status telebotgen.service
journalctl -u telebotgen.service -n 150 --no-pager
systemctl cat telebotgen.service
```

### Publicación de Hex Tunnel

```bash
set +e
ghostctl publish-hextunnel "COMMIT_SHA_COMPLETO" "VERSION" \
  2>&1 | tee /root/hextunnel-publish.log
rc=${PIPESTATUS[0]}
echo "RC=$rc"
tail -n 150 /root/hextunnel-publish.log
```

No volver a ejecutar repetidamente un despliegue fallido sin conservar el log y entender primero la causa.
