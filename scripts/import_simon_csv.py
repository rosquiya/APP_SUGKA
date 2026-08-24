#!/usr/bin/env python3
"""Importa fichas SIMON extraidas en CSV hacia la base SUGKA."""
import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'app'))

from api_server import (  # noqa: E402
    canonical_codigo_modular,
    ensure_db_schema,
    get_db,
    rebuild_simon_operational_summary,
    safe_int,
    save_ficha_to_db,
)

SIMON_MONITOR_DEFAULT = 'María Eugenia Aldava Asencios'
SIMON_ITEMS = (
    ('A-01', 'a1', 'preparacion_aprendizaje'),
    ('A-02', 'a2', 'preparacion_aprendizaje'),
    ('A-03', 'a3', 'preparacion_aprendizaje'),
    ('B-01', 'b1', 'ensenanza_aprendizaje'),
    ('B-02', 'b2', 'ensenanza_aprendizaje'),
    ('B-03', 'b3', 'ensenanza_aprendizaje'),
    ('B-04', 'b4', 'ensenanza_aprendizaje'),
    ('B-05', 'b5', 'ensenanza_aprendizaje'),
)


def clean_text(value):
    return str(value or '').strip()


def parse_date(value):
    value = clean_text(value)
    if not value:
        return ''
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(value, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return value


def row_to_ficha(conn, row, monitor_name):
    code = canonical_codigo_modular(conn, row.get('codigo_modular'))
    levels = {
        field: safe_int(row.get(f'{code_name}_score'), 0)
        for code_name, field, _section in SIMON_ITEMS
    }
    valid_levels = [level for level in levels.values() if level > 0]
    promedio = round(sum(valid_levels) / len(valid_levels), 2) if valid_levels else 0.0
    compromisos = '\n'.join(
        text for text in (
            clean_text(row.get('compromiso_monitoreado_1')),
            clean_text(row.get('compromiso_monitoreado_2')),
        )
        if text
    )

    respuestas = []
    for code_name, field, section in SIMON_ITEMS:
        respuestas.append({
            'pregunta_codigo': code_name,
            'seccion_clave': section,
            'nivel': levels[field],
            'respuesta_texto': clean_text(row.get(f'{code_name}_nivel')),
            'observacion': clean_text(row.get(f'{code_name}_observaciones')),
        })

    ficha = {
        'source': 'simon_csv',
        'file_name': clean_text(row.get('archivo_fuente')),
        'extraction_method': 'csv_import',
        'confidence': 1.0,
        'region': clean_text(row.get('region')) or 'Amazonas',
        'ugel': clean_text(row.get('ugel')) or 'UGEL IBIR-IMAZA',
        'n_visita': clean_text(row.get('n_visita')) or '1',
        'codigo_modular': code,
        'nombre_ie': clean_text(row.get('nombre_iiee_catalogo')) or clean_text(row.get('ie')),
        'nivel_modalidad': clean_text(row.get('nivel_modalidad')),
        'director': clean_text(row.get('director')),
        'director_cel': clean_text(row.get('director_cel')),
        'director_email': clean_text(row.get('director_email')),
        'director_situacion_laboral': clean_text(row.get('situacion_laboral_director')),
        'docente': clean_text(row.get('docente_nombre')),
        'docente_dni': clean_text(row.get('docente_dni')),
        'docente_cel': clean_text(row.get('docente_cel')),
        'docente_email': clean_text(row.get('docente_email')),
        'docente_situacion_laboral': clean_text(row.get('situacion_laboral_docente')),
        'grado': clean_text(row.get('grado')),
        'seccion': clean_text(row.get('seccion')),
        'nro_estudiantes': safe_int(row.get('n_estudiantes'), 0),
        'area': clean_text(row.get('area')),
        'competencia': clean_text(row.get('competencia')),
        'titulo_sesion': clean_text(row.get('titulo_sesion')),
        'monitor': monitor_name,
        'monitor_dni': clean_text(row.get('monitor_dni')),
        'iged': clean_text(row.get('iged')) or 'UGEL IBIR-IMAZA',
        'monitor_email': clean_text(row.get('monitor_email')),
        'fecha_ejecucion': parse_date(row.get('fecha')),
        'promedio': promedio,
        'observaciones': clean_text(row.get('observaciones_recomendaciones')),
        'observaciones_recomendaciones': clean_text(row.get('observaciones_recomendaciones')),
        'compromisos': compromisos,
        'compromisos_monitoreado': compromisos,
        'instrumentos': [{
            'codigo': 'simon_docente_2026',
            'tipo': 'fija',
            'formulario': clean_text(row.get('instrumento')) or 'Ficha SIMON docente 2026',
            'respuestas': respuestas,
            'campos_finales': {
                'observaciones_recomendaciones': clean_text(row.get('observaciones_recomendaciones')),
                'compromiso_monitoreado_1': clean_text(row.get('compromiso_monitoreado_1')),
                'compromiso_monitoreado_2': clean_text(row.get('compromiso_monitoreado_2')),
            },
        }],
    }
    for _code_name, field, _section in SIMON_ITEMS:
        ficha[field] = levels[field]
        ficha[f'{field}_observacion'] = clean_text(row.get(f'{_code_name}_observaciones'))
    return ficha


def import_csv(path, monitor_name=SIMON_MONITOR_DEFAULT, clear=True):
    ensure_db_schema()
    conn = get_db()
    inserted = 0
    try:
        if clear:
            conn.execute('DELETE FROM ficha_campo_instrumento')
            conn.execute('DELETE FROM ficha_respuesta_instrumento')
            conn.execute('DELETE FROM fichas_monitoreo')
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('fichas_monitoreo','ficha_respuesta_instrumento','ficha_campo_instrumento')")

        with Path(path).open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                save_ficha_to_db(conn, row_to_ficha(conn, row, monitor_name))
                inserted += 1

        rebuild_simon_operational_summary(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return inserted


def main():
    parser = argparse.ArgumentParser(description='Importa fichas SIMON desde CSV.')
    parser.add_argument('csv_path', help='Ruta del CSV extraido de SIMON.')
    parser.add_argument('--monitor', default=SIMON_MONITOR_DEFAULT, help='Nombre del monitor para todos los registros.')
    parser.add_argument('--append', action='store_true', help='No limpia fichas existentes antes de importar.')
    args = parser.parse_args()
    inserted = import_csv(args.csv_path, monitor_name=args.monitor, clear=not args.append)
    print(f'Importadas {inserted} fichas SIMON.')


if __name__ == '__main__':
    main()
