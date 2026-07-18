import pandas as pd
import sqlite3
from pathlib import Path
import warnings

# Ignorar advertencia de beautifulsoup sobre HTML
warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
XLS_PATH = ROOT / 'data' / 'raw' / 'listado_iiee_georefeerenciadas.xls'
DB_PATH = ROOT / 'data' / 'database' / 'sugka_demo.db'

print("Leyendo XLS (formato HTML)...")
with open(XLS_PATH, 'r', encoding='latin-1') as f:
    html_content = f.read()
dfs = pd.read_html(html_content)
df = dfs[0]

# Limpiar columnas
df.columns = [c.strip() for c in df.columns]

# Conectar a la DB
conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# Contar cuántos antes
c_before = cursor.execute("SELECT count(*) FROM dim_institucion").fetchone()[0]
print(f"IEs antes de actualizar: {c_before}")

# Limpiar tabla para tener solo el universo nuevo
cursor.execute("DELETE FROM dim_institucion")

# Mapear e insertar
count = 0
for idx, row in df.iterrows():
    cod_mod = str(row.get('Código Modular', '')).strip().zfill(7)
    if not cod_mod or cod_mod == 'nan':
        continue
        
    cod_inst = str(row.get('Código Institución', ''))
    cod_local = str(row.get('Código Local', ''))
    nombre = str(row.get('Nombre de SS.EE.', ''))
    nivel = str(row.get('Nivel / Modalidad', ''))
    gestion = str(row.get('Gestion / Dependencia', ''))
    direccion = str(row.get('Dirección', ''))
    depto = str(row.get('Departamento', ''))
    prov = str(row.get('Provincia', ''))
    dist = str(row.get('Distrito', ''))
    cp = str(row.get('Centro Poblado', ''))
    lat = pd.to_numeric(row.get('Latitud'), errors='coerce')
    lon = pd.to_numeric(row.get('Longitud'), errors='coerce')
    alt = pd.to_numeric(row.get('Altitud'), errors='coerce')
    fuente = str(row.get('Fuente de coordenadas', ''))
    
    if pd.isna(lat): lat = None
    if pd.isna(lon): lon = None
    if pd.isna(alt): alt = None
    
    # SQLite UPSERT
    cursor.execute("""
        INSERT INTO dim_institucion (
            codigo_modular, codigo_institucion, codigo_local, nombre_iiee, 
            nivel_modalidad, tipo_gestion, direccion_iiee, departamento, 
            provincia, distrito, centro_poblado, latitud, longitud, altitud, 
            fuente_coordenadas
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(codigo_modular) DO UPDATE SET
            codigo_institucion=excluded.codigo_institucion,
            codigo_local=excluded.codigo_local,
            nombre_iiee=excluded.nombre_iiee,
            nivel_modalidad=excluded.nivel_modalidad,
            tipo_gestion=excluded.tipo_gestion,
            direccion_iiee=excluded.direccion_iiee,
            departamento=excluded.departamento,
            provincia=excluded.provincia,
            distrito=excluded.distrito,
            centro_poblado=excluded.centro_poblado,
            latitud=excluded.latitud,
            longitud=excluded.longitud,
            altitud=excluded.altitud,
            fuente_coordenadas=excluded.fuente_coordenadas
    """, (cod_mod, cod_inst, cod_local, nombre, nivel, gestion, direccion, 
          depto, prov, dist, cp, lat, lon, alt, fuente))
    count += 1

conn.commit()

c_after = cursor.execute("SELECT count(*) FROM dim_institucion").fetchone()[0]
print(f"IEs insertadas/actualizadas: {count}")
print(f"Total IEs ahora en la BD: {c_after}")

conn.close()
