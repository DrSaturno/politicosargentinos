# -*- coding: utf-8 -*-
"""
Carga la tabla `sueldo` con las dietas actuales por cargo.
Solo se cargan montos con fuente oficial verificable (regla de oro del proyecto).

Fuentes:
  - senador:  recibo oficial publicado por el Senado (senado.gob.ar/dietas),
              liquidación enero 2026. Módulo = $2.554,849933 (Resolución DR 8/24:
              2.500 módulos dieta + 1.000 gastos representación + 500 desarraigo).
  - diputado: recibo oficial publicado por HCDN (transparencia, actualizado dic-2025).

Pendientes (sin fuente oficial con monto publicado):
  - presidente: el Decreto 931/2025 (InfoLeg 422014) confirma que su retribución
    quedó excluida de los aumentos, pero no publica el monto en pesos.
  - gobernadores: cada provincia publica (o no) su escala; cargar a medida que
    se consiga boletín/escala oficial provincial.

Uso:
    python cargar_sueldos.py
"""
import os
import sys

import requests


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
SUPABASE_URL = ENV.get("SUPABASE_URL")
KEY = ENV.get("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_URL or not KEY:
    print("Faltan credenciales en .env")
    sys.exit(1)

HEADERS = {
    "apikey": KEY,
    "Authorization": f"Bearer {KEY}",
    "Content-Type": "application/json",
}

SUELDOS = [
    {
        "cargo": "senador",
        "descripcion": (
            "Dieta bruta mensual total: 2.500 módulos de dieta ($6.387.124,83) "
            "+ 1.000 módulos de gastos de representación ($2.554.849,93) "
            "+ 500 módulos de desarraigo ($1.277.424,97). "
            "Valor del módulo: $2.554,849933 (Resolución DR 8/24). "
            "Liquidación modelo publicada por el Senado, enero 2026."
        ),
        "monto_bruto": 10219399.73,
        "moneda": "ARS",
        "periodo": "2026-01",
        "fuente_url": "https://www.senado.gob.ar/dietas",
        "fuente_nombre": "Senado de la Nación — Dietas (recibo oficial)",
    },
    {
        "cargo": "diputado",
        "descripcion": (
            "Dieta bruta mensual: dieta ($5.620.669,85) + gastos de representación "
            "($428.394,18). No incluye desarraigo ni movilidad, que varían según "
            "distrito. Recibo modelo publicado por HCDN (transparencia), "
            "liquidación diciembre 2025."
        ),
        "monto_bruto": 6049064.03,
        "moneda": "ARS",
        "periodo": "2025-12",
        "fuente_url": "https://www3.hcdn.gob.ar/institucional/gestion/ingresos_diputados/remuneraciones2.0.pdf",
        "fuente_nombre": "HCDN — Dietas y Gastos de Representación (recibo oficial)",
    },
]


def main():
    # evitar duplicados por (cargo, periodo)
    for s in SUELDOS:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/sueldo",
            headers=HEADERS,
            params={"cargo": f"eq.{s['cargo']}", "periodo": f"eq.{s['periodo']}"},
            timeout=60,
        )
        r.raise_for_status()
        if r.json():
            print(f"  {s['cargo']} {s['periodo']}: ya existe, no se duplica")
            continue
        r = requests.post(f"{SUPABASE_URL}/rest/v1/sueldo", headers=HEADERS, json=[s], timeout=60)
        if r.status_code >= 400:
            print(f"ERROR {s['cargo']}: {r.status_code} {r.text[:300]}")
            sys.exit(1)
        print(f"  {s['cargo']} {s['periodo']}: ${s['monto_bruto']:,.2f} cargado")

    print("\nListo. Pendientes sin fuente oficial con monto: presidente, gobernadores, ministros.")


if __name__ == "__main__":
    main()
