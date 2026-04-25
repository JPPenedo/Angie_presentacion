# Despliegue en Railway

Guía paso a paso para publicar este proyecto Django en Railway con la URL final:

```
https://<tu-subdominio>.up.railway.app/denuncia-verde/
```

> La nueva ruta `/denuncia-verde/` es un alias de `/proyecto-ods16/` y sirve la misma página del proyecto de responsabilidad social ("Denuncia Verde", ODS 16). Ambas URLs funcionan; usa la que prefieras.

---

## 1. Requisitos previos

- Cuenta en [Railway](https://railway.app/) (login con GitHub recomendado).
- Proyecto subido a un repositorio de GitHub.
- (Opcional) [Railway CLI](https://docs.railway.com/guides/cli) si quieres desplegar desde tu máquina sin GitHub.

## 2. Archivos que ya están listos

Estos archivos ya están en el repo y son los que Railway usará:

- `Procfile` — define los procesos `release` (migrate + collectstatic) y `web` (gunicorn).
- `requirements.txt` — incluye `gunicorn`, `whitenoise`, `psycopg2-binary`, `dj-database-url`, `python-decouple`.
- `.python-version` y `runtime.txt` — fijan Python 3.12.
- `Angie_presentacion/settings.py` — preparado para producción (WhiteNoise, `DATABASE_URL`, `ALLOWED_HOSTS` con `.up.railway.app`, `CSRF_TRUSTED_ORIGINS`, `SECURE_PROXY_SSL_HEADER`).
- `.env.example` — referencia de variables; **no subas tu `.env`**.

## 3. Crear el proyecto en Railway

1. Entra a Railway -> **New Project** -> **Deploy from GitHub repo**.
2. Autoriza el repo `Angie_presentacion`.
3. Railway detecta Python automáticamente (Nixpacks) y empezará un primer build (probablemente fallará la primera vez por falta de variables; es normal).

## 4. Añadir base de datos PostgreSQL

1. Dentro del mismo proyecto: **+ New** -> **Database** -> **Add PostgreSQL**.
2. Una vez creada, Railway expone la variable `DATABASE_URL` automáticamente al servicio web.
3. Verifícalo en el servicio web -> **Variables** -> debería aparecer `DATABASE_URL` con un valor `${{Postgres.DATABASE_URL}}`.

> Nota: SQLite (`db.sqlite3`) NO es viable en Railway porque su sistema de archivos es efímero — se reinicia en cada deploy. Por eso usamos Postgres.

## 5. Configurar variables de entorno

En el servicio web -> **Variables** añade (mínimo):

| Variable                | Valor de ejemplo                                                  |
|-------------------------|-------------------------------------------------------------------|
| `SECRET_KEY`            | una cadena aleatoria larga (ver abajo cómo generarla)             |
| `DEBUG`                 | `False`                                                           |
| `ALLOWED_HOSTS`         | (déjalo vacío; settings ya cubre `*.up.railway.app`)              |
| `CSRF_TRUSTED_ORIGINS`  | (déjalo vacío salvo que añadas dominio personalizado)             |
| `DATABASE_URL`          | `${{Postgres.DATABASE_URL}}` (auto si añadiste Postgres)          |
| `SECURE_SSL_REDIRECT`   | `True` (opcional, fuerza HTTPS)                                   |

Para email (opcional, solo si quieres que funcionen recuperación de contraseña / verificación):

| Variable               | Valor                          |
|------------------------|--------------------------------|
| `EMAIL_HOST`           | `smtp.gmail.com`               |
| `EMAIL_PORT`           | `587`                          |
| `EMAIL_USE_TLS`        | `True`                         |
| `EMAIL_HOST_USER`      | tu correo                      |
| `EMAIL_HOST_PASSWORD`  | contraseña de aplicación       |
| `DEFAULT_FROM_EMAIL`   | tu correo                      |

### Generar SECRET_KEY

En tu terminal local:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(60))"
```

Copia el resultado al campo `SECRET_KEY` en Railway.

## 6. Generar el dominio público

1. En el servicio web -> **Settings** -> **Networking** -> **Generate Domain**.
2. Railway crea algo como `https://angie-presentacion-production.up.railway.app`.
3. Si quieres un nombre específico (`dominioproyecto.up.railway.app`), edita el subdominio antes de confirmar (debe estar disponible globalmente).

## 7. Disparar el deploy

- Cualquier push a la rama configurada (por defecto `main`) dispara un build automático.
- Railway ejecutará en orden: instalar deps -> `release` (migrate + collectstatic) -> arrancar `web` (gunicorn).
- Sigue los logs en tiempo real desde la pestaña **Deployments**.

## 8. Verificar

Abre en el navegador:

- `https://<tu-subdominio>.up.railway.app/` — dashboard / login.
- `https://<tu-subdominio>.up.railway.app/denuncia-verde/` — proyecto de responsabilidad social.
- `https://<tu-subdominio>.up.railway.app/proyecto-ods16/` — la misma página por la URL original.

## 9. Crear superusuario en Railway (una sola vez)

Para acceder al admin de Django:

```bash
railway run python manage.py createsuperuser
```

(necesitas Railway CLI logueado y vinculado al proyecto: `railway link`).

---

## Troubleshooting

**Error 400 / DisallowedHost.** El subdominio que generó Railway no termina en `.up.railway.app`. Añádelo manualmente a la variable `ALLOWED_HOSTS` en Railway separado por coma.

**CSRF verification failed.** Falta el origin completo en `CSRF_TRUSTED_ORIGINS`. Añade `https://tu-dominio.up.railway.app` (con esquema).

**Static files 404.** Verifica que en los logs del paso `release` salió `collectstatic` correctamente. Si no, revisa que `whitenoise` esté en `MIDDLEWARE` (ya lo está) y `STORAGES.staticfiles` use `CompressedManifestStaticFilesStorage`.

**psycopg2 error / connection refused.** El servicio web no tiene `DATABASE_URL`. Vuelve al paso 4 y verifica que el plugin de Postgres esté linkeado.

**El deploy queda en "crashed" pero los logs no muestran traceback.** Revisa la pestaña **Build Logs** primero (errores de instalación de paquetes), luego **Deploy Logs** (errores de runtime de gunicorn / Django).
