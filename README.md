# Día del Programador 2026 — backend

API Django/DRF para el registro, pases QR, entrega de completos y torneos del evento de INACAP Sede Arica.

## Instalación local

Requiere Python 3.11 o superior.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py cargar_torneos
python manage.py cargar_carreras
python manage.py createsuperuser
python manage.py runserver
```

La API vive bajo `/api/`; el admin de respaldo está en `/admin-site/`. Los tokens JWT se obtienen en `/api/token/` y se renuevan en `/api/token/refresh/`.

## Variables

`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `SESSION_COOKIE_SECURE` y `CSRF_COOKIE_SECURE` configuran seguridad y frontend. La aplicación carga automáticamente estas variables desde `.env` mediante `python-dotenv`; las variables de entorno reales tienen precedencia. SQLite es el valor predeterminado. Para MySQL defina `DATABASE_ENGINE=mysql` y todas las variables `DATABASE_*` mostradas en `.env.example`.

## PythonAnywhere

1. Clone el repositorio y cree un virtualenv Python 3.11.
2. Instale `requirements.txt` y cree una base MySQL desde el panel.
3. Configure las variables de entorno anteriores en el archivo WSGI (no publique secretos). Use `DEBUG=False`, agregue `https://usuario.pythonanywhere.com` a `CSRF_TRUSTED_ORIGINS` y mantenga `SESSION_COOKIE_SECURE=True` y `CSRF_COOKIE_SECURE=True`.
4. Ajuste el archivo WSGI para añadir el repositorio a `sys.path` y cargar `config.wsgi.application`.
5. Ejecute, en este orden, `python manage.py migrate`, `python manage.py cargar_carreras`, `python manage.py cargar_torneos`, `python manage.py createsuperuser` y `python manage.py collectstatic --noinput`.
6. En **Web > Static files** de PythonAnywhere, asocie la URL `/static/` con la ruta absoluta `<ruta-del-repositorio>/staticfiles`, que contiene los estáticos del admin, y recargue la aplicación.

Siempre que cambien dependencias o archivos estáticos, recopile los recursos del admin con:

```bash
python manage.py collectstatic --noinput
```

## Pruebas

`pytest`


## Operadores del escáner

Cree un usuario distinto para cada persona que operará el escáner, para que el historial de retiros identifique de manera legible quién hizo cada entrega. No deben compartir cuentas. Para estos usuarios basta activar `is_staff` y agregarlos a un grupo con permisos de **solo lectura** en el admin; no necesitan ser superusuarios.

## Datos para el ensayo general

Con los catálogos cargados, genere datos reconocibles de prueba y luego elimínelos así:

```bash
python manage.py datos_prueba --asistentes 60 --equipos 6
python manage.py datos_prueba --limpiar
```

La limpieza solicita escribir `BORRAR` y solo funciona con `DEBUG=True`. En otro entorno se requiere además `--forzar`; compruebe siempre la base seleccionada antes de confirmar.
