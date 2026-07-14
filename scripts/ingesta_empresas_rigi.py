# -*- coding: utf-8 -*-
"""
Ingesta de empresas beneficiarias del RIGI (Régimen de Incentivos para Grandes Inversiones)
hacia la tabla `empresa_rigi`.

Fuente: Ministerio de Economía (argentina.gob.ar/economia/rigi) + medios especializados
(Chequeado, Cronista, LA NACIÓN) que han documentado los proyectos aprobados y en evaluación.

NOTA IMPORTANTE: Los CUITs no están todos disponibles públicamente. Se cargan los datos
de las empresas APROBADAS y las principales en EVALUACIÓN. Los CUITs se buscan manualmente
o pueden quedas como NULL a ser completados con búsqueda AFIP.

Uso:
  python ingesta_empresas_rigi.py            # carga los datos definidos en el script
  python ingesta_empresas_rigi.py --sin-reset  # no borra tabla previa (append)
"""
import argparse
import os
import sys

import requests

FUENTE_URL = "https://www.argentina.gob.ar/economia/rigi"
FUENTE_NOMBRE = "Ministerio de Economía — Régimen de Incentivos para Grandes Inversiones"

# Empresas RIGI aprobadas + principales en evaluación (datos de fuentes públicas)
EMPRESAS_RIGI = [
    # ===== APROBADAS =====
    {
        "razon_social": "Rio Tinto Limited",
        "cuit": None,  # Subsidiary argentina: Rio Tinto Argentina - buscar CUIT
        "proyecto_nombre": "Rincón",
        "sector": "mineria",
        "monto_inversion": 2700000000,
        "moneda_inversion": "USD",
        "provincia": "Salta",
        "estado": "aprobado",
    },
    {
        "razon_social": "Galan Lithium",
        "cuit": None,
        "proyecto_nombre": "Hombre Muerto Oeste",
        "sector": "mineria",
        "monto_inversion": 217000000,
        "moneda_inversion": "USD",
        "provincia": "Catamarca",
        "estado": "aprobado",
    },
    {
        "razon_social": "McEwen Copper Corp",
        "cuit": None,
        "proyecto_nombre": "Los Azules",
        "sector": "mineria",
        "monto_inversion": 2672000000,
        "moneda_inversion": "USD",
        "provincia": "San Juan",
        "estado": "aprobado",
    },
    {
        "razon_social": "YPF Luz / Luz de Campo SA",
        "cuit": None,
        "proyecto_nombre": "Parque Solar El Quemado",
        "sector": "energia",
        "monto_inversion": 211000000,
        "moneda_inversion": "USD",
        "provincia": "Mendoza",
        "estado": "aprobado",
    },
    {
        "razon_social": "VMOS SA",
        "cuit": None,
        "proyecto_nombre": "Vaca Muerta Oleoducto Sur",
        "sector": "energia",
        "monto_inversion": 2486000000,
        "moneda_inversion": "USD",
        "provincia": "Rio Negro",
        "estado": "aprobado",
    },
    {
        "razon_social": "Southern Energy",
        "cuit": None,
        "proyecto_nombre": "Planta de Licuefacción de Gas Natural",
        "sector": "energia",
        "monto_inversion": 6878000000,
        "moneda_inversion": "USD",
        "provincia": "Rio Negro",
        "estado": "aprobado",
    },
    {
        "razon_social": "Sidersa",
        "cuit": None,
        "proyecto_nombre": "Planta Siderúrgica",
        "sector": "industria",
        "monto_inversion": 296000000,
        "moneda_inversion": "USD",
        "provincia": "Buenos Aires",
        "estado": "aprobado",
    },
    # ===== EN EVALUACION / ESTUDIO =====
    {
        "razon_social": "Glencore",
        "cuit": None,
        "proyecto_nombre": "El Pachón",
        "sector": "mineria",
        "monto_inversion": 9500000000,
        "moneda_inversion": "USD",
        "provincia": "San Juan",
        "estado": "en_evaluacion",
    },
    {
        "razon_social": "Glencore",
        "cuit": None,
        "proyecto_nombre": "Agua Rica (MARA)",
        "sector": "mineria",
        "monto_inversion": 4000000000,
        "moneda_inversion": "USD",
        "provincia": "Catamarca",
        "estado": "en_evaluacion",
    },
    {
        "razon_social": "Barrick Gold",
        "cuit": None,
        "proyecto_nombre": "Veladero Expansion",
        "sector": "mineria",
        "monto_inversion": 400000000,
        "moneda_inversion": "USD",
        "provincia": "San Juan",
        "estado": "en_evaluacion",
    },
]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-reset", action="store_true",
                    help="no borrar la tabla antes de cargar (por defecto hace reset)")
    args = ap.parse_args()

    # preparar registros: agregar fuente_url y fuente_nombre
    filas = []
    for emp in EMPRESAS_RIGI:
        reg = dict(emp)
        reg["fuente_url"] = FUENTE_URL
        reg["fuente_nombre"] = FUENTE_NOMBRE
        filas.append(reg)

    print(f"-> Cargando {len(filas)} empresas RIGI...")
    print(f"   Aprobadas: {sum(1 for e in filas if e['estado']=='aprobado')}")
    print(f"   En evaluación: {sum(1 for e in filas if e['estado']=='en_evaluacion')}")
    print(f"   CUITs completados: {sum(1 for e in filas if e['cuit'] is not None)}")
    print()

    if not args.sin_reset:
        print("-> Reset: borrando empresa_rigi previo...")
        rr = requests.delete(
            f"{SUPABASE_URL}/rest/v1/empresa_rigi",
            headers={**HEADERS, "Prefer": "return=minimal"},
            params={"id": "gte.0"},
            timeout=120,
        )
        if rr.status_code >= 400:
            print(f"ERROR en reset: {rr.status_code} {rr.text[:300]}")
            sys.exit(1)

    print("-> Insertando...")
    h = dict(HEADERS)
    h["Prefer"] = "return=minimal"
    rr = requests.post(f"{SUPABASE_URL}/rest/v1/empresa_rigi", headers=h, json=filas, timeout=120)
    if rr.status_code >= 400:
        print(f"ERROR: {rr.status_code} {rr.text[:400]}")
        sys.exit(1)
    print(f"   OK — {len(filas)} empresas cargadas")

    # registrar en fuente_log
    requests.post(f"{SUPABASE_URL}/rest/v1/fuente_log", headers=h, json=[{
        "url": FUENTE_URL,
        "workflow": "ingesta_empresas_rigi.py",
    }], timeout=60)
    print("OK")


if __name__ == "__main__":
    main()
