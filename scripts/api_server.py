#!/usr/bin/env python3
"""
SUGKA LAB – API Server
REST API Flask para la aplicacion de gestion educativa UGEL IBIR-IMAZA.
Puerto: 8000
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Rutas relativas al directorio raíz del proyecto
ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / 'data' / 'database' / 'sugka_demo.db'

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def rows_to_list(rows):
    return [dict(r) for r in rows]

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
        SELECT i.nombre_iiee, i.distrito, r.priority_score, r.coverage_category,
               r.total_alertas_campo
        FROM institucion_resumen r
        JOIN dim_institucion i ON r.codigo_modular = i.codigo_modular
        ORDER BY r.priority_score DESC LIMIT 8
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
    })

# ─── OCR ──────────────────────────────────────────────────────────────────────

@app.route('/api/ocr/upload', methods=['POST'])
def ocr_upload():
    conn = get_db()
    ie      = conn.execute('SELECT codigo_modular,nombre_iiee,nivel_modalidad,distrito FROM dim_institucion ORDER BY RANDOM() LIMIT 1').fetchone()
    monitor = conn.execute('SELECT nombre FROM dim_especialista ORDER BY RANDOM() LIMIT 1').fetchone()
    conn.close()

    today     = datetime.now()
    days_ago  = random.randint(4, 25)
    fecha_ex  = today  - timedelta(days=days_ago)
    fecha_pr  = fecha_ex - timedelta(days=random.randint(1,6))

    niv   = {1: random.randint(0,3), 2: random.randint(1,5), 3: random.randint(0,3), 4: random.randint(0,2)}
    total = sum(niv.values()) or 1
    prom  = round(sum(k*v for k,v in niv.items()) / total, 2)

    nombres = ['PEDRO','MARIA','JUAN','ANA','CARLOS','ROSA','EDGAR','LUZ']
    apelis  = ['QUISPE','LOPEZ','GARCIA','HUANCA','FLORES','DIAZ','CHAVEZ','MAMANI']

    return jsonify({
        'success': True,
        'method':  'simulated',
        'extracted': {
            'codigo_modular':    dict(ie)['codigo_modular']  if ie else '',
            'nombre_ie':         dict(ie)['nombre_iiee']     if ie else 'No detectado',
            'nivel_modalidad':   dict(ie)['nivel_modalidad'] if ie else '',
            'distrito':          dict(ie)['distrito']        if ie else '',
            'docente':           f'{random.choice(nombres)} {random.choice(apelis)}',
            'monitor':           dict(monitor)['nombre']     if monitor else 'No detectado',
            'fecha_programacion': fecha_pr.strftime('%Y-%m-%d'),
            'fecha_ejecucion':    fecha_ex.strftime('%Y-%m-%d'),
            'plan':              random.choice(['PELA','Acomp. Pedagógico','PREVAED']),
            'instrumento':       'Rúbrica de observación de aula',
            'visita':            str(random.randint(1,3)),
            'nivel_i':   str(niv[1]),
            'nivel_ii':  str(niv[2]),
            'nivel_iii': str(niv[3]),
            'nivel_iv':  str(niv[4]),
            'promedio_nivel': str(prom),
            'confidence': round(random.uniform(0.73, 0.96), 2),
        }
    })

@app.route('/api/fichas', methods=['POST'])
def save_ficha():
    return jsonify({
        'success':  True,
        'message':  'Ficha guardada exitosamente (modo demo)',
        'ficha_id': f'demo_{datetime.now().strftime("%Y%m%d%H%M%S")}'
    })

# ─── MAIN ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=' * 50)
    print('  SUGKA LAB API Server')
    print(f'  DB : {DB_PATH}')
    print('  URL: http://localhost:8000')
    print('=' * 50)
    app.run(host='0.0.0.0', port=8000, debug=True)
