# SUGKA LAB – UGEL IBIR-IMAZA

Aplicación de gestión educativa para la **UGEL IBIR-IMAZA** (Bagua, Amazonas, Perú): mapa georreferenciado de Instituciones Educativas, fichas de monitoreo docente (SIMON, fijas y con preguntas dinámicas), informes de campo, todo con OCR asistido por IA (Azure Document Intelligence, Google Gemini y OpenAI como respaldo) y un panel de administración con roles (especialista/administrador).

Backend en Flask + SQLite; frontend en HTML/CSS/JS sin framework (todo vive en `frontend/index.html`), servido por el mismo proceso Flask.

## Estructura del proyecto

```
APP_SUGKA/
├── app/
│   └── api_server.py       # Backend Flask completo: API REST, auth, OCR, esquema de BD, sirve el frontend
├── frontend/
│   ├── index.html          # SPA completa (HTML + CSS + JS inline, sin build step)
│   ├── sw.js                # Service worker (PWA)
│   └── logo/
├── scripts/                 # Utilidades de importación de datos, uso manual (no corren en producción)
│   ├── import_simon_csv.py
│   ├── import_infraestructura_csv.py
│   └── import_informes_campo_csv.py
├── tests/
│   └── fixtures/             # Insumos para pruebas manuales (ej. fotos de ejemplo para el flujo de OCR)
├── docs/
│   └── referencia/           # Documentos de referencia (padrón, ficha oficial, extracciones) sin uso en código
├── data/
│   ├── database/sugka_demo.db  # BD SQLite semilla (se copia al disco persistente en el primer deploy)
│   └── raw/                    # CSV fuente para los scripts de importación
├── render.yaml               # Configuración de despliegue en Render
└── requirements.txt
```

## Cómo ejecutar en local

```bash
pip install -r requirements.txt
python app/api_server.py
```

Por defecto sirve en `http://localhost:8000` usando la base de datos semilla (`data/database/sugka_demo.db`). Variables de entorno relevantes (ver `.env.example`): credenciales de OCR (`AZURE_DOCUMENT_INTELLIGENCE_*`, `GEMINI_API_KEY`, `OPENAI_API_KEY`), `SUGKA_DB_PATH` para apuntar a otra base de datos, `SEED_ADMIN_PASSWORD`/`SEED_ESPECIALISTA_PASSWORD` para los usuarios semilla.

## Despliegue

Se despliega en Render (`render.yaml`, plan starter con disco persistente en `/var/data` para que la base SQLite sobreviva a los redeploys). El comando de arranque es `gunicorn app.api_server:app`.

## Scripts de importación de datos

Los scripts en `scripts/` son utilidades de un solo uso para cargar datos históricos (CSV de fichas SIMON, censo de infraestructura, features de informes de campo) hacia la base de datos. Se ejecutan manualmente, no forman parte del servicio en producción:

```bash
python scripts/import_simon_csv.py ruta/al/archivo.csv
python scripts/import_infraestructura_csv.py ruta/al/archivo.csv
python scripts/import_informes_campo_csv.py ruta/al/archivo.csv
```
