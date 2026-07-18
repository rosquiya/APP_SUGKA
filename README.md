# Mapa de IEs – UGEL IBIR-IMAZA

Aplicación web interactiva que muestra todas las **Instituciones Educativas (IEs)** de la **UGEL IBIR-IMAZA** (Bagua, Amazonas, Perú) sobre un mapa georreferenciado.

---

## 🗂️ Estructura del proyecto

```
APP_SUGKA/
├── index.html              # Aplicación principal (entry point)
├── README.md               # Este archivo
│
├── assets/
│   ├── css/                # Estilos CSS adicionales (actualmente en index.html)
│   ├── js/                 # Scripts JS adicionales (actualmente en index.html)
│   └── img/                # Imágenes e íconos
│
├── data/
│   ├── ies_imaza.json      # ← Datos procesados (usado por la app)
│   └── raw/
│       ├── tabla_01.csv                         # Padrón fuente ESCALE
│       └── listado_iiee_georefeerenciadas.xls   # Listado georreferenciado
│
└── scripts/
    └── process_data.py     # Script Python para regenerar ies_imaza.json
```

---

## 🚀 Cómo ejecutar

Requiere un servidor HTTP local (por CORS al cargar el JSON):

```bash
# Con Python (recomendado)
python -m http.server 8080

# Luego abrir en el navegador:
http://localhost:8080
```

---

## 🔄 Regenerar los datos

Si el CSV fuente cambia, regenerar el JSON con:

```bash
cd scripts
python process_data.py
```

---

## 📚 Tecnologías

| Librería | Versión | Uso |
|---|---|---|
| [Leaflet](https://leafletjs.com/) | 1.9.4 | Mapa interactivo |
| [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster) | 1.5.3 | Agrupación de marcadores |
| CartoDB / Esri | — | Capas de mapa base |

---

## 📊 Datos

- **Fuente:** ESCALE – Unidad de Estadística Educativa del MINEDU
- **UGEL:** IBIR-IMAZA (código `10009`)
- **Cobertura:** Distritos de Imaza, Aramango y Nieva (Provincia de Bagua, Amazonas)
- **Total IEs:** 383 georreferenciadas
