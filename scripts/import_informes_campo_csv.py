#!/usr/bin/env python3
"""Importa la tabla oficial `features_campo_por_visita_ie.csv` del subproyecto
de datos `informes_campo_v3` hacia la base de datos de la app SUGKA LAB.

Llena informe_campo_documento + informe_campo_visita + informe_campo_hallazgo
con fuente='historico_v3', y recalcula institucion_resumen/alertas.

Es ADITIVO: no borra fichas, visitas ni alertas existentes (usa INSERT OR
REPLACE solo sobre las filas que este mismo importador crea, identificadas
por su propio visita_campo_id). Se puede correr varias veces con el mismo
CSV sin duplicar datos.

Uso:
    python scripts/import_informes_campo_csv.py ruta/a/features_campo_por_visita_ie.csv
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import api_server as api

CAMPO_VARS = api.CAMPO_CONCRETE_VARIABLES


def import_csv(path):
    with api.app.app_context():
        conn = api.get_db()
        with open(path, encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        doc_by_archivo = {}
        inserted_docs = 0
        inserted_visitas = 0
        inserted_hallazgos = 0
        omitidas_sin_codigo = 0

        for row in rows:
            archivo_id = row.get('archivo_id', '')
            if archivo_id not in doc_by_archivo:
                cur = conn.execute('''
                    INSERT INTO informe_campo_documento (
                        nombre_archivo, ruta_relativa, hash_sha1, tipo_documento,
                        subtipo_documento, especialista_detectado, fecha_visita_inicio,
                        fecha_visita_fin, metodo_extraccion, requiere_ocr,
                        longitud_texto_documento, fuente
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'historico_v3')
                ''', (
                    row.get('nombre_archivo', ''), row.get('ruta_relativa', ''), row.get('hash_sha1', ''),
                    row.get('tipo_documento', ''), row.get('subtipo_documento', ''),
                    row.get('especialista_detectado', ''), row.get('fecha_visita_inicio', ''),
                    row.get('fecha_visita_fin', ''), row.get('metodo_extraccion', ''),
                    api.safe_int(row.get('requiere_ocr'), 0), api.safe_int(row.get('longitud_texto_documento'), 0),
                ))
                doc_by_archivo[archivo_id] = cur.lastrowid
                inserted_docs += 1
            documento_id = doc_by_archivo[archivo_id]

            codigo = api.resolve_codigo_modular_strict(conn, row.get('codigo_modular', ''))
            if not codigo:
                omitidas_sin_codigo += 1
                continue

            visita_id = row.get('visita_campo_id') or None
            if not visita_id:
                continue

            columns = [
                'visita_campo_id', 'documento_id', 'codigo_modular', 'nombre_ie_detectado',
                'nombre_ie_padron', 'nivel_padron', 'centro_poblado_padron', 'distrito_padron',
                'codlocal_padron', 'fecha_visita', 'anio_visita', 'mes_visita', 'especialista_detectado',
                'n_variables_observadas', 'variables_observadas', 'metodo_match_ie',
                'flag_match_dudoso', 'requiere_revision', 'motivo_revision', 'fuente',
            ]
            values = [
                visita_id, documento_id, codigo, row.get('nombre_ie_detectado', ''),
                row.get('nombre_ie_padron', ''), row.get('nivel_padron', ''),
                row.get('centro_poblado_padron', ''), row.get('distrito_padron', ''),
                row.get('codlocal_padron', ''), row.get('fecha_visita', ''),
                row.get('anio_visita', ''), row.get('mes_visita', ''),
                row.get('especialista_detectado', ''),
                api.safe_int(row.get('n_variables_observadas'), 0),
                row.get('variables_observadas', ''), row.get('metodo_match_ie', ''),
                api.safe_int(row.get('flag_match_dudoso'), 0),
                api.safe_int(row.get('requiere_revision'), 0),
                row.get('motivo_revision', ''), 'historico_v3',
            ]
            for var in CAMPO_VARS:
                raw = row.get(var, '')
                flag_value = 1 if str(raw).strip() == '1' else None
                columns.append(var)
                values.append(flag_value)
                columns.append(f'span_{var}')
                values.append(row.get(f'span_{var}') or None)

            placeholders = ', '.join('?' for _ in columns)
            conn.execute(
                f'INSERT OR REPLACE INTO informe_campo_visita ({", ".join(columns)}) VALUES ({placeholders})',
                values,
            )
            inserted_visitas += 1

            for var in CAMPO_VARS:
                raw = row.get(var, '')
                span = row.get(f'span_{var}') or ''
                if str(raw).strip() == '1' and span:
                    conn.execute('''
                        INSERT INTO informe_campo_hallazgo (
                            visita_campo_id, documento_id, codigo_modular_hallazgo,
                            variable_detectada, tema, descripcion, evidencia_textual
                        ) VALUES (?, ?, ?, ?, '', '', ?)
                    ''', (visita_id, documento_id, codigo, var, span))
                    inserted_hallazgos += 1

        api.rebuild_simon_operational_summary(conn)
        conn.commit()
        print(
            f'Documentos: {inserted_docs} | Visitas importadas: {inserted_visitas} | '
            f'Hallazgos: {inserted_hallazgos} | Omitidas sin codigo modular resoluble: {omitidas_sin_codigo}'
        )


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Uso: python import_informes_campo_csv.py ruta/al/features_campo_por_visita_ie.csv')
        sys.exit(1)
    import_csv(sys.argv[1])
