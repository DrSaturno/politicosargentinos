# -*- coding: utf-8 -*-
"""
Detector diario de votaciones nuevas en Diputados y Senado.

Recorre los listados oficiales, compara contra `fuente_log` y reporta actas
que todavía no fueron ingestadas. No carga votos automáticamente: la carga
está atada a una ley destacada (curaduría manual), este script solo avisa.

Salida: una línea por acta nueva, formato
    [diputados] 5957 https://votaciones.hcdn.gob.ar/votacion/5957
    [senado]    2641 https://www.senado.gob.ar/votaciones/detalleActa/2641

Exit code 0 siempre que pudo consultar al menos una cámara; n8n decide qué
hacer con la salida (mail/Telegram). Exit 2 si ambas fuentes fallaron.
"""
import os
import re
import sys

import requests

UA = {"User-Agent": "Mozilla/5.0 (TransparenciaAR; detector de votaciones)"}


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
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}

FUENTES = [
    # (camara, url listado, regex de links a actas, template url acta)
    ("diputados", "https://votaciones.hcdn.gob.ar/",
     r"/votacion/(\d+)", "https://votaciones.hcdn.gob.ar/votacion/{}"),
    ("senado", "https://www.senado.gob.ar/votaciones/actas",
     r"/votaciones/detalleActa/(\d+)", "https://www.senado.gob.ar/votaciones/detalleActa/{}"),
]


def urls_ya_registradas():
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/votacion",
        headers=HEADERS, params={"select": "fuente_url", "limit": "10000"}, timeout=60,
    )
    r.raise_for_status()
    registradas = {v["fuente_url"] for v in r.json()}
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/fuente_log",
        headers=HEADERS, params={"select": "url", "limit": "10000"}, timeout=60,
    )
    r.raise_for_status()
    registradas |= {v["url"] for v in r.json()}
    return registradas


def main():
    if not SUPABASE_URL or not KEY:
        print("Faltan credenciales (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)")
        sys.exit(2)

    registradas = urls_ya_registradas()
    fallas = 0
    nuevas = 0

    for camara, listado, patron, template in FUENTES:
        try:
            r = requests.get(listado, headers=UA, timeout=90)
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"[{camara}] ERROR consultando listado: {type(e).__name__}", file=sys.stderr)
            fallas += 1
            continue
        ids = sorted({int(m) for m in re.findall(patron, r.text)}, reverse=True)
        for acta_id in ids[:30]:  # solo las más recientes
            url = template.format(acta_id)
            if url not in registradas:
                print(f"[{camara}] {acta_id} {url}")
                nuevas += 1

    if fallas == len(FUENTES):
        sys.exit(2)
    if nuevas == 0:
        print("sin votaciones nuevas")


if __name__ == "__main__":
    main()
