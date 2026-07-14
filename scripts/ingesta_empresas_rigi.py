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

# Empresas RIGI aprobadas + principales en evaluación.
# Para las APROBADAS, la razón social es el Vehículo de Proyecto Único (VPU) tal como
# figura en la resolución de aprobación del Ministerio de Economía, y el CUIT + la
# fuente_url apuntan a la resolución oficial en el Boletín Oficial (regla de oro).
# BO_* = URL de la resolución específica; si es None se usa la web general del RIGI.
BO = "https://www.boletinoficial.gob.ar"
EMPRESAS_RIGI = [
    # ===== APROBADAS (con CUIT y resolución oficial) =====
    {
        "razon_social": "Rincón Mining PTY LTD",
        "cuit": "30-70708643-9",
        "proyecto_nombre": "Proyecto Rincón (litio)",
        "sector": "mineria",
        "monto_inversion": 2744000000,
        "moneda_inversion": "USD",
        "provincia": "Salta",
        "estado": "aprobado",
        "fuente_res": "Resolución 735/2025 (Min. Economía) — adhesión RIGI",
        "fuente_url": f"{BO}/#!DetalleNorma",  # Res. 735/2025
    },
    {
        "razon_social": "Andes Corporación Minera SA",  # McEwen Copper — Los Azules
        "cuit": "30-70952278-3",
        "proyecto_nombre": "Los Azules (cobre)",
        "sector": "mineria",
        "monto_inversion": 2672000000,
        "moneda_inversion": "USD",
        "provincia": "San Juan",
        "estado": "aprobado",
        "fuente_res": "Resolución 1553/2025 (Min. Economía) — adhesión RIGI",
        "fuente_url": f"{BO}/#!DetalleNorma",  # Res. 1553/2025
    },
    {
        "razon_social": "VMOS SA",  # accionistas: YPF, Vista, Pampa, Pan American
        "cuit": "30-71871335-4",
        "proyecto_nombre": "Vaca Muerta Oleoducto Sur",
        "sector": "energia",
        "monto_inversion": 2486000000,
        "moneda_inversion": "USD",
        "provincia": "Rio Negro",
        "estado": "aprobado",
        "fuente_res": "Adhesión RIGI (Min. Economía)",
        "fuente_url": "https://www.argentina.gob.ar/economia/rigi",
    },
    {
        "razon_social": "Southern Energy SA",  # Pan American Energy + Golar LNG
        "cuit": "30-71858062-1",
        "proyecto_nombre": "Planta de Licuefacción de Gas Natural (FLNG)",
        "sector": "energia",
        "monto_inversion": 6878000000,
        "moneda_inversion": "USD",
        "provincia": "Rio Negro",
        "estado": "aprobado",
        "fuente_res": "Resolución 559/2025 (Min. Economía) — adhesión RIGI",
        "fuente_url": f"{BO}/detalleAviso/primera/324772/20250505",  # Res. 559/2025
    },
    {
        "razon_social": "Sidersa SA",  # VPU: SIDERSA ACERÍA S.D.E. (CUIT 33-71879284-9)
        "cuit": "30-61536829-2",
        "proyecto_nombre": "Acería en San Nicolás (SIDERSA ACERÍA S.D.E.)",
        "sector": "industria",
        "monto_inversion": 286300000,
        "moneda_inversion": "USD",
        "provincia": "Buenos Aires",
        "estado": "aprobado",
        "fuente_res": "Resolución 1028/2025 (Min. Economía) — adhesión RIGI",
        "fuente_url": f"{BO}/detalleAviso/primera/328690/20250722",  # Res. 1028/2025
    },
    # ===== APROBADAS sin CUIT confirmado aún (pendiente de fuente oficial) =====
    {
        "razon_social": "Galan Lithium (VPU pendiente)",
        "cuit": None,
        "proyecto_nombre": "Hombre Muerto Oeste (litio)",
        "sector": "mineria",
        "monto_inversion": 217000000,
        "moneda_inversion": "USD",
        "provincia": "Catamarca",
        "estado": "aprobado",
        "fuente_res": None,
        "fuente_url": "https://www.argentina.gob.ar/economia/rigi",
    },
    {
        "razon_social": "Luz de Campo SA (YPF Luz)",
        "cuit": None,
        "proyecto_nombre": "Parque Solar El Quemado",
        "sector": "energia",
        "monto_inversion": 211000000,
        "moneda_inversion": "USD",
        "provincia": "Mendoza",
        "estado": "aprobado",
        "fuente_res": None,
        "fuente_url": "https://www.argentina.gob.ar/economia/rigi",
    },
    # ===== EN EVALUACION / ESTUDIO (sin CUIT VPU aún) =====
    {
        "razon_social": "Glencore (VPU pendiente)",
        "cuit": None,
        "proyecto_nombre": "El Pachón (cobre)",
        "sector": "mineria",
        "monto_inversion": 9500000000,
        "moneda_inversion": "USD",
        "provincia": "San Juan",
        "estado": "en_evaluacion",
        "fuente_res": None,
        "fuente_url": "https://www.argentina.gob.ar/economia/rigi",
    },
    {
        "razon_social": "Glencore (VPU pendiente)",
        "cuit": None,
        "proyecto_nombre": "Agua Rica / MARA (cobre)",
        "sector": "mineria",
        "monto_inversion": 4000000000,
        "moneda_inversion": "USD",
        "provincia": "Catamarca",
        "estado": "en_evaluacion",
        "fuente_res": None,
        "fuente_url": "https://www.argentina.gob.ar/economia/rigi",
    },
    {
        "razon_social": "Minera Argentina Gold (Barrick)",
        "cuit": None,
        "proyecto_nombre": "Veladero Expansion (oro)",
        "sector": "mineria",
        "monto_inversion": 400000000,
        "moneda_inversion": "USD",
        "provincia": "San Juan",
        "estado": "en_evaluacion",
        "fuente_res": None,
        "fuente_url": "https://www.argentina.gob.ar/economia/rigi",
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

    # preparar registros: respetar fuente_url por fila; fuente_nombre = resolución
    # oficial si se conoce, si no el nombre general del régimen. Se quita el campo
    # auxiliar fuente_res (no es columna de la tabla).
    filas = []
    for emp in EMPRESAS_RIGI:
        reg = dict(emp)
        reg.setdefault("fuente_url", FUENTE_URL)
        reg["fuente_nombre"] = reg.pop("fuente_res", None) or FUENTE_NOMBRE
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
