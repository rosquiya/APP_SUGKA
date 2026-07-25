#!/usr/bin/env python3
"""Importa el cruce censal 2025 de infraestructura hacia la base SUGKA."""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

from api_server import (  # noqa: E402
    canonical_codigo_modular,
    ensure_db_schema,
    get_db,
    rebuild_simon_operational_summary,
    safe_float,
    safe_int,
)


def clean_text(value):
    return str(value or '').strip()


def import_csv(path, clear=True):
    ensure_db_schema()
    conn = get_db()
    inserted = 0
    try:
        if clear:
            conn.execute('DELETE FROM infraestructura_censo_2025')

        with Path(path).open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                original_code = clean_text(row.get('codigo_modular'))
                code = canonical_codigo_modular(conn, original_code)
                if not code:
                    continue
                conn.execute('''
                    INSERT OR REPLACE INTO infraestructura_censo_2025 (
                        codigo_modular, codigo_modular_original, codigo_local,
                        nombre_iiee, nivel_modalidad, distrito, centro_poblado,
                        alumnos_censo, edificaciones, edificaciones_en_uso,
                        edificaciones_riesgo, aulas, aulas_en_uso,
                        alumnos_por_aula_en_uso, alertas_infraestructura_campo,
                        risk_score_infra, risk_flags, fuente, actualizado_en
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'censo_educativo_2025', CURRENT_TIMESTAMP)
                ''', (
                    code,
                    original_code,
                    clean_text(row.get('codigo_local')),
                    clean_text(row.get('nombre_iiee')),
                    clean_text(row.get('nivel_modalidad')),
                    clean_text(row.get('distrito')),
                    clean_text(row.get('centro_poblado')),
                    safe_int(row.get('alumnos_censo'), 0),
                    safe_int(row.get('edificaciones'), 0),
                    safe_int(row.get('edificaciones_en_uso'), 0),
                    safe_int(row.get('edificaciones_riesgo'), 0),
                    safe_int(row.get('aulas'), 0),
                    safe_int(row.get('aulas_en_uso'), 0),
                    safe_float(row.get('alumnos_por_aula_en_uso'), None),
                    safe_int(row.get('alertas_infraestructura_campo'), 0),
                    safe_float(row.get('risk_score_infra'), 0.0),
                    clean_text(row.get('risk_flags')),
                ))
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
    parser = argparse.ArgumentParser(description='Importa infraestructura censal 2025 desde CSV.')
    parser.add_argument('csv_path', help='Ruta del CSV app_sugka_iiee_cruce_edific_aulas_resumen.csv.')
    parser.add_argument('--append', action='store_true', help='No limpia infraestructura existente antes de importar.')
    args = parser.parse_args()
    inserted = import_csv(args.csv_path, clear=not args.append)
    print(f'Importadas {inserted} filas de infraestructura censal 2025.')


if __name__ == '__main__':
    main()
