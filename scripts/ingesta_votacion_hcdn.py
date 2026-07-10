# -*- coding: utf-8 -*-
"""
Ingesta genérica de una votación nominal de Diputados desde la Plataforma de
Votaciones Abiertas (votaciones.hcdn.gob.ar). Pensado para correr a mano o
desde n8n (Execute Command).

Uso:
    python ingesta_votacion_hcdn.py --votacion-id 5956 --ley-slug super-rigi \
        --camara diputados --fecha 2026-06-24 --resultado aprobada

La ley (slug) tiene que existir en la tabla `ley`. El script:
  1. Crea la votación si no existe (dedup por ley+camara+fecha).
  2. Descarga el acta oficial y parsea la tabla de votos nominales.
  3. Matchea nombres contra `persona` (cargo=diputado) y upserta `voto`.
  4. Registra la captura en `fuente_log`.
  5. Escribe votos_sin_match.txt si algún nombre no matchea (revisar a mano).

Sale con código != 0 si algo falla, para que n8n alerte.
"""
import argparse
import os
import sys
import unicodedata

import requests
from bs4 import BeautifulSoup


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

MAPA_VOTO = {
    "AFIRMATIVO": "afirmativo",
    "NEGATIVO": "negativo",
    "ABSTENCION": "abstencion",
    "AUSENTE": "ausente",
}


def sb_get(tabla, params):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=HEADERS, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def sb_upsert(tabla, filas, on_conflict):
    h = dict(HEADERS)
    h["Prefer"] = "resolution=merge-duplicates,return=representation"
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{tabla}?on_conflict={on_conflict}", headers=h, json=filas, timeout=120)
    if r.status_code >= 400:
        print(f"ERROR upsert {tabla}: {r.status_code} {r.text[:500]}")
        sys.exit(1)
    return r.json()


def sb_insert(tabla, filas):
    h = dict(HEADERS)
    h["Prefer"] = "return=representation"
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{tabla}", headers=h, json=filas, timeout=120)
    if r.status_code >= 400:
        print(f"ERROR insert {tabla}: {r.status_code} {r.text[:500]}")
        sys.exit(1)
    return r.json()


def normalizar(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().replace(",", " ").replace(".", " ").split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--votacion-id", required=True, help="id numérico del acta en votaciones.hcdn.gob.ar")
    ap.add_argument("--ley-slug", required=True)
    ap.add_argument("--camara", default="diputados")
    ap.add_argument("--fecha", required=True, help="YYYY-MM-DD")
    ap.add_argument("--resultado", default=None, help="aprobada / rechazada")
    args = ap.parse_args()

    url = f"https://votaciones.hcdn.gob.ar/votacion/{args.votacion_id}"

    leyes = sb_get("ley", {"slug": f"eq.{args.ley_slug}", "select": "id"})
    if not leyes:
        print(f"No existe ley con slug '{args.ley_slug}'. Cargala primero en la tabla ley.")
        sys.exit(1)
    ley_id = leyes[0]["id"]

    existentes = sb_get("votacion", {"ley_id": f"eq.{ley_id}", "camara": f"eq.{args.camara}", "fecha": f"eq.{args.fecha}"})
    if existentes:
        votacion_id = existentes[0]["id"]
        print(f"votación ya existe (id={votacion_id}), se re-upsertan los votos")
    else:
        res = sb_insert("votacion", [{
            "ley_id": ley_id,
            "camara": args.camara,
            "fecha": args.fecha,
            "resultado": args.resultado,
            "fuente_url": url,
        }])
        votacion_id = res[0]["id"]
        print(f"votación creada (id={votacion_id})")

    r = requests.get(url, timeout=120)
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "lxml")
    tabla = soup.find("table", id="myTable")
    if tabla is None:
        print("No se encontró la tabla de votos (cambió la estructura de la página?)")
        sys.exit(1)
    filas = tabla.find("tbody").find_all("tr")
    print(f"filas en acta oficial: {len(filas)}")

    personas = sb_get("persona", {"cargo": "eq.diputado", "select": "id,nombre,apellido", "limit": "400"})
    indice = {}
    for p in personas:
        indice[normalizar(f"{p['apellido']} {p['nombre']}")] = p["id"]
        primer = normalizar(p["nombre"]).split()[0] if p["nombre"].strip() else ""
        indice.setdefault(normalizar(p["apellido"]) + " " + primer, p["id"])

    votos, sin_match = [], []
    for tr in filas:
        celdas = [td.get_text(strip=True) for td in tr.find_all("td")]
        celdas = [c for c in celdas if c]
        if len(celdas) < 2:
            continue
        nombre_completo, valor_crudo = celdas[0], celdas[-1]
        valor = MAPA_VOTO.get(valor_crudo.upper().replace("Ó", "O"))
        if not valor:
            continue
        clave = normalizar(nombre_completo)
        pid = indice.get(clave)
        if not pid:
            partes = clave.split()
            for corte in range(len(partes) - 1, 0, -1):
                intento = " ".join(partes[:corte + 1])
                if intento in indice:
                    pid = indice[intento]
                    break
        if pid:
            votos.append({"votacion_id": votacion_id, "persona_id": pid, "valor": valor})
        else:
            sin_match.append(f"{nombre_completo} [{valor_crudo}]")

    print(f"votos matcheados: {len(votos)} | sin match: {len(sin_match)}")
    if sin_match:
        with open("votos_sin_match.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(sin_match))
        print("-> revisar votos_sin_match.txt")

    if votos:
        sb_upsert("voto", votos, on_conflict="votacion_id,persona_id")
        print(f"{len(votos)} votos cargados")

    sb_insert("fuente_log", [{"url": url, "workflow": "ingesta_votacion_hcdn.py"}])
    print("OK")


if __name__ == "__main__":
    main()
