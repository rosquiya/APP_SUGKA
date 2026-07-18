import csv, json, io
from pathlib import Path

# Rutas relativas al directorio raíz del proyecto (un nivel arriba de scripts/)
ROOT = Path(__file__).parent.parent
INPUT_CSV   = ROOT / 'data' / 'raw' / 'tabla_01.csv'
OUTPUT_JSON = ROOT / 'data' / 'ies_imaza.json'

def fix_encoding(s):
    """Re-encode latin-1 string as UTF-8."""
    try:
        return s.encode('latin-1').decode('utf-8')
    except Exception:
        return s

with open(INPUT_CSV, encoding='latin-1') as f:
    raw = f.read()

reader = csv.reader(io.StringIO(raw))
headers = next(reader)

ies = []
for row in reader:
    if len(row) < 19:
        continue
    try:
        lat = float(row[16])
        lon = float(row[17])
    except ValueError:
        continue

    nombre     = fix_encoding(row[3].strip())
    nivel      = fix_encoding(row[14].strip())
    distrito   = fix_encoding(row[7].strip())
    centro_pob = fix_encoding(row[10].strip())
    gestion    = fix_encoding(row[15].strip())

    # Si el nombre es solo un código numérico, agregar contexto
    try:
        int(nombre)
        nombre = f"IE {nombre} - {centro_pob}"
    except ValueError:
        pass

    ies.append({
        'nombre':       nombre,
        'codModular':   row[1].strip(),
        'nivel':        nivel,
        'distrito':     distrito,
        'centroPoblado': centro_pob,
        'gestion':      gestion,
        'lat':          lat,
        'lon':          lon,
        'altitud':      row[18].strip()
    })

print(f"Total IEs procesadas: {len(ies)}")
print("Niveles encontrados:")
for n in sorted(set(ie['nivel'] for ie in ies)):
    print(f"  - {n}")

with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(ies, f, ensure_ascii=False, indent=2)

print(f"\nArchivo guardado en: {OUTPUT_JSON}")
