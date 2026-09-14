# Día del Programador 2026 — backend

API Django/DRF para el registro, pases QR, entrega de completos y torneos del evento de INACAP Sede Arica.

## Instalación local

Requiere Python 3.11 o superior.

\`\`\`bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py cargar_torneos
python manage.py cargar_carreras
python manage.py createsuperuser
python manage.py runserver
\`\`\`

La API vive bajo \`/api/\`; el admin de respaldo está en \`/admin-site/\`. Los tokens JWT se obtienen en \`/api/token/\` y se renuevan en \`/api/token/refresh/\`.

## Variables

\`SECRET_KEY\`, \`DEBUG\`, \`ALLOWED_HOSTS\` y \`CORS_ALLOWED_ORIGINS\` configuran seguridad y frontend. La aplicación carga automáticamente estas variables desde \`.env\` mediante \`python-dotenv\`; las variables de entorno reales tienen precedencia. SQLite es el valor predeterminado. Para MySQL defina \`DATABASE_ENGINE=mysql\` y todas las variables \`DATABASE_*\` mostradas en \`.env.example\`.

## PythonAnywhere

1. Clone el repositorio y cree un virtualenv Python 3.11.
2. Instale \`requirements.txt\` y cree una base MySQL desde el panel.
3. Configure las variables de entorno anteriores en el archivo WSGI (no publique secretos).
4. Ajuste el archivo WSGI para añadir el repositorio a \`sys.path\` y cargar \`config.wsgi.application\`.
5. Ejecute \`python manage.py migrate\`, \`python manage.py cargar_torneos\`, \`python manage.py cargar_carreras\`, \`python manage.py createsuperuser\` y \`python manage.py collectstatic --noinput\`.
6. Configure los archivos estáticos en el panel Web y recargue la aplicación.

Siempre que cambien dependencias o archivos estáticos, recopile los recursos del admin con:

\`\`\`bash
python manage.py collectstatic --noinput
\`\`\`

## Pruebas

\`pytest\`
