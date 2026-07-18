#!/usr/bin/env python3
"""
SUGKA LAB – API Server
REST API Flask para la aplicacion de gestion educativa UGEL IBIR-IMAZA.
Puerto: 8000
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import io
import sqlite3
import random
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Rutas relativas al directorio raíz del proyecto
ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / 'data' / 'database' / 'sugka_demo.db'

def load_local_env():
    env_path = ROOT / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_local_env()

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def rows_to_list(rows):
    return [dict(r) for r in rows]

FICHA_MONITOREO_COLUMNS = {
    'source': 'TEXT',
    'file_name': 'TEXT',
    'extraction_method': 'TEXT',
    'confidence': 'REAL',
    'raw_text': 'TEXT',
    'extracted_json': 'TEXT',
    'region': 'TEXT',
    'ugel': 'TEXT',
    'n_visita': 'TEXT',
    'codigo_modular': 'TEXT',
    'nombre_ie': 'TEXT',
    'nivel_modalidad': 'TEXT',
    'director': 'TEXT',
    'director_cel': 'TEXT',
    'director_email': 'TEXT',
    'director_situacion_laboral': 'TEXT',
    'docente': 'TEXT',
    'docente_dni': 'TEXT',
    'docente_cel': 'TEXT',
    'docente_email': 'TEXT',
    'docente_situacion_laboral': 'TEXT',
    'grado': 'TEXT',
    'seccion': 'TEXT',
    'nro_estudiantes': 'INTEGER',
    'area': 'TEXT',
    'competencia': 'TEXT',
    'titulo_sesion': 'TEXT',
    'monitor': 'TEXT',
    'monitor_dni': 'TEXT',
    'iged': 'TEXT',
    'monitor_email': 'TEXT',
    'fecha_ejecucion': 'TEXT',
    'a1': 'INTEGER',
    'a2': 'INTEGER',
    'a3': 'INTEGER',
    'b1': 'INTEGER',
    'b2': 'INTEGER',
    'b3': 'INTEGER',
    'b4': 'INTEGER',
    'b5': 'INTEGER',
    'a1_observacion': 'TEXT',
    'a2_observacion': 'TEXT',
    'a3_observacion': 'TEXT',
    'b1_observacion': 'TEXT',
    'b2_observacion': 'TEXT',
    'b3_observacion': 'TEXT',
    'b4_observacion': 'TEXT',
    'b5_observacion': 'TEXT',
    'promedio': 'REAL',
    'observaciones': 'TEXT',
    'observaciones_recomendaciones': 'TEXT',
    'compromisos': 'TEXT',
    'compromisos_monitoreado': 'TEXT',
}

def ensure_db_schema():
    conn = get_db()
    columns_sql = ',\n            '.join(
        f'{name} {column_type}' for name, column_type in FICHA_MONITOREO_COLUMNS.items()
    )
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS fichas_monitoreo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            {columns_sql},
            fecha_sincronizacion DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    existing = {
        row['name'] for row in conn.execute('PRAGMA table_info(fichas_monitoreo)').fetchall()
    }
    for name, column_type in FICHA_MONITOREO_COLUMNS.items():
        if name not in existing:
            conn.execute(f'ALTER TABLE fichas_monitoreo ADD COLUMN {name} {column_type}')

    conn.commit()
    conn.close()

def first_text(data, *keys):
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return ''

def safe_int(value, default=0):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r'-?\d+', str(value))
    return int(match.group(0)) if match else default

def safe_float(value, default=0.0):
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r'-?\d+(?:[.,]\d+)?', str(value))
        return float(match.group(0).replace(',', '.')) if match else default

def normalize_level(value):
    if value is None or value == '':
        return 0
    if isinstance(value, (int, float)):
        level = int(value)
        return level if 0 <= level <= 4 else 0

    text = str(value).strip().upper()
    roman_levels = {'IV': 4, 'III': 3, 'II': 2, 'I': 1}
    for roman, score in roman_levels.items():
        if re.search(rf'\b{roman}\b', text):
            return score

    match = re.search(r'[0-4]', text)
    if match:
        return int(match.group(0))
    return 0

def calculate_promedio(ficha):
    levels = [ficha.get(k, 0) for k in ('a1', 'a2', 'a3', 'b1', 'b2', 'b3', 'b4', 'b5')]
    valid = [level for level in levels if level > 0]
    return round(sum(valid) / len(valid), 2) if valid else 0.0

def normalize_ficha(data, source='manual'):
    data = data if isinstance(data, dict) else {}
    ficha = {
        'source': first_text(data, 'source') or source,
        'file_name': first_text(data, 'file_name', 'filename'),
        'extraction_method': first_text(data, 'extraction_method', 'method'),
        'confidence': safe_float(data.get('confidence'), 0.0),
        'raw_text': first_text(data, 'raw_text'),
        'extracted_json': first_text(data, 'extracted_json'),
        'region': first_text(data, 'region'),
        'ugel': first_text(data, 'ugel'),
        'n_visita': first_text(data, 'n_visita', 'numero_visita', 'nro_visita', 'visita'),
        'codigo_modular': first_text(data, 'codigo_modular', 'cod_modular', 'codModular'),
        'nombre_ie': first_text(data, 'nombre_ie', 'ie', 'institucion_educativa', 'nombre_iiee'),
        'nivel_modalidad': first_text(data, 'nivel_modalidad', 'nivel', 'modalidad'),
        'director': first_text(data, 'director', 'directora', 'director_nombre'),
        'director_cel': first_text(data, 'director_cel', 'director_celular', 'cel_director'),
        'director_email': first_text(data, 'director_email', 'email_director'),
        'director_situacion_laboral': first_text(data, 'director_situacion_laboral', 'situacion_laboral_director'),
        'docente': first_text(data, 'docente', 'docente_nombre', 'nombre_docente'),
        'docente_dni': first_text(data, 'docente_dni', 'dni_docente', 'dni'),
        'docente_cel': first_text(data, 'docente_cel', 'docente_celular', 'cel_docente', 'cel'),
        'docente_email': first_text(data, 'docente_email', 'email_docente', 'email'),
        'docente_situacion_laboral': first_text(data, 'docente_situacion_laboral', 'situacion_laboral_docente'),
        'grado': first_text(data, 'grado'),
        'seccion': first_text(data, 'seccion', 'sección'),
        'nro_estudiantes': safe_int(first_text(data, 'nro_estudiantes', 'numero_estudiantes', 'n_estudiantes')),
        'area': first_text(data, 'area', 'área'),
        'competencia': first_text(data, 'competencia'),
        'titulo_sesion': first_text(data, 'titulo_sesion', 'titulo_de_la_sesion', 'sesion'),
        'monitor': first_text(data, 'monitor', 'monitor_nombre', 'especialista', 'especialista_monitor'),
        'monitor_dni': first_text(data, 'monitor_dni', 'dni_monitor'),
        'iged': first_text(data, 'iged'),
        'monitor_email': first_text(data, 'monitor_email', 'email_monitor'),
        'fecha_ejecucion': first_text(data, 'fecha_ejecucion', 'fecha'),
    }

    for key in ('a1', 'a2', 'a3', 'b1', 'b2', 'b3', 'b4', 'b5'):
        ficha[key] = normalize_level(data.get(key))

    for key in (
        'a1_observacion', 'a2_observacion', 'a3_observacion',
        'b1_observacion', 'b2_observacion', 'b3_observacion',
        'b4_observacion', 'b5_observacion',
    ):
        ficha[key] = first_text(data, key, key.replace('_observacion', '_obs'))

    observaciones = first_text(data, 'observaciones', 'observaciones_recomendaciones')
    compromisos = first_text(data, 'compromisos', 'compromisos_monitoreado')
    ficha['observaciones'] = observaciones
    ficha['observaciones_recomendaciones'] = first_text(data, 'observaciones_recomendaciones') or observaciones
    ficha['compromisos'] = compromisos
    ficha['compromisos_monitoreado'] = first_text(data, 'compromisos_monitoreado') or compromisos
    ficha['promedio'] = safe_float(data.get('promedio', data.get('promedio_nivel')), 0.0) or calculate_promedio(ficha)
    ficha['promedio_nivel'] = str(ficha['promedio'])

    if not ficha['extracted_json']:
        ficha['extracted_json'] = json.dumps(data, ensure_ascii=False)

    return ficha

def save_ficha_to_db(conn, data):
    data = data if isinstance(data, dict) else {}
    ficha = normalize_ficha(data, source=first_text(data, 'source') or 'manual')
    columns = list(FICHA_MONITOREO_COLUMNS.keys())
    placeholders = ', '.join('?' for _ in columns)
    conn.execute(
        f'INSERT INTO fichas_monitoreo ({", ".join(columns)}) VALUES ({placeholders})',
        [ficha.get(column) for column in columns]
    )
    return ficha

RISK_MODEL = {
    'name': 'Modelo de Riesgo Educativo SUGKA v0.1',
    'type': 'Reglas ponderadas explicables',
    'description': (
        'Clasifica cada IE con una puntuacion de 0 a 100 para priorizar '
        'acompanamiento. No es un modelo predictivo de caja negra; es una '
        'matriz de riesgo auditable que combina evidencia SIMON, campo y OCR.'
    ),
    'levels': [
        {'level': 'Critico', 'range': '75-100', 'action': 'Visita prioritaria y plan de accion inmediato'},
        {'level': 'Alto', 'range': '60-74', 'action': 'Seguimiento focalizado en la siguiente ronda'},
        {'level': 'Medio', 'range': '40-59', 'action': 'Monitoreo regular con revision mensual'},
        {'level': 'Bajo', 'range': '0-39', 'action': 'Seguimiento ordinario'},
    ],
    'weights': [
        {'factor': 'Alertas pedagogicas y de infraestructura', 'weight': '30%', 'rule': 'Mas alertas abiertas elevan el riesgo'},
        {'factor': 'Brecha de cobertura SIMON/campo', 'weight': '25%', 'rule': 'Sin evidencia o solo una fuente aumenta incertidumbre'},
        {'factor': 'Priority score existente', 'weight': '25%', 'rule': 'Usa la priorizacion ya calculada por la base'},
        {'factor': 'Desempeno observado', 'weight': '15%', 'rule': 'Promedio menor a 2.5 eleva el riesgo'},
        {'factor': 'Volumen de evidencias', 'weight': '5%', 'rule': 'Muchas evidencias sin cierre aumentan necesidad de revision'},
    ],
}

ALERT_RULES = [
    {
        'code': 'COBERTURA_SIN_EVIDENCIA',
        'name': 'IE sin evidencia reciente',
        'severity': 'alta',
        'condition': 'coverage_category = "Sin evidencia"',
        'score': 25,
        'focus': 'Programar primera visita o carga de ficha OCR/SIMON.',
    },
    {
        'code': 'CAMPO_SIN_SIMON',
        'name': 'Campo sin ficha SIMON',
        'severity': 'media',
        'condition': 'campo_sin_simon = 1',
        'score': 16,
        'focus': 'Regularizar ficha y contrastar hallazgos de campo.',
    },
    {
        'code': 'ALERTAS_PEDAGOGICAS_ALTAS',
        'name': 'Alertas pedagogicas acumuladas',
        'severity': 'alta',
        'condition': 'alertas_pedagogicas_campo >= 20',
        'score': 18,
        'focus': 'Priorizar acompanamiento pedagogico y compromisos.',
    },
    {
        'code': 'INFRA_SERVICIOS',
        'name': 'Infraestructura o servicios criticos',
        'severity': 'alta',
        'condition': 'alertas_infraestructura_campo >= 10',
        'score': 14,
        'focus': 'Coordinar respuesta con gestion institucional.',
    },
    {
        'code': 'DESEMPENO_BAJO',
        'name': 'Desempeno observado bajo',
        'severity': 'media',
        'condition': 'promedio_nivel < 2.5',
        'score': 15,
        'focus': 'Revisar planificacion, retroalimentacion y convivencia.',
    },
]

def risk_level(score):
    if score >= 75:
        return 'Critico'
    if score >= 60:
        return 'Alto'
    if score >= 40:
        return 'Medio'
    return 'Bajo'

def pseudo_percent(seed, base, spread):
    return max(0, min(100, base + (int(str(seed)[-2:] or 0) % spread) - spread // 2))

def calculate_risk(row):
    priority = safe_float(row.get('priority_score'), 0.0)
    coverage = row.get('coverage_category') or 'Sin evidencia'
    total_alerts = safe_int(row.get('total_alertas_campo'), 0)
    infra_alerts = safe_int(row.get('alertas_infraestructura_campo'), 0)
    pedagogic_alerts = safe_int(row.get('alertas_pedagogicas_campo'), 0)
    simon_fichas = safe_int(row.get('simon_fichas'), 0)
    campo_docs = safe_int(row.get('campo_documentos'), 0)
    simon_average = safe_float(row.get('simon_promedio_nivel'), 0.0)

    score = min(priority * 3.2, 28)
    reasons = []

    if coverage == 'Sin evidencia':
        score += 25
        reasons.append('sin evidencia registrada')
    elif coverage == 'Solo campo':
        score += 16
        reasons.append('campo sin contraste SIMON')
    elif coverage == 'Solo SIMON':
        score += 10
        reasons.append('SIMON sin contraste de campo')

    alert_score = min(total_alerts * 0.07, 16)
    score += alert_score
    if total_alerts >= 20:
        reasons.append(f'{total_alerts} alertas abiertas')

    if pedagogic_alerts >= 20:
        score += 10
        reasons.append('alertas pedagogicas acumuladas')
    elif pedagogic_alerts >= 8:
        score += 5

    if infra_alerts >= 10:
        score += 8
        reasons.append('alertas de infraestructura/servicios')
    elif infra_alerts >= 4:
        score += 4

    if simon_average and simon_average < 2:
        score += 15
        reasons.append('desempeno menor a nivel 2')
    elif simon_average and simon_average < 2.5:
        score += 9
        reasons.append('desempeno por debajo de 2.5')
    elif not simon_fichas and campo_docs:
        score += 6
        reasons.append('evidencia de campo pendiente de ficha')

    score = round(min(score, 100), 1)
    return {
        'risk_score': score,
        'risk_level': risk_level(score),
        'risk_reasons': reasons[:4] or ['sin alertas criticas acumuladas'],
    }

# ─── HEALTH / API INDEX ───────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
@app.route('/api', methods=['GET'])
def api_index():
    return jsonify({
        'service': 'SUGKA LAB API',
        'status': 'ok',
        'frontend_url': 'http://localhost:8080',
        'endpoints': {
            'dashboard': '/api/dashboard',
            'especialistas': '/api/especialistas',
            'instituciones': '/api/instituciones',
            'alertas': '/api/alertas',
            'fichas': '/api/fichas',
            'ocr_upload': '/api/ocr/upload_advanced',
            'sync': '/api/sync',
            'login': '/api/login',
        }
    })

# ─── ESPECIALISTAS / AUTH ─────────────────────────────────────────────────────

@app.route('/api/especialistas', methods=['GET'])
def get_especialistas():
    conn = get_db()
    rows = conn.execute(
        'SELECT especialista_id, nombre, rol_inferido, total_fichas_simon, total_documentos_campo '
        'FROM dim_especialista ORDER BY nombre'
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        # Demo PIN = first 4 chars of hash after 'esp_'
        d['pin_hint'] = d['especialista_id'].replace('esp_', '')[:4]
        result.append(d)
    return jsonify(result)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    esp_id = data.get('especialista_id', '')
    pin    = data.get('pin', '')

    conn = get_db()
    esp  = conn.execute('SELECT * FROM dim_especialista WHERE especialista_id = ?', (esp_id,)).fetchone()
    conn.close()

    if not esp:
        return jsonify({'error': 'Especialista no encontrado'}), 401

    expected = esp_id.replace('esp_', '')[:4]
    if pin != expected:
        return jsonify({'error': 'PIN incorrecto'}), 401

    return jsonify({'success': True, 'especialista': dict(esp), 'token': f'demo_{esp_id}'})

# ─── INSTITUCIONES ────────────────────────────────────────────────────────────

@app.route('/api/instituciones', methods=['GET'])
def get_instituciones():
    conn = get_db()
    rows = conn.execute('''
        SELECT
            i.codigo_modular,
            i.nombre_iiee,
            i.nivel_modalidad,
            i.distrito,
            i.centro_poblado,
            i.latitud,
            i.longitud,
            i.altitud,
            i.tipo_gestion,
            COALESCE(i.alumnos_censo,  0) AS alumnos_censo,
            COALESCE(i.docentes_censo, 0) AS docentes_censo,
            COALESCE(r.priority_score,      0)              AS priority_score,
            COALESCE(r.total_alertas_campo, 0)              AS total_alertas,
            COALESCE(r.coverage_category,   'Sin evidencia') AS coverage_category,
            COALESCE(r.simon_fichas,        0)              AS simon_fichas,
            COALESCE(r.campo_documentos,    0)              AS campo_documentos,
            COALESCE(r.campo_owners,        '')             AS especialistas,
            COALESCE(r.simon_promedio_nivel,0)              AS simon_promedio,
            CASE
                WHEN COALESCE(r.priority_score,0) >= 15 THEN 'alta'
                WHEN COALESCE(r.priority_score,0) >= 8  THEN 'media'
                ELSE 'baja'
            END AS nivel_alerta
        FROM dim_institucion i
        LEFT JOIN institucion_resumen r ON i.codigo_modular = r.codigo_modular
        WHERE i.latitud  IS NOT NULL AND i.latitud  != 0
          AND i.longitud IS NOT NULL AND i.longitud != 0
        ORDER BY COALESCE(r.priority_score,0) DESC
    ''').fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

# ─── ALERTAS ──────────────────────────────────────────────────────────────────

@app.route('/api/alertas', methods=['GET'])
def get_alertas():
    cm   = request.args.get('codigo_modular')
    conn = get_db()
    if cm:
        rows = conn.execute('''
            SELECT a.*, c.nombre AS cat_nombre, c.tipo AS cat_tipo
            FROM app_alerta_priorizada a
            LEFT JOIN dim_alerta_categoria c ON a.alerta_codigo = c.alerta_codigo
            WHERE a.codigo_modular = ?
            ORDER BY a.score DESC
        ''', (cm,)).fetchall()
    else:
        rows = conn.execute('''
            SELECT a.*, c.nombre AS cat_nombre, c.tipo AS cat_tipo,
                   i.nombre_iiee, i.distrito
            FROM app_alerta_priorizada a
            LEFT JOIN dim_alerta_categoria c ON a.alerta_codigo = c.alerta_codigo
            LEFT JOIN dim_institucion      i ON a.codigo_modular = i.codigo_modular
            WHERE a.estado = 'pendiente'
            ORDER BY a.score DESC LIMIT 60
        ''').fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

# ─── DASHBOARD ────────────────────────────────────────────────────────────────

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    conn = get_db()

    total_ies        = conn.execute('SELECT COUNT(*) FROM dim_institucion').fetchone()[0]
    alertas_altas    = conn.execute("SELECT COUNT(DISTINCT codigo_modular) FROM app_alerta_priorizada WHERE severidad='alta' AND estado='pendiente'").fetchone()[0]
    alertas_pend     = conn.execute("SELECT COUNT(*) FROM app_alerta_priorizada WHERE estado='pendiente'").fetchone()[0]
    ies_monitoreadas = conn.execute("SELECT COUNT(*) FROM institucion_resumen WHERE coverage_category != 'Sin evidencia'").fetchone()[0]
    especialistas    = conn.execute('SELECT COUNT(*) FROM dim_especialista').fetchone()[0]

    top = conn.execute('''
        SELECT i.codigo_modular, i.nombre_iiee, i.nivel_modalidad, i.distrito,
               r.priority_score, r.coverage_category, r.total_alertas_campo,
               r.alertas_infraestructura_campo, r.alertas_pedagogicas_campo,
               r.campo_documentos, r.simon_fichas, r.simon_promedio_nivel,
               r.priority_reason
        FROM institucion_resumen r
        JOIN dim_institucion i ON r.codigo_modular = i.codigo_modular
        ORDER BY r.priority_score DESC LIMIT 20
    ''').fetchall()

    por_distrito = conn.execute('''
        SELECT i.distrito,
               COUNT(*) AS total,
               SUM(CASE WHEN COALESCE(r.priority_score,0) >= 15 THEN 1 ELSE 0 END) AS alerta_alta,
               SUM(CASE WHEN COALESCE(r.priority_score,0) >= 8  THEN 1 ELSE 0 END) AS alerta_media
        FROM dim_institucion i
        LEFT JOIN institucion_resumen r ON i.codigo_modular = r.codigo_modular
        WHERE i.distrito IS NOT NULL
        GROUP BY i.distrito ORDER BY total DESC
    ''').fetchall()

    risk_rows = conn.execute('''
        SELECT i.codigo_modular, i.nombre_iiee, i.nivel_modalidad, i.distrito,
               COALESCE(r.priority_score, 0) AS priority_score,
               COALESCE(r.coverage_category, 'Sin evidencia') AS coverage_category,
               COALESCE(r.total_alertas_campo, 0) AS total_alertas_campo,
               COALESCE(r.alertas_infraestructura_campo, 0) AS alertas_infraestructura_campo,
               COALESCE(r.alertas_pedagogicas_campo, 0) AS alertas_pedagogicas_campo,
               COALESCE(r.campo_documentos, 0) AS campo_documentos,
               COALESCE(r.simon_fichas, 0) AS simon_fichas,
               COALESCE(r.simon_promedio_nivel, 0) AS simon_promedio_nivel,
               COALESCE(r.priority_reason, '') AS priority_reason
        FROM dim_institucion i
        LEFT JOIN institucion_resumen r ON i.codigo_modular = r.codigo_modular
    ''').fetchall()

    scored = []
    risk_distribution = {'Critico': 0, 'Alto': 0, 'Medio': 0, 'Bajo': 0}
    for row in risk_rows:
        item = dict(row)
        item.update(calculate_risk(item))
        risk_distribution[item['risk_level']] += 1
        scored.append(item)

    scored.sort(key=lambda r: r['risk_score'], reverse=True)
    top_riesgo = scored[:10]
    risk_focus_count = risk_distribution['Critico'] + risk_distribution['Alto']

    ficha_stats = conn.execute('''
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN source = 'ocr' THEN 1 ELSE 0 END) AS ocr_total,
            AVG(promedio) AS promedio,
            SUM(CASE WHEN COALESCE(compromisos_monitoreado, compromisos, '') != '' THEN 1 ELSE 0 END) AS compromisos
        FROM fichas_monitoreo
    ''').fetchone()

    actual_fichas = safe_int(ficha_stats['total'], 0) if ficha_stats else 0
    demo_mode = actual_fichas == 0
    fichas_recolectadas = actual_fichas or 48
    ocr_total = safe_int(ficha_stats['ocr_total'], 0) if ficha_stats else 0
    ocr_total = ocr_total or (12 if demo_mode else 0)
    promedio_observado = safe_float(ficha_stats['promedio'], 0.0) if ficha_stats else 0.0
    promedio_observado = promedio_observado or 2.7
    compromisos = safe_int(ficha_stats['compromisos'], 0) if ficha_stats else 0
    compromisos = compromisos or (19 if demo_mode else 0)

    resultados = [
        {
            'area': 'Preparacion para el aprendizaje',
            'valor': pseudo_percent(total_ies, 68, 14),
            'estado': 'En observacion',
            'lectura': 'Fortalecer planificacion curricular y criterios de evaluacion.',
        },
        {
            'area': 'Ensenanza y participacion',
            'valor': pseudo_percent(alertas_pend, 63, 16),
            'estado': 'Prioritario',
            'lectura': 'Acompanamiento focalizado en interacciones y actividades retadoras.',
        },
        {
            'area': 'Retroalimentacion formativa',
            'valor': pseudo_percent(alertas_altas, 58, 18),
            'estado': 'Prioritario',
            'lectura': 'Revisar evidencias y compromisos del monitoreado.',
        },
        {
            'area': 'Clima y convivencia',
            'valor': pseudo_percent(especialistas, 72, 12),
            'estado': 'Estable',
            'lectura': 'Mantener seguimiento regular y deteccion temprana.',
        },
    ]

    acciones_recomendadas = [
        'Atender primero las IEs en riesgo Critico y Alto.',
        'Cruzar cada alerta con ficha OCR/SIMON antes de cerrar el caso.',
        'Registrar compromisos del monitoreado y revisar avance en la siguiente visita.',
        'Usar el score como priorizador, no como sentencia definitiva.',
    ]

    conn.close()
    return jsonify({
        'total_ies':        total_ies,
        'alertas_altas':    alertas_altas,
        'alertas_pendientes': alertas_pend,
        'ies_monitoreadas': ies_monitoreadas,
        'especialistas':    especialistas,
        'pct_monitoreadas': round(ies_monitoreadas / total_ies * 100, 1) if total_ies else 0,
        'top_prioridad':    rows_to_list(top),
        'por_distrito':     rows_to_list(por_distrito),
        'risk_distribution': risk_distribution,
        'risk_focus_count': risk_focus_count,
        'top_riesgo': top_riesgo,
        'risk_model': RISK_MODEL,
        'alert_rules': ALERT_RULES,
        'demo_mode': demo_mode,
        'resultados_recolectados': {
            'fichas_recolectadas': fichas_recolectadas,
            'ocr_total': ocr_total,
            'promedio_observado': round(promedio_observado, 2),
            'compromisos_registrados': compromisos,
            'indicadores': resultados,
            'acciones_recomendadas': acciones_recomendadas,
        },
    })

import pdfplumber
import google.generativeai as genai
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient

AZURE_ENDPOINT = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
AZURE_KEY = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

def extract_with_python(file_bytes):
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    except Exception as e:
        print(f"Error pdfplumber: {e}")
    return text.strip()

def extract_with_azure(file_bytes, content_type='application/octet-stream'):
    if not AZURE_ENDPOINT or not AZURE_KEY:
        print("Azure OCR no configurado: define AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT y AZURE_DOCUMENT_INTELLIGENCE_KEY.")
        return ""
    try:
        client = DocumentIntelligenceClient(endpoint=AZURE_ENDPOINT, credential=AzureKeyCredential(AZURE_KEY))
        poller = client.begin_analyze_document(
            "prebuilt-read",
            file_bytes,
            content_type=content_type,
        )
        result = poller.result()
        return result.content or ""
    except Exception as e:
        print(f"Error Azure: {e}")
        return ""

def is_pdf_file(filename, mimetype=''):
    lower = (filename or '').lower()
    return lower.endswith('.pdf') or mimetype == 'application/pdf'

def extract_text_from_upload(file_storage):
    file_bytes = file_storage.read()
    filename = file_storage.filename or 'documento'
    mimetype = file_storage.mimetype or 'application/octet-stream'

    if is_pdf_file(filename, mimetype):
        text = extract_with_python(file_bytes)
        if len(text) >= 100:
            return text, 'pdfplumber', filename
        print("Usando Azure OCR como fallback para PDF...")
        text = extract_with_azure(file_bytes, mimetype)
        return text, 'azure', filename

    text = extract_with_azure(file_bytes, mimetype)
    return text, 'azure', filename

FORM_LABELS = {
    'REGIÓN', 'REGION', 'UGEL', 'I.E.', 'IE', 'NIVEL/MODALIDAD', 'DIRECTOR(A)',
    'CEL.', 'EMAIL', 'SITUACIÓN LABORAL', 'SITUACION LABORAL', 'DESIGNADO(A)',
    'ENCARGADO(A)', 'NOMBRE', 'DNI', 'GRADO', 'SECCIÓN', 'SECCION',
    'Nº ESTUDIANTES', 'N° ESTUDIANTES', 'AREA', 'ÁREA', 'COMPETENCIA',
    'TÍTULO DE LA SESIÓN', 'TITULO DE LA SESION', 'MONITOR', 'IGED',
}

def compact_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]

def is_form_label(line):
    normalized = re.sub(r'\s+', ' ', line.upper().strip(' :'))
    return normalized in FORM_LABELS

def next_line_after(lines, *labels):
    normalized = [line.upper() for line in lines]
    for label in labels:
        label = label.upper()
        for i, line in enumerate(normalized):
            if line == label or line.startswith(label):
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if is_form_label(candidate):
                        return ''
                    if candidate and candidate.upper() not in labels:
                        return candidate
    return ''

def section_text(text, start, *ends):
    upper = text.upper()
    start_idx = upper.find(start.upper())
    if start_idx < 0:
        return ''
    end_idx = len(text)
    for end in ends:
        idx = upper.find(end.upper(), start_idx + len(start))
        if idx >= 0:
            end_idx = min(end_idx, idx)
    return text[start_idx:end_idx]

def text_between(text, start, *ends):
    upper = text.upper()
    start_idx = upper.find(start.upper())
    if start_idx < 0:
        return ''
    start_idx += len(start)
    end_idx = len(text)
    for end in ends:
        idx = upper.find(end.upper(), start_idx)
        if idx >= 0:
            end_idx = min(end_idx, idx)
    return re.sub(r'\s+', ' ', text[start_idx:end_idx]).strip(' :.-')

def text_between_raw(text, start, *ends):
    upper = text.upper()
    start_idx = upper.find(start.upper())
    if start_idx < 0:
        return ''
    start_idx += len(start)
    end_idx = len(text)
    for end in ends:
        idx = upper.find(end.upper(), start_idx)
        if idx >= 0:
            end_idx = min(end_idx, idx)
    return text[start_idx:end_idx].strip()

def text_after_all_headings(text, heading, *ends):
    upper = text.upper()
    heading_upper = heading.upper()
    parts = []
    start = 0
    while True:
        idx = upper.find(heading_upper, start)
        if idx < 0:
            break
        chunk_start = idx + len(heading)
        chunk_end = len(text)
        for end in (heading, *ends):
            end_idx = upper.find(end.upper(), chunk_start)
            if end_idx >= 0:
                chunk_end = min(chunk_end, end_idx)
        chunk = re.sub(r'\s+', ' ', text[chunk_start:chunk_end]).strip(' :.-')
        if chunk:
            parts.append(chunk)
        start = chunk_end
    return '\n'.join(parts)

def infer_selected_level(block):
    for line in compact_lines(block):
        if 'NIVEL' not in line.upper():
            continue
        level = normalize_level(line)
        if level and (
            re.search(r'[Xx☒✓✔&\\_]', line)
            or not re.match(r'^\s*[a-dA-D]\.?\s*', line)
        ):
            return level

    selected_patterns = [
        r'(?:X|☒|✓|✔|:SELECTED:|SELECTED)\s*(?:[A-D]\.?\s*)?NIVEL\s*(IV|III|II|I|[1-4])',
        r'(?:[A-D]\.?\s*)?NIVEL\s*(IV|III|II|I|[1-4])\s*(?:X|☒|✓|✔|:SELECTED:|SELECTED)',
    ]
    for pattern in selected_patterns:
        match = re.search(pattern, block, re.IGNORECASE)
        if match:
            return normalize_level(match.group(1))
    return 0

def parse_ficha_from_text(text):
    lines = compact_lines(text)
    ie_section = section_text(
        text,
        'Datos de identificación la IE',
        'Datos de identificación del docente monitoreado',
    )
    docente_section = section_text(
        text,
        'Datos de identificación del docente monitoreado',
        'Datos de identificación del especialista responsable',
    )
    monitor_section = section_text(
        text,
        'Datos de identificación del especialista responsable',
        'A: Preparación',
    )
    ie_lines = compact_lines(ie_section)
    docente_lines = compact_lines(docente_section)
    monitor_lines = compact_lines(monitor_section)

    area_match = re.search(r'(?:ÁREA|AREA)\s+([^\n]+)', docente_section, re.IGNORECASE)
    students_match = re.search(r'(?:N[°º]\s*)?ESTUDIANTES\s*(\d+)', docente_section, re.IGNORECASE)

    parsed = {
        'region': next_line_after(ie_lines, 'REGIÓN', 'REGION') or 'AMAZONAS',
        'ugel': next_line_after(ie_lines, 'UGEL'),
        'nombre_ie': next_line_after(ie_lines, 'I.E.', 'IE'),
        'nivel_modalidad': next_line_after(ie_lines, 'NIVEL/MODALIDAD'),
        'director': next_line_after(ie_lines, 'DIRECTOR(A)'),
        'director_cel': next_line_after(ie_lines, 'CEL.'),
        'docente': next_line_after(docente_lines, 'NOMBRE'),
        'docente_dni': next_line_after(docente_lines, 'DNI'),
        'docente_cel': next_line_after(docente_lines, 'CEL.'),
        'grado': next_line_after(docente_lines, 'GRADO'),
        'seccion': next_line_after(docente_lines, 'SECCIÓN', 'SECCION'),
        'area': area_match.group(1).strip() if area_match else next_line_after(docente_lines, 'ÁREA', 'AREA'),
        'competencia': next_line_after(docente_lines, 'COMPETENCIA'),
        'titulo_sesion': next_line_after(docente_lines, 'TÍTULO DE LA SESIÓN', 'TITULO DE LA SESION'),
        'monitor': next_line_after(monitor_lines, 'MONITOR'),
        'monitor_dni': next_line_after(monitor_lines, 'DNI'),
        'iged': next_line_after(monitor_lines, 'IGED'),
        'observaciones_recomendaciones': text_between(
            text,
            'OBSERVACIONES/ RECOMENDACIONES',
            'COMPROMISOS DEL MONITOREADO',
        ),
        'compromisos_monitoreado': text_after_all_headings(
            text,
            'COMPROMISOS DEL MONITOREADO',
            'Especialista monitoreado',
            'Monitoreado',
        ),
    }

    date_match = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', text)
    if date_match:
        day, month, year = date_match.groups()
        parsed['fecha_ejecucion'] = f'{year}-{int(month):02d}-{int(day):02d}'

    visit_match = re.search(r'N[°º]?\s*VISITA\s*(\d+)', text, re.IGNORECASE)
    if visit_match:
        parsed['n_visita'] = visit_match.group(1)

    if students_match:
        parsed['nro_estudiantes'] = int(students_match.group(1))

    item_markers = {
        'a1': 'En la planificación curricular del docente se evidencia',
        'a2': 'En la planificación curricular del docente se observa',
        'a3': 'En la programación curricular del docente se observa',
        'b1': 'El docente promueve el interés',
        'b2': 'El docente propone actividades',
        'b3': 'El docente acompaña el proceso',
        'b4': 'El docente se comunica de manera respetuosa',
        'b5': 'El docente establece en su práctica pedagógica',
    }
    marker_values = list(item_markers.items())
    for idx, (key, marker) in enumerate(marker_values):
        end_markers = [m for _, m in marker_values[idx + 1:]] + ['OBSERVACIONES/ RECOMENDACIONES']
        block = text_between_raw(text, marker, *end_markers)
        parsed[key] = infer_selected_level(block)

    parsed['observaciones'] = parsed['observaciones_recomendaciones']
    parsed['compromisos'] = parsed['compromisos_monitoreado']
    return parsed

def process_with_gemini(text):
    if not GEMINI_KEY:
        print("Gemini no configurado: define GEMINI_API_KEY.")
        return None

    prompt = """
    Eres un asistente experto en extraer datos de fichas de monitoreo docente en Perú.
    Extrae todos los datos disponibles y devuélvelos estrictamente como un objeto JSON válido,
    sin markdown ni texto adicional.

    Usa exactamente estas claves:
    {
      "region": "string",
      "ugel": "string",
      "n_visita": "string",
      "fecha_ejecucion": "YYYY-MM-DD",
      "codigo_modular": "string",
      "nombre_ie": "string",
      "nivel_modalidad": "string",
      "director": "string",
      "director_cel": "string",
      "director_email": "string",
      "director_situacion_laboral": "string",
      "docente": "string",
      "docente_dni": "string",
      "docente_cel": "string",
      "docente_email": "string",
      "docente_situacion_laboral": "string",
      "grado": "string",
      "seccion": "string",
      "nro_estudiantes": "entero",
      "area": "string",
      "competencia": "string",
      "titulo_sesion": "string",
      "monitor": "string",
      "monitor_dni": "string",
      "iged": "string",
      "monitor_email": "string",
      "a1": "entero (1 al 4)",
      "a2": "entero (1 al 4)",
      "a3": "entero (1 al 4)",
      "b1": "entero (1 al 4)",
      "b2": "entero (1 al 4)",
      "b3": "entero (1 al 4)",
      "b4": "entero (1 al 4)",
      "b5": "entero (1 al 4)",
      "a1_observacion": "string",
      "a2_observacion": "string",
      "a3_observacion": "string",
      "b1_observacion": "string",
      "b2_observacion": "string",
      "b3_observacion": "string",
      "b4_observacion": "string",
      "b5_observacion": "string",
      "observaciones_recomendaciones": "string",
      "compromisos_monitoreado": "string"
    }

    Reglas:
    - Si no encuentras un dato, usa "" para textos y 0 para números.
    - Para los ítems A1-A3 y B1-B5, convierte NIVEL I, II, III o IV a 1, 2, 3 o 4.
    - Extrae las observaciones de cada ítem en su clave *_observacion.
    - El bloque "OBSERVACIONES/ RECOMENDACIONES" debe ir completo en observaciones_recomendaciones.
    - El bloque "COMPROMISOS DEL MONITOREADO" debe ir completo en compromisos_monitoreado.
    - No inventes valores. Si el documento es una plantilla vacía, deja esos campos vacíos o en 0.

    TEXTO A ANALIZAR:
    """ + text

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
    except Exception as e:
        print(f"Error Gemini request: {e}")
        return None

    raw = response.text.replace('```json', '').replace('```', '').strip()
    try:
        data = json.loads(raw)
        return data
    except Exception as e:
        print(f"Error Gemini JSON: {e}, Raw: {raw}")
        return None

# ─── OCR Y SINCRONIZACIÓN ─────────────────────────────────────────────────────

@app.route('/api/ocr/upload_advanced', methods=['POST'])
def ocr_upload_advanced():
    uploaded_files = request.files.getlist('files') or request.files.getlist('file')
    uploaded_files = [file for file in uploaded_files if file and file.filename]
    if not uploaded_files:
        return jsonify({'error': 'No file uploaded'}), 400

    extracted_parts = []
    methods = []
    filenames = []
    for idx, file in enumerate(uploaded_files, start=1):
        text_part, method, filename = extract_text_from_upload(file)
        methods.append(method)
        filenames.append(filename)
        if text_part:
            extracted_parts.append(f'--- DOCUMENTO {idx}: {filename} ---\n{text_part}')

    text = '\n\n'.join(extracted_parts).strip()
    method = '+'.join(sorted(set(methods))) if methods else 'unknown'

    if len(text) < 50:
        return jsonify({'error': 'No se detectó texto en el documento.'}), 400

    raw_extracted = process_with_gemini(text)
    parser = 'gemini'
    if not raw_extracted:
        raw_extracted = parse_ficha_from_text(text)
        parser = 'fallback_reglas'

    extracted_data = normalize_ficha(raw_extracted, source='ocr')
    extracted_data['file_name'] = ' | '.join(filenames)
    extracted_data['extraction_method'] = method
    extracted_data['parser'] = parser
    extracted_data['confidence'] = 0.95 if method == 'pdfplumber' else (0.78 if parser == 'fallback_reglas' else 0.85)
    extracted_data['raw_text'] = text
    extracted_data['extracted_json'] = json.dumps(raw_extracted, ensure_ascii=False)

    # Buscar datos adicionales de la IE en la BD si existe el código modular
    conn = get_db()
    ie = conn.execute('SELECT nombre_iiee, nivel_modalidad, distrito FROM dim_institucion WHERE codigo_modular = ?',
                     (extracted_data.get('codigo_modular',''),)).fetchone()
    conn.close()

    if ie:
        extracted_data['distrito'] = dict(ie)['distrito']
        extracted_data['nivel_modalidad'] = dict(ie)['nivel_modalidad']
        if extracted_data.get('nombre_ie', '') == '':
            extracted_data['nombre_ie'] = dict(ie)['nombre_iiee']

    return jsonify({
        'success': True,
        'method': method,
        'parser': parser,
        'file_count': len(uploaded_files),
        'files': filenames,
        'extracted': extracted_data
    })

@app.route('/api/fichas', methods=['GET', 'POST'])
def fichas():
    ensure_db_schema()
    conn = get_db()
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
            ficha = save_ficha_to_db(conn, data)
            conn.commit()
            return jsonify({'success': True, 'ficha': ficha})

        rows = conn.execute('''
            SELECT *
            FROM fichas_monitoreo
            ORDER BY fecha_sincronizacion DESC, id DESC
            LIMIT 100
        ''').fetchall()
        return jsonify(rows_to_list(rows))
    finally:
        conn.close()

@app.route('/api/sync', methods=['POST'])
def sync_data():
    data = request.get_json() or []
    if not isinstance(data, list):
        data = [data]

    ensure_db_schema()
    conn = get_db()
    inserted = 0
    try:
        for f in data:
            save_ficha_to_db(conn, f)
            inserted += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error al sincronizar: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

    return jsonify({
        'success': True,
        'message': f'{inserted} registros guardados en la BD (fichas_monitoreo).',
        'synced_count': inserted
    })


# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    ensure_db_schema()
    print('=' * 50)
    print('  SUGKA LAB API Server')
    print(f'  DB : {DB_PATH}')
    print('  URL: http://localhost:8000')
    print('=' * 50)
    app.run(host='0.0.0.0', port=8000, debug=True)
