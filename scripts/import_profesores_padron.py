#!/usr/bin/env python3
"""Importa un directorio/padron de profesores y directores (.xlsx) hacia el core
`profesor`, vinculando cada persona con su IE en dim_institucion.

Es generico por nivel educativo: la columna "Nombre de IE" del padron trae en
realidad el numero local corto de la IE (ej. "205"), que en dim_institucion vive
en la columna nombre_iiee -- se resuelve con api.resolve_by_nombre_local, la
misma funcion que ya usan los informes de campo. En las filas donde esa columna
trae un nombre de lugar en vez de un numero, se resuelve por centro_poblado.

Nunca adivina: si una IE queda ambigua (varias candidatas) o no se encuentra,
las filas de esa IE no se importan y se reportan al final para revision manual.

Es idempotente: si el DNI ya existe, actualiza esa fila en vez de duplicarla.

Uso:
    python scripts/import_profesores_padron.py ruta/al/padron.xlsx --nivel-educativo Inicial
    python scripts/import_profesores_padron.py ruta/al/padron.xlsx --nivel-educativo Inicial --dry-run
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import api_server as api  # noqa: E402
import openpyxl  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402

# Mapeo de columnas del padron (0-indexed). Ajustable si un padron de otro nivel
# viene con otro orden de columnas.
COLUMN_MAP = {
    'codigo_ie': 1,       # "Nombre de IE" -> numero local corto de la IE
    'lugar': 2,           # centro poblado / localidad
    'distrito': 3,
    'nombre_persona': 4,  # "Director" -> apellidos y nombres
    'dni': 5,
    'celular': 6,
}
DATA_START_ROW = 6  # 1-indexed: fila 4 son titulos, fila 5 va vacia


def _normaliza(texto):
    return re.sub(r'[^A-Z0-9]', '', api._normalize_place_text(texto or ''))


def resolver_ie(conn, codigo_texto, lugar, nivel_educativo):
    """Resuelve la IE del padron contra dim_institucion.

    El identificador del padron (columna "Nombre de IE") es el numero local corto
    de la IE -- o su nombre, en las filas donde no hay numero -- y en ambos casos
    vive en dim_institucion.nombre_iiee.

    La ambiguedad tipica no es entre colegios distintos, sino entre los niveles
    del mismo colegio: "16358" existe como Primaria y como Inicial - Jardin en la
    misma localidad. Como el padron declara su nivel (--nivel-educativo), filtrar
    por nivel no es adivinar: es usar un dato que el propio archivo aporta.

    Si tras filtrar por nivel siguen quedando varias candidatas, se desempata por
    centro poblado tolerando variantes de escritura (NAYUMPIN/NAYUMPIM,
    KUSUIN/KUSUIM son la misma localidad awajun escrita distinto). Ese desempate
    solo elige entre candidatas que ya comparten el mismo codigo de IE: nunca
    inventa un match desde cero. Si aun asi queda mas de una, devuelve '' para
    que la fila se reporte y la revise una persona.
    """
    codigo_texto = (codigo_texto or '').strip()
    if not codigo_texto:
        return ''
    candidatas = conn.execute(
        'SELECT codigo_modular, nivel_modalidad, centro_poblado FROM dim_institucion '
        'WHERE UPPER(TRIM(nombre_iiee)) = UPPER(TRIM(?))',
        (codigo_texto,),
    ).fetchall()
    if not candidatas:
        return ''
    if len(candidatas) == 1:
        return candidatas[0]['codigo_modular']

    nivel = (nivel_educativo or '').strip().lower()
    if nivel:
        por_nivel = [
            row for row in candidatas
            if (row['nivel_modalidad'] or '').strip().lower().startswith(nivel)
        ]
        if len(por_nivel) == 1:
            return por_nivel[0]['codigo_modular']
        if por_nivel:
            candidatas = por_nivel

    lugar_norm = _normaliza(lugar)
    if lugar_norm:
        por_lugar = [
            row for row in candidatas
            if fuzz.ratio(lugar_norm, _normaliza(row['centro_poblado'])) >= 85
        ]
        if len(por_lugar) == 1:
            return por_lugar[0]['codigo_modular']

    return ''


def es_fila_de_director(nombre_raw):
    """En estos padrones el director de la IE va en MAYUSCULAS y los docentes de
    aula en Tipo Oracion. El numero de fila (columna N) no sirve para esto: en el
    archivo real hay IEs cuyo director aparece con N=2 y sus docentes con N=1,2,3."""
    nombre_raw = (nombre_raw or '').strip()
    if not nombre_raw or not any(c.isalpha() for c in nombre_raw):
        return False
    return nombre_raw == nombre_raw.upper()


def clasificar_celular(raw):
    """Devuelve (celular, condicion_laboral).

    En el padron real la columna de celular a veces trae "Contratada"/"Contratado"
    en vez de un numero. Ese dato es util (condicion laboral), pero no es un
    telefono: se guarda en su propia columna en vez de perderse o ensuciar celular.
    """
    raw = str(raw or '').strip()
    if not raw:
        return None, None
    digitos = re.sub(r'\D', '', raw)
    if len(digitos) >= 6 and re.fullmatch(r'[\d\s+()\-.]+', raw):
        return digitos, None
    return None, raw


def import_padron(xlsx_path, nivel_educativo, fuente=None, dry_run=False):
    fuente = fuente or f'padron_{nivel_educativo.strip().lower().replace(" ", "_")}'
    stats = {
        'filas_leidas': 0,
        'sin_nombre': 0,
        'creados': 0,
        'actualizados': 0,
        'sin_dni': 0,
        'celular_reclasificado': 0,
        'filas_sin_ie': 0,
        'ies_resueltas': set(),
        'ies_sin_resolver': {},
    }

    with api.app.app_context():
        conn = api.get_db()
        workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
        sheet = workbook.active
        cache_ie = {}

        for row in sheet.iter_rows(min_row=DATA_START_ROW, values_only=True):
            if not row or len(row) <= COLUMN_MAP['nombre_persona']:
                continue
            nombre_raw = str(row[COLUMN_MAP['nombre_persona']] or '').strip()
            codigo_texto = str(row[COLUMN_MAP['codigo_ie']] or '').strip()
            lugar = str(row[COLUMN_MAP['lugar']] or '').strip()
            if not nombre_raw:
                if codigo_texto or lugar:
                    stats['sin_nombre'] += 1
                continue
            stats['filas_leidas'] += 1

            clave = (codigo_texto, lugar)
            if clave not in cache_ie:
                cache_ie[clave] = resolver_ie(conn, codigo_texto, lugar, nivel_educativo)
            codigo_modular = cache_ie[clave]

            if not codigo_modular:
                stats['filas_sin_ie'] += 1
                stats['ies_sin_resolver'].setdefault(clave, 0)
                stats['ies_sin_resolver'][clave] += 1
                continue
            stats['ies_resueltas'].add(codigo_modular)

            dni = re.sub(r'\D', '', str(row[COLUMN_MAP['dni']] or '')) or None
            if not dni:
                stats['sin_dni'] += 1
            celular, condicion = clasificar_celular(row[COLUMN_MAP['celular']])
            if condicion:
                stats['celular_reclasificado'] += 1
            cargo = 'director' if es_fila_de_director(nombre_raw) else 'docente'

            # El DNI es la identidad real, pero hay filas del padron que no lo
            # traen; para esas se deduplica por nombre + IE, si no cada corrida
            # del import volveria a crearlas.
            if dni:
                existente = conn.execute('SELECT id FROM profesor WHERE dni = ?', (dni,)).fetchone()
            else:
                existente = conn.execute(
                    'SELECT id FROM profesor WHERE dni IS NULL '
                    'AND UPPER(TRIM(nombre_completo)) = UPPER(TRIM(?)) AND codigo_modular_ie = ?',
                    (nombre_raw, codigo_modular),
                ).fetchone()

            if dry_run:
                if existente:
                    stats['actualizados'] += 1
                else:
                    stats['creados'] += 1
                continue

            if existente:
                conn.execute(
                    '''
                    UPDATE profesor
                    SET nombre_completo = ?, celular = COALESCE(?, celular), cargo = ?,
                        condicion_laboral = COALESCE(?, condicion_laboral),
                        codigo_modular_ie = ?, fuente = ?, estado_fila = 1,
                        actualizado_en = CURRENT_TIMESTAMP
                    WHERE id = ?
                    ''',
                    (nombre_raw, celular, cargo, condicion, codigo_modular, fuente, existente['id']),
                )
                stats['actualizados'] += 1
            else:
                conn.execute(
                    '''
                    INSERT INTO profesor (
                        dni, nombre_completo, celular, cargo, condicion_laboral,
                        codigo_modular_ie, fuente
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (dni, nombre_raw, celular, cargo, condicion, codigo_modular, fuente),
                )
                stats['creados'] += 1

        if not dry_run:
            conn.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description='Importa un padron de profesores/directores al core.')
    parser.add_argument('xlsx_path', help='Ruta al archivo .xlsx del padron')
    parser.add_argument('--nivel-educativo', required=True, help='Inicial, Primaria, Secundaria, ...')
    parser.add_argument('--fuente', help='Etiqueta de procedencia (por defecto: padron_<nivel>)')
    parser.add_argument('--dry-run', action='store_true', help='Simula sin escribir en la base')
    args = parser.parse_args()

    stats = import_padron(args.xlsx_path, args.nivel_educativo, args.fuente, args.dry_run)

    modo = ' (DRY RUN, no se escribio nada)' if args.dry_run else ''
    print(f'Padron procesado{modo}')
    print(f'  Filas de persona leidas : {stats["filas_leidas"]}')
    print(f'  Profesores creados      : {stats["creados"]}')
    print(f'  Profesores actualizados : {stats["actualizados"]}')
    print(f'  IEs distintas resueltas : {len(stats["ies_resueltas"])}')
    print(f'  Filas sin DNI           : {stats["sin_dni"]}')
    print(f'  Celular reclasificado a condicion_laboral: {stats["celular_reclasificado"]}')
    print(f'  Filas omitidas sin nombre: {stats["sin_nombre"]}')
    print(f'  Filas NO importadas por IE sin resolver: {stats["filas_sin_ie"]}')
    if stats['ies_sin_resolver']:
        print('  IEs sin resolver (revisar manualmente):')
        for (codigo_texto, lugar), cuantas in sorted(stats['ies_sin_resolver'].items()):
            print(f'    - codigo="{codigo_texto}" lugar="{lugar}" ({cuantas} fila(s))')


if __name__ == '__main__':
    main()
