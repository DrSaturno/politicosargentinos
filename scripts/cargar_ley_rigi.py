# -*- coding: utf-8 -*-
"""
Carga en Supabase el caso testigo RIGI / Súper RIGI:
  1. Tabla `ley`: RIGI original (Ley 27.742) + Súper RIGI (media sanción 24/06/2026)
  2. Tabla `votacion` + `voto`: votación nominal del Súper RIGI en Diputados
     (fuente oficial: https://votaciones.hcdn.gob.ar/votacion/5956)
  3. Tabla `provincia_adhesion`: estado de adhesión de las 24 jurisdicciones al RIGI
     (fuente oficial: PDF de argentina.gob.ar al 29/08/2025 + normas provinciales)

Uso:
    python cargar_ley_rigi.py

Requiere .env con SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY.
La lógica de parseo de votaciones.hcdn.gob.ar es la misma que va a usar
el workflow n8n de ingesta diaria (ver n8n/).
"""
import os
import sys
import unicodedata
from datetime import date

import requests
from bs4 import BeautifulSoup

# ---------- credenciales ----------

def cargar_env():
    env = {}
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8-sig") as f:  # utf-8-sig: tolera BOM de PowerShell
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    env[k.strip()] = v.strip()
    return env

ENV = cargar_env()
SUPABASE_URL = ENV.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
KEY = ENV.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_URL or not KEY:
    print("Faltan credenciales en .env (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)")
    sys.exit(1)

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
}


def sb_get(tabla, params):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=HEADERS, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def sb_upsert(tabla, filas, on_conflict):
    h = dict(HEADERS)
    h["Prefer"] = "resolution=merge-duplicates,return=representation"
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{tabla}?on_conflict={on_conflict}",
        headers=h, json=filas, timeout=120,
    )
    if r.status_code >= 400:
        print(f"ERROR upsert {tabla}: {r.status_code} {r.text[:500]}")
        sys.exit(1)
    return r.json()


def sb_insert(tabla, filas):
    h = dict(HEADERS)
    h["Prefer"] = "return=minimal"
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=h, json=filas, timeout=120)
    if r.status_code >= 400:
        print(f"ERROR insert {tabla}: {r.status_code} {r.text[:500]}")
        sys.exit(1)


# ---------- normalización de nombres ----------

def normalizar(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().replace(",", " ").replace(".", " ").split())


# ---------- 1. leyes ----------

LEYES = [
    {
        "titulo": "RIGI — Régimen de Incentivo para Grandes Inversiones (Ley Bases 27.742, Título VII)",
        "slug": "rigi",
        "expediente": "Ley 27.742",
        "camara_origen": "diputados",
        "estado": "sancionada",
        "resumen": (
            "Régimen de incentivos fiscales, aduaneros y cambiarios por 30 años para "
            "inversiones mayores a USD 200 millones. Sancionado dentro de la Ley Bases "
            "el 28/06/2024. Las provincias adhieren por ley provincial."
        ),
        "fuente_url": "https://servicios.infoleg.gob.ar/infolegInternet/anexos/400000-404999/403230/norma.htm",
        "fuente_nombre": "InfoLeg — Ley 27.742",
    },
    {
        "titulo": "Súper RIGI — Régimen de Incentivo para Grandes Inversiones en Nuevas Industrias",
        "slug": "super-rigi",
        "expediente": "O.D. 149/2026",
        "camara_origen": "diputados",
        "estado": "media_sancion",
        "resumen": (
            "Incentivos fiscales (alícuota especial de Ganancias del 15%), aduaneros y "
            "cambiarios para nuevas actividades económicas (IA, litio, data centers, "
            "industrias del futuro). Media sanción en Diputados el 24/06/2026 "
            "(130 afirmativos, 106 negativos, 7 abstenciones). En tratamiento en el Senado."
        ),
        "fuente_url": "https://votaciones.hcdn.gob.ar/votacion/5956",
        "fuente_nombre": "HCDN — Plataforma de Votaciones Abiertas",
    },
]


def cargar_leyes():
    print("== Cargando leyes ==")
    res = sb_upsert("ley", LEYES, on_conflict="slug")
    ids = {r["slug"]: r["id"] for r in res}
    print(f"  leyes: {ids}")
    return ids


# ---------- 2. votación nominal Súper RIGI ----------

VOTACION_URL = "https://votaciones.hcdn.gob.ar/votacion/5956"
MAPA_VOTO = {
    "AFIRMATIVO": "afirmativo",
    "NEGATIVO": "negativo",
    "ABSTENCION": "abstencion",
    "AUSENTE": "ausente",
}


def cargar_votacion(ley_id):
    print("== Cargando votación nominal Súper RIGI (Diputados 24/06/2026) ==")

    # evitar duplicados si se corre dos veces
    existentes = sb_get("votacion", {"ley_id": f"eq.{ley_id}", "camara": "eq.diputados", "fecha": "eq.2026-06-24"})
    if existentes:
        votacion_id = existentes[0]["id"]
        print(f"  votación ya existe (id={votacion_id}), no se duplica")
    else:
        res = sb_upsert("votacion", [{
            "ley_id": ley_id,
            "camara": "diputados",
            "fecha": "2026-06-24",
            "resultado": "aprobada",
            "fuente_url": VOTACION_URL,
        }], on_conflict="id")
        votacion_id = res[0]["id"]
        print(f"  votación creada (id={votacion_id})")

    # descarga y parseo de la página oficial
    r = requests.get(VOTACION_URL, timeout=120)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "lxml")
    tabla = soup.find("table", id="myTable")
    filas = tabla.find("tbody").find_all("tr")
    print(f"  filas en acta oficial: {len(filas)}")

    # índice de diputados en la base
    personas = sb_get("persona", {"cargo": "eq.diputado", "select": "id,nombre,apellido", "limit": "400"})
    indice = {}
    for p in personas:
        clave = normalizar(f"{p['apellido']} {p['nombre']}")
        indice[clave] = p["id"]
        # también apellido + primer nombre
        primer = normalizar(p["nombre"]).split()[0] if p["nombre"].strip() else ""
        indice.setdefault(normalizar(p["apellido"]) + " " + primer, p["id"])

    votos, sin_match = [], []
    for tr in filas:
        tds = [td.get_text(strip=True) for td in tr.find_all("td")]
        celdas = [c for c in tds if c]
        if len(celdas) < 2:
            continue
        nombre_completo, valor_crudo = celdas[0], celdas[-1]
        valor = MAPA_VOTO.get(valor_crudo.upper().replace("Ó", "O"))
        if not valor:
            continue  # "SIN VOTAR" u otros estados no mapeados
        clave = normalizar(nombre_completo)
        pid = indice.get(clave)
        if not pid:
            # fallback: apellido + primer nombre
            partes = normalizar(nombre_completo).split()
            for corte in range(len(partes) - 1, 0, -1):
                intento = " ".join(partes[:corte + 1])
                if intento in indice:
                    pid = indice[intento]
                    break
        if pid:
            votos.append({"votacion_id": votacion_id, "persona_id": pid, "valor": valor})
        else:
            sin_match.append(f"{nombre_completo} [{valor_crudo}]")

    print(f"  votos matcheados: {len(votos)} | sin match: {len(sin_match)}")
    if sin_match:
        with open("votos_sin_match.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(sin_match))
        print("  -> revisar votos_sin_match.txt")

    if votos:
        sb_upsert("voto", votos, on_conflict="votacion_id,persona_id")
        print(f"  {len(votos)} votos cargados")

    sb_insert("fuente_log", [{
        "url": VOTACION_URL,
        "workflow": "cargar_ley_rigi.py (manual)",
    }])


# ---------- 3. adhesiones provinciales al RIGI ----------

FUENTE_PDF = "https://www.argentina.gob.ar/sites/default/files/adhesion_rigi_rra.pdf"

# Estado al 29/08/2025 según PDF oficial del Gobierno Nacional (argentina.gob.ar),
# normas provinciales según registro público de cada legislatura.
ADHESIONES = [
    ("Buenos Aires",        "no_adherida",    None,                 FUENTE_PDF),
    ("CABA",                "en_tratamiento", None,                 FUENTE_PDF),
    ("Catamarca",           "adherida",       "Ley 5863",           FUENTE_PDF),
    ("Chaco",               "adherida",       "Ley 4086-F",         FUENTE_PDF),
    ("Chubut",              "adherida",       "Ley IX N° 171 (excluye minería)", FUENTE_PDF),
    ("Córdoba",             "adherida",       "Ley 10.997",         FUENTE_PDF),
    ("Corrientes",          "adherida",       "Ley 6694",           FUENTE_PDF),
    ("Entre Ríos",          "adherida",       None,                 FUENTE_PDF),
    ("Formosa",             "no_adherida",    None,                 FUENTE_PDF),
    ("Jujuy",               "adherida",       "Ley 6409",           FUENTE_PDF),
    ("La Pampa",            "no_adherida",    None,                 FUENTE_PDF),
    ("La Rioja",            "no_adherida",    None,                 FUENTE_PDF),
    ("Mendoza",             "adherida",       "Ley 9567",           FUENTE_PDF),
    ("Misiones",            "adherida",       None,                 FUENTE_PDF),
    ("Neuquén",             "adherida",       None,                 FUENTE_PDF),
    ("Río Negro",           "adherida",       "Ley 5724",           FUENTE_PDF),
    ("Salta",               "adherida",       "Ley 8451",           FUENTE_PDF),
    ("San Juan",            "adherida",       "Ley 2671-I",         FUENTE_PDF),
    ("San Luis",            "adherida",       "Ley VIII-1135/2024", FUENTE_PDF),
    ("Santa Cruz",          "en_tratamiento", None,                 FUENTE_PDF),
    ("Santa Fe",            "adherida",       "Ley 14.386 (Ley Tributaria 2025)",
     "https://www.santafe.gov.ar/index.php/web/content/view/full/258340"),
    ("Santiago del Estero", "no_adherida",    None,                 FUENTE_PDF),
    ("Tierra del Fuego",    "en_tratamiento", None,                 FUENTE_PDF),
    ("Tucumán",             "adherida",       "Ley 9803",           FUENTE_PDF),
]


def cargar_adhesiones(ley_id):
    print("== Cargando adhesiones provinciales al RIGI ==")

    gobernadores = sb_get("persona", {"cargo": "eq.gobernador", "select": "id,provincia"})
    por_provincia = {normalizar(g["provincia"] or ""): g["id"] for g in gobernadores}

    filas = []
    for provincia, estado, norma, fuente in ADHESIONES:
        gid = por_provincia.get(normalizar(provincia))
        if gid is None and normalizar(provincia) == "caba":
            gid = por_provincia.get("ciudad autonoma de buenos aires") or por_provincia.get("capital federal")
        filas.append({
            "provincia": provincia,
            "ley_id": ley_id,
            "estado": estado,
            "gobernador_id": gid,
            "norma_provincial": norma,
            "fuente_url": fuente,
        })

    sb_upsert("provincia_adhesion", filas, on_conflict="provincia,ley_id")
    con_gob = sum(1 for f in filas if f["gobernador_id"])
    print(f"  {len(filas)} jurisdicciones cargadas ({con_gob} con gobernador linkeado)")


if __name__ == "__main__":
    ids = cargar_leyes()
    cargar_votacion(ids["super-rigi"])
    cargar_adhesiones(ids["rigi"])
    print("\nListo.")
