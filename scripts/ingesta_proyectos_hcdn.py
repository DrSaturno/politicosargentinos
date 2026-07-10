# -*- coding: utf-8 -*-
"""
Ingesta de proyectos parlamentarios desde datos.hcdn.gob.ar (CKAN, dataset
"proyectos-parlamentarios") hacia la tabla `proyecto`. Pensado para correr
a mano (backfill) o desde n8n (cron diario).

Solo carga proyectos cuyo AUTOR matchea un diputado activo en `persona`
(el dataset es de la HCDN; proyectos del Senado se ingestarán aparte).

Uso:
    python ingesta_proyectos_hcdn.py --desde 2026-01-01
    python ingesta_proyectos_hcdn.py --dias 7        # últimos 7 días (cron)
"""
import argparse
import os
import sys
import time
import unicodedata
from datetime import date, timedelta

import requests

UA = {"User-Agent": "Mozilla/5.0 (TransparenciaAR; ingesta de datos abiertos)"}


def get_con_reintentos(url, params=None, intentos=4, timeout=120):
    """datos.hcdn.gob.ar es intermitente: reintentar con backoff."""
    for i in range(intentos):
        try:
            return requests.get(url, params=params, headers=UA, timeout=timeout)
        except requests.exceptions.RequestException as e:
            if i == intentos - 1:
                raise
            espera = 15 * (i + 1)
            print(f"  intento {i + 1} falló ({type(e).__name__}), reintento en {espera}s...")
            time.sleep(espera)

RESOURCE_ID = "22b2d52c-7a0e-426b-ac0a-a3326c388ba6"
CKAN_SQL = "https://datos.hcdn.gob.ar/api/3/action/datastore_search_sql"
DATASET_URL = "https://datos.hcdn.gob.ar/dataset/proyectos-parlamentarios"


def cargar_env():
    env = {}
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(ruta):
        with open(ruta, encoding="utf-8-sig") as f:
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
    print("Faltan credenciales (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)")
    sys.exit(1)

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
}


def normalizar(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().replace(",", " ").replace(".", " ").split())


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--desde", help="YYYY-MM-DD")
    g.add_argument("--dias", type=int, help="últimos N días")
    args = ap.parse_args()

    desde = args.desde or (date.today() - timedelta(days=args.dias)).isoformat()

    sql = (
        f'SELECT "PROYECTO_ID","TITULO","PUBLICACION_FECHA","EXP_DIPUTADOS","TIPO","AUTOR" '
        f'FROM "{RESOURCE_ID}" '
        f"WHERE \"PUBLICACION_FECHA\" >= '{desde}' AND \"CAMARA_ORIGEN\" = 'Diputados' "
        f'ORDER BY "PUBLICACION_FECHA"'
    )
    r = get_con_reintentos(CKAN_SQL, params={"sql": sql}, timeout=180)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        print("ERROR CKAN:", str(data.get("error"))[:300])
        sys.exit(1)
    registros = data["result"]["records"]
    print(f"proyectos en fuente desde {desde}: {len(registros)}")

    # índice de diputados
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/persona",
        headers=HEADERS,
        params={"cargo": "eq.diputado", "select": "id,nombre,apellido", "limit": "400"},
        timeout=60,
    )
    r.raise_for_status()
    indice = {}
    for p in r.json():
        indice[normalizar(f"{p['apellido']} {p['nombre']}")] = p["id"]
        primer = normalizar(p["nombre"]).split()[0] if p["nombre"].strip() else ""
        indice.setdefault(normalizar(p["apellido"]) + " " + primer, p["id"])

    # expedientes ya cargados (dedup)
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/proyecto",
        headers=HEADERS,
        params={"select": "expediente", "limit": "100000"},
        timeout=120,
    )
    r.raise_for_status()
    existentes = {p["expediente"] for p in r.json()}

    nuevos, sin_match = [], 0
    for reg in registros:
        exp = reg.get("EXP_DIPUTADOS") or reg.get("PROYECTO_ID")
        if not exp or exp in existentes:
            continue
        autor = reg.get("AUTOR") or ""
        clave = normalizar(autor)
        pid = indice.get(clave)
        if not pid:
            partes = clave.split()
            for corte in range(len(partes) - 1, 0, -1):
                if " ".join(partes[:corte + 1]) in indice:
                    pid = indice[" ".join(partes[:corte + 1])]
                    break
        if not pid:
            sin_match += 1  # autor no es diputado actual (mandato anterior) — se salta
            continue
        nuevos.append({
            "persona_id": pid,
            "expediente": exp,
            "titulo": (reg.get("TITULO") or "")[:500],
            "fecha": (reg.get("PUBLICACION_FECHA") or "")[:10] or None,
            "estado": reg.get("TIPO"),
            "fuente_url": DATASET_URL,
        })
        existentes.add(exp)

    print(f"nuevos: {len(nuevos)} | autores sin match (no son diputados actuales): {sin_match}")

    for i in range(0, len(nuevos), 200):
        lote = nuevos[i:i + 200]
        h = dict(HEADERS)
        h["Prefer"] = "return=minimal"
        rr = requests.post(f"{SUPABASE_URL}/rest/v1/proyecto", headers=h, json=lote, timeout=120)
        if rr.status_code >= 400:
            print(f"ERROR lote {i}: {rr.status_code} {rr.text[:300]}")
            sys.exit(1)
        print(f"  lote {i}-{i + len(lote)} OK")

    h = dict(HEADERS)
    h["Prefer"] = "return=minimal"
    requests.post(f"{SUPABASE_URL}/rest/v1/fuente_log", headers=h, json=[{
        "url": DATASET_URL,
        "workflow": "ingesta_proyectos_hcdn.py",
    }], timeout=60)
    print("OK")


if __name__ == "__main__":
    main()
