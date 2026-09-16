#!/usr/bin/env python3
"""Aplica en produccion la validacion de hallazgos hecha por el especialista.

Se corre en el shell de Render. Es idempotente: repetirlo no cambia nada mas.
No pasa por el repositorio porque la semilla versionada no puede llevar datos
personales del padron.

Empareja cada tarjeta validada por (codigo de IE de la visita, variable,
nombre de archivo). El nombre se compara normalizado y tratando el caracter
corrupto U+FFFD como comodin, porque la base guarda las tildes danadas.
"""
import re, sqlite3, sys, unicodedata

RUTA = '/var/data/sugka_demo.db'
FUENTE = 'Validacion de especialistas - muestra Cochran 84 casos (2026-09)'

DESCARTADOS = [
    ('0269993', 'presenta_violencia', 'INFORME DE ASITENCIA TECNICA- SEMANA 2 DE MAYO.pdf', 'se refiere a sobre lo que se capacito, no de un caso'),
    ('0918136', 'presenta_violencia', 'INFORME SALIDA A VALENTIN SALEGUI EL 13 DE JUNIO- PAMELA QUISPE.pdf', 'Se refiere al tema, no a un caso. Se podria agregar para diferenciar "capacitacion sobre violencia" o algo parecido'),
    ('1412261', 'presenta_violencia', 'INFORME 2 - MONITOREO SEMANA 2 DE MAYO- ROCIO SILVA.pdf', 'se habla del tema de capacitacion, en todo caso que desconocian el tema'),
    ('1661883', 'presenta_violencia', 'INOFORME DE SALIDA DEL 20 AL 23 DE JULIO- PAMELA QUISPE.pdf', 'hace referencia a recomendaciones'),
    ('1718790', 'presenta_violencia', 'INOFORME DE SALIDA DEL 20 AL 23 DE JULIO- PAMELA QUISPE.pdf', 'son recomendaciones'),
    ('0918136', 'ausencia_docente', 'INFORME DE LA PRIMERA SEMANA ED GESTION MAYO- GERSON ASANGKAY.pdf', 'no se logra comprender el sentido del parrafo'),
    ('0554345', 'falta_materiales', 'INFORME BIAE FASE III- MARILU MONTENEGRO.pdf', 'ambiguo, dice que se entrego y luego que no llegaron'),
    ('0623660', 'falta_materiales', 'INFORME BIAE FASE III- ELEONORA NUNCANQUIT.pdf', 'no indica nada al respecto'),
    ('0768614', 'falta_materiales', 'INFORMA SALIDA BIAE FASE II- SAMUEL BECERRA.pdf', 'solo es correcta la ultima parte que refiere sobre los cuadernos de trabajo'),
    ('0918136', 'falta_materiales', 'INFORMA SALIDA A BAGUA 30 DE JUNIO- PROEIB.pdf', 'son recomendaciones'),
    ('1432004', 'falta_materiales', 'INFORME BIAE FASE III- MARILU MONTENEGRO.pdf', 'no hay coherencia en el parrafo, no se puede afirmar que da la alerta'),
    ('3022779', 'falta_materiales', 'INFORMA VISITA A 18858- GUIRALDES TOCAS.pdf', 'es recomendacion, no alerta'),
    ('0223453', 'infraestructura_deficiente', 'SALIDA BIAE FASE III- JOSE HUGO.pdf', 'no indica alerta'),
    ('0270041', 'infraestructura_deficiente', 'MONITOREO 27 Y 28 DE FEBRERO.pdf', 'no indica alerta, al contrario'),
    ('0270272', 'infraestructura_deficiente', 'INFORMA SALIDA BIAE FASE III- SAMUEL BECERRA.pdf', 'seria correcto si indica "mal estado", porque si menciona SSHH, pero es buen estado'),
    ('0401851', 'infraestructura_deficiente', 'INFORME BIAE FASE III- MARILU MONTENEGRO.pdf', 'seria correcto si indica "no tiene plan de gestion de riesgo"'),
    ('0402289', 'infraestructura_deficiente', 'INFORMA SALIDA BIAE FASE III- SAMUEL BECERRA.pdf', 'no indica alerta, al contrario'),
    ('0745125', 'infraestructura_deficiente', 'INFORME DE ACTIVIDADES PROGRAMADAS DE OCEIB CHIPE- MAYO 27-30.pdf', 'parece una recomendacion'),
    ('0768614', 'infraestructura_deficiente', 'INFORMA SALIDA BIAE FASE II- SAMUEL BECERRA.pdf', 'se recomienda, pero no indica que es porque estan en mal estado'),
    ('1307537', 'infraestructura_deficiente', 'INFORME BIAE FASE III- ELEONORA NUNCANQUIT.pdf', 'no se detalla la alerta identificada'),
    ('1346279', 'infraestructura_deficiente', 'INFORME BIAE FASE II- ANA ANTUASH.pdf', 'no menciona nada del criterio'),
    ('1412261', 'infraestructura_deficiente', 'Informe Monitoreo BIAE FASE 3 2025- OTONAR.pdf', 'se corto la parte final donde parece indicar con que no cuenta'),
    ('1412311', 'infraestructura_deficiente', 'Informe Monitoreo BIAE FASE 3 2025- OTONAR.pdf', 'no se logra comprender el sentido del fragmento'),
    ('0259093', 'riesgo_salud_seguridad', 'Informe Monitoreo BIAE FASE 3 2025- OTONAR.pdf', 'se podria poner la palabra y un adjetivo, como: botiquin incompleto o botiquin en mal estado'),
    ('0402289', 'riesgo_salud_seguridad', 'INFORMA SALIDA BIAE FASE 1.pdf', 'lo ultimo creo que podria mas bien ir en la seccion anterior donde se indicaba ausencia de docente y/o director'),
    ('0402719', 'riesgo_salud_seguridad', 'INFORME BIAE FASE II-ISABEL ELERA.pdf', 'no identifico alerta'),
    ('0491852', 'riesgo_salud_seguridad', 'INFRME SALIDA BIAE FASE III- JENNY SANCHIUM.pdf', 'no da contexto de ser alerta o recomendacion'),
    ('0623660', 'riesgo_salud_seguridad', 'INFORME BIAE FASE III- ELEONORA NUNCANQUIT.pdf', 'no se precisa si es alerta o esta bien'),
    ('0768614', 'riesgo_salud_seguridad', 'INFORMA SALIDA BIAE FASE III- SAMUEL BECERRA.pdf', 'no indica alerta'),
    ('0918102', 'riesgo_salud_seguridad', 'INFORMA SALIDA BIAE FASE II- SAMUEL BECERRA.pdf', 'son recomendaciones'),
    ('0918102', 'riesgo_salud_seguridad', 'INFORMA SALIDA BIAE FASE III- SAMUEL BECERRA.pdf', 'no indica alerta'),
    ('1412261', 'riesgo_salud_seguridad', 'Informe Monitoreo BIAE FASE 3 2025- OTONAR.pdf', 'no se completa la parte que dice "no cuenta con..."'),
    ('1412261', 'riesgo_salud_seguridad', 'INFORME 2 - MONITOREO SEMANA 2 DE MAYO- ROCIO SILVA.pdf', 'son recomendaciones'),
    ('1788520', 'riesgo_salud_seguridad', 'INFORME BIAE FASE I-ISABEL ELERA.pdf', 'son recomendaciones no alertas'),
    ('0918136', 'inasistencia_estudiantes', 'SALIDA A CHACHAPOYAS 10 DE ABRIL- MARITZA CHAVEZ.pdf', 'no se indica si es alerta o a que se refiere con exactitud'),
    ('0259093', 'gestion_directiva_debil', 'SALIDA DEL 09 AL 14 DE AGOSTO- MONITOREO A CGB- PAMELA QUISPE.pdf', 'no se comprende'),
    ('0270272', 'gestion_directiva_debil', 'INFORMA SALIDA BIAE FASE II- SAMUEL BECERRA.pdf', 'no se indica la referencia al criterio'),
    ('0402297', 'gestion_directiva_debil', 'SALIDA DEL 09 AL 14 DE AGOSTO- MONITOREO A CGB- PAMELA QUISPE.pdf', 'no se precisa al respecto del criterio'),
    ('0402610', 'gestion_directiva_debil', 'INFORME SE SALIDA 2 AL 5 DE JUNIO- PAMELA QUISPE SANDOVAL.pdf', 'no detalla la alerta'),
    ('0623405', 'gestion_directiva_debil', 'INFORME DE SALIDA DEL IV BLOQUE SEMANA DE GESTION- HOMERO ZUNIGA.pdf', 'no se identifica la alerta'),
    ('0768614', 'gestion_directiva_debil', 'INFORMA SALIDA BIAE FASE II- SAMUEL BECERRA.pdf', 'puede ser para infraestructura, por la primera parte'),
    ('0918136', 'gestion_directiva_debil', 'INFORME DE SALIDA A CHIRIACO II REUNION SAR 20 JUNIO- PAMELA QUISPE.pdf', 'no se identifica la alerta'),
    ('0918136', 'gestion_directiva_debil', 'INFORME BIAE FASE II- ANA ANTUASH.pdf', 'no se identifica la alerta, se corto la parte que parece que lo indicaria'),
    ('0918136', 'gestion_directiva_debil', 'INOFORME DE SALIDA DEL 20 AL 23 DE JULIO- PAMELA QUISPE.pdf', 'no se identifica alerta'),
    ('0623405', 'retroalimentacion_debil', 'INFORME DEL 22 AL 26 DE SEPT. Y DEL 06 AL 09 DE OCT. OTONAR.pdf', 'no se menciona el "no"'),
    ('0918102', 'retroalimentacion_debil', 'INFORME DEL 22 AL 26 DE SEPT. Y DEL 06 AL 09 DE OCT. OTONAR.pdf', 'no se menciona el "no"'),
    ('1633833', 'retroalimentacion_debil', 'INFORME DE MONITOREO DEL 16 DE JUNIO AL 11 DE JULIO- OTONAR HURTADO.pdf', 'no se menciona el "no descriptiva", sino lo contrario'),
    ('0918136', 'acceso_dificil', 'INFORMO SALIDA A BAGUA SOBRE CETPRO- 22 Y 23 DE ABRIL- SAMUEL BECERRA.pdf', 'no se hace referencia al criterio'),
    ('0918136', 'acceso_dificil', 'INFORME SALIDA A BAGUA DEL 05 AL 08 DE MAYO- JANNY PPATI.pdf', 'no se hace referencia al criterio'),
    ('0918136', 'acceso_dificil', 'INFORME DE TALLER EN NIEVA JUNIO- MERCIDA YAGKUG.pdf', 'no hace referencia al criterio'),
    ('0918136', 'acceso_dificil', 'INFORMA TALLAER EN NIEVA DEL 2-6 DE JUNIO- GUIRALDES TOCAS.pdf', 'no hace referencia al criterio'),
    ('3022779', 'acceso_dificil', 'INFORMA VISITA A 18858- GUIRALDES TOCAS.pdf', 'no hace referencia al criterio'),
    ('3877632', 'acceso_dificil', 'INFORME DE SALIDA DE CONVIVENCIA SOBRE ELABORACION DE NORMAS DE CONV.- PAMELA.pdf', 'no hace referencia al criterio'),
    ('3877632', 'acceso_dificil', 'INFORME DE SALIDA DE CONVIVENCIA SOBRE ELABORACION DE NORMAS DE CONV..pdf', 'no hace referencia al criterio'),
    ('1464908', 'alimentacion_qaliwarma_problema', 'INFORME DE SALIDA DEL 19 AL 22 DE AGOTO- MENTE SHUSHI.pdf', 'se lee como terminos libres, no se deja identificar alerta con respecto al criterio'),
    ('1661883', 'alimentacion_qaliwarma_problema', 'INFORME SALIDA DEL 22 AL 26 DE SEP- ANA ANTUASH.pdf', 'se lee como terminos libres, no se deja identificar alerta con respecto al criterio'),
]

CONFIRMADOS = [
    ('0554345', 'presenta_violencia', 'INFORME DE VISITA A LA IE 16587- KUSU GRANDE- 11 DE AGOSTO- GUIRALDES TOCAS.pdf', 'confirmado por el especialista'),
    ('0745075', 'presenta_violencia', 'INFORME DE SALIDA 25 DE AGOSTO JHONATAN VILLANUEVA.pdf', 'confirmado por el especialista'),
    ('0918136', 'presenta_violencia', 'INFORME DE VISITA A LA IE VALENTIN SALEGUI 23 DE JUNIO.pdf', 'confirmado por el especialista'),
    ('1432004', 'presenta_violencia', 'INFORME D SALIDA 30 DE OCT- CHIPE - JANNY PAATI.pdf', 'confirmado por el especialista'),
    ('1432004', 'presenta_violencia', 'INFORME D SALIDA 28 DE OCT- CHIPE - JANNY PAATI.pdf', 'confirmado por el especialista'),
    ('0402289', 'falta_materiales', 'INFORMA SALIDA BIAE FASE III- SAMUEL BECERRA.pdf', 'confirmado por el especialista'),
    ('1432004', 'falta_materiales', 'INFORME BIAE FASE II- MARILU MONTENEGRO.pdf', 'confirmado por el especialista'),
    ('1696913', 'falta_materiales', 'SALIDA BIAE FASE III- MARITZA CHAVEZ.pdf', 'confirmado por el especialista'),
    ('3005477', 'falta_materiales', 'SALIDA BIAE FASE III- MARITZA CHAVEZ.pdf', 'confirmado por el especialista'),
    ('3965292', 'falta_materiales', 'INFORMA SALIDA BIAE FASE III- SAMUEL BECERRA.pdf', 'confirmado por el especialista'),
    ('0918136', 'infraestructura_deficiente', 'INFORME DE EVALUACION DIAGNOSTICA 7 Y 8 DE MAYO- MARIA CHUMAP.pdf', 'confirmado por el especialista'),
    ('1373034', 'infraestructura_deficiente', 'INFORME DE RESULTADOS BIAE FASE II- GERSON ASANGKAY.pdf', 'confirmado por el especialista'),
    ('0270272', 'riesgo_salud_seguridad', 'INFORMA SALIDA BIAE FASE III- SAMUEL BECERRA.pdf', 'correcto para el aspecto final, de lo demas se indica que esta bien'),
    ('0554345', 'riesgo_salud_seguridad', 'INFORME BIAE FASE III- MARILU MONTENEGRO.pdf', 'confirmado por el especialista'),
    ('0658401', 'riesgo_salud_seguridad', 'INFRME SALIDA BIAE FASE III- JENNY SANCHIUM.pdf', 'correcto por la parte que indica que no tiene mamparas'),
    ('1432004', 'riesgo_salud_seguridad', 'INFORME BIAE FASE III- MARILU MONTENEGRO.pdf', 'confirmado por el especialista'),
    ('1646215', 'riesgo_salud_seguridad', 'Informe Monitoreo BIAE FASE 3 2025- OTONAR.pdf', 'correcto; incorporar "senaletica" como palabra del criterio'),
    ('1692461', 'inasistencia_estudiantes', 'INFORME DE SALIDA DE 13 AL 28 DE AGOSTO- JOCABETH KAKIAS.pdf', 'confirmado por el especialista'),
    ('3877632', 'inasistencia_estudiantes', 'INFORME SALIDA 25 AL 30 DE MAYO- JOCABETH.pdf', 'confirmado por el especialista'),
    ('0401851', 'eib_no_practicado', 'INFORME BIAE FASE III- MARILU MONTENEGRO.pdf', 'confirmado por el especialista'),
    ('0918136', 'eib_no_practicado', 'INFORME DE MONITOREO DEL 15 AL 20 DE JUNIO.pdf', 'confirmado por el especialista'),
    ('1432004', 'eib_no_practicado', 'INFORME BIAE FASE III- MARILU MONTENEGRO.pdf', 'confirmado por el especialista'),
    ('1661883', 'eib_no_practicado', 'INFORME SALIDA DEL 22 AL 26 DE SEP- ANA ANTUASH.pdf', 'confirmado por el especialista'),
    ('3965956', 'eib_no_practicado', 'INFORME DE SALIDA DEL 17 AL 22 DE AGOSTO- JANNY PAATI.pdf', 'confirmado por el especialista'),
    ('0918136', 'gestion_directiva_debil', 'INFORME DE SALIDA A YAMAKENTSA 23 JUNIO- PAMELA QUISPE.pdf', 'confirmado por el especialista'),
    ('3022431', 'gestion_directiva_debil', 'INFORMA VISITA A 18859- SACHAM ENTSA- DAVID ESAMAT.pdf', 'confirmado por el especialista'),
    ('3022431', 'retroalimentacion_debil', 'INFORMA VISITA A 18859- SACHAM ENTSA- DAVID ESAMAT.pdf', 'confirmado por el especialista'),
    ('3022779', 'retroalimentacion_debil', 'INFORMA VISITA A 18858- GUIRALDES TOCAS.pdf', 'confirmado por el especialista'),
]


def norm(texto, comodin=False):
    t = unicodedata.normalize('NFKD', texto or '')
    t = ''.join(ch for ch in t if not unicodedata.combining(ch))
    t = t.replace('\ufffd', '\x00' if comodin else '')
    t = re.sub(r'[^A-Za-z0-9\x00]+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip().upper()


def coincide(bd, pdf):
    if '\x00' not in bd:
        return bd == pdf
    patron = '^' + ''.join('.' if c == '\x00' else re.escape(c) for c in bd) + '$'
    return re.match(patron, pdf) is not None


conn = sqlite3.connect(RUTA)
conn.row_factory = sqlite3.Row
print('Base: ' + RUTA)

# --- columnas de validacion (por si el deploy aun no migro el esquema) ---
cols = {f[1] for f in conn.execute('PRAGMA table_info(informe_campo_hallazgo)')}
for col, tipo in (('validacion_estado', "TEXT DEFAULT 'sin_validar'"),
                  ('validacion_comentario', 'TEXT'), ('validacion_por', 'TEXT'),
                  ('validacion_en', 'DATETIME'), ('validacion_fuente', 'TEXT')):
    if col not in cols:
        conn.execute('ALTER TABLE informe_campo_hallazgo ADD COLUMN %s %s' % (col, tipo))
        print('  columna agregada: ' + col)

filas = conn.execute('''
    SELECT h.id, v.codigo_modular cm, h.variable_detectada var,
           d.nombre_archivo arch, h.visita_campo_id
    FROM informe_campo_hallazgo h
    JOIN informe_campo_visita v ON v.visita_campo_id = h.visita_campo_id
    LEFT JOIN informe_campo_documento d ON d.id = h.documento_id
''').fetchall()


def buscar(cm, var, arch):
    objetivo = norm(arch)
    return [f for f in filas if f['cm'] == cm and f['var'] == var
            and coincide(norm(f['arch'], True), objetivo)]


# --- control previo: todo debe emparejar antes de escribir nada ---
plan, problemas = [], []
for estado, grupo in (('descartado', DESCARTADOS), ('confirmado', CONFIRMADOS)):
    for cm, var, arch, com in grupo:
        cand = buscar(cm, var, arch)
        if len(cand) == 1:
            plan.append((estado, cand[0]['id'], cand[0]['visita_campo_id'], var, com))
        else:
            problemas.append((estado, cm, var, arch, len(cand)))

print('Emparejados: %d de %d' % (len(plan), len(DESCARTADOS) + len(CONFIRMADOS)))
if problemas:
    for estado, cm, var, arch, n in problemas:
        print('  SIN EMPAREJAR (%d) %s %s | %s' % (n, cm, var, arch))
    sys.exit('Abortado: la base de produccion no coincide con lo validado. No se escribio nada.')

# --- 1. veredicto por hallazgo ---
for estado, hid, _vid, _var, com in plan:
    conn.execute(
        'UPDATE informe_campo_hallazgo SET validacion_estado = ?, validacion_comentario = ?,'
        " validacion_por = 'especialista', validacion_en = CURRENT_TIMESTAMP,"
        ' validacion_fuente = ?, estado_fila = ? WHERE id = ?',
        (estado, com, FUENTE, 0 if estado == 'descartado' else 1, hid))

# --- 2. una variable se desmarca solo si ya no le queda ninguna cita vigente ---
cambios = 0
for estado, hid, vid, var, com in plan:
    if estado != 'descartado':
        continue
    vis = conn.execute(
        'SELECT %s AS valor FROM informe_campo_visita WHERE visita_campo_id = ?' % var,
        (vid,)).fetchone()
    if not vis or not vis['valor']:
        continue
    vivos = conn.execute(
        'SELECT COUNT(*) FROM informe_campo_hallazgo'
        ' WHERE visita_campo_id = ? AND variable_detectada = ? AND estado_fila = 1',
        (vid, var)).fetchone()[0]
    if vivos == 0:
        conn.execute('UPDATE informe_campo_visita SET %s = 0 WHERE visita_campo_id = ?' % var,
                     (vid,))
        cambios += 1
print('Variables desmarcadas en su visita: %d' % cambios)
conn.commit()

# --- 3. recalculo de resumen, alertas y score ---
sys.path.insert(0, '/opt/render/project/src')
sys.path.insert(0, '/opt/render/project/src/app')
import api_server
api_server.rebuild_simon_operational_summary(conn)
conn.commit()

print('--- estado final ---')
for estado, n in conn.execute(
        "SELECT COALESCE(validacion_estado,'sin_validar'), COUNT(*)"
        ' FROM informe_campo_hallazgo GROUP BY 1 ORDER BY 2 DESC'):
    print('   %-12s %d' % (estado, n))
print('   alertas de campo pendientes: %d' % conn.execute(
    "SELECT COUNT(*) FROM app_alerta_priorizada WHERE fuente='campo' AND estado='pendiente'"
).fetchone()[0])
for r in conn.execute('SELECT prioridad_v5, COUNT(*) FROM institucion_resumen GROUP BY 1 ORDER BY 2 DESC'):
    print('   prioridad %-8s %d' % (r[0], r[1]))
conn.close()
print('Listo.')
