# -*- coding: utf-8 -*-
"""
Ingesta de aportes de campaña declarados desde la Cámara Nacional Electoral
(aportantes.electoral.gob.ar) hacia la tabla `aporte_campana`.

La fuente expone el dataset COMPLETO en un solo CSV (sin paginación):
  https://aportantes.electoral.gob.ar/aportes/descargar-csv/
~80.000 registros, ~20 MB. Columnas (encabezado real del CSV):
  Fecha | Cod_destino | Destino | Persona Humana/Jurídica | Aportante |
  Cuil/Cuit | Distrito | Agrupacion | Modalidad | Recurrente | Monto |
  Banco Origen | Rectificado | Anulado | Observación

Diseño (ver sql/financiamiento.sql):
- Guardamos el CUIT tal cual + normalizado (solo dígitos) para el JOIN con RIGI.
- Derivamos `anio` del texto de Destino (ej. "...2019–2022" -> 2019).
- Por defecto SALTAMOS los aportes Anulado=True (no cuentan); se pueden incluir
  con --incluir-anulados si se quiere auditar.
- Reemplazo completo por defecto (--reset): borra y recarga, porque la fuente es
  un snapshot completo y no incremental.

Uso:
  python ingesta_aportes_cne.py            # descarga + carga (reset)
  python ingesta_aportes_cne.py --archivo aportes.csv   # usa CSV local ya bajado
  python ingesta_aportes_cne.py --incluir-anulados
"""
import argparse
import csv
import io
import os
import re
import sys
import time

import requests

CSV_URL = "https://aportantes.electoral.gob.ar/aportes/descargar-csv/"
FUENTE_URL = "https://aportantes.electoral.gob.ar/aportes/"
FUENTE_NOMBRE = "Cámara Nacional Electoral — Consulta de Aportes Declarados"
UA = {"User-Agent": "Mozilla/5.0 (TransparenciaAR; ingesta de datos abiertos)"}


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

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def parse_fecha(texto):
    """'6 de Julio de 2019' -> '2019-07-06'. Devuelve None si no matchea."""
    if not texto:
        return None
    m = re.match(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", texto.strip(), re.IGNORECASE)
    if not m:
        return None
    dia, mes_txt, anio = m.groups()
    mes = MESES.get(mes_txt.lower())
    if not mes:
        return None
    return f"{anio}-{mes:02d}-{int(dia):02d}"


def parse_anio_destino(destino):
    """Primer año de 4 dígitos que aparezca en el texto de Destino."""
    if not destino:
        return None
    m = re.search(r"(20\d{2})", destino)
    return int(m.group(1)) if m else None


def norm_cuit(cuit):
    """Solo dígitos; None si queda vacío."""
    d = re.sub(r"\D", "", cuit or "")
    return d or None


def parse_monto(texto):
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        # por si viniera con separador de miles/coma
        limpio = texto.replace(".", "").replace(",", ".")
        try:
            return float(limpio)
        except ValueError:
            return None


def descargar_csv(intentos=4, timeout=180):
    for i in range(intentos):
        try:
            r = requests.get(CSV_URL, headers=UA, timeout=timeout)
            r.raise_for_status()
            return r.content.decode("utf-8-sig")
        except requests.exceptions.RequestException as e:
            if i == intentos - 1:
                raise
            espera = 15 * (i + 1)
            print(f"  intento {i + 1} falló ({type(e).__name__}), reintento en {espera}s...")
            time.sleep(espera)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archivo", help="usar un CSV local ya descargado en vez de bajarlo")
    ap.add_argument("--incluir-anulados", action="store_true",
                    help="incluir aportes con Anulado=True (por defecto se saltan)")
    ap.add_argument("--no-reset", action="store_true",
                    help="no borrar la tabla antes de cargar (por defecto hace reset completo)")
    args = ap.parse_args()

    if args.archivo:
        print(f"-> Leyendo CSV local: {args.archivo}")
        with open(args.archivo, encoding="utf-8-sig") as f:
            texto = f.read()
    else:
        print(f"-> Descargando CSV completo de {CSV_URL} ...")
        texto = descargar_csv()
        print(f"   {len(texto)} bytes")

    lector = csv.DictReader(io.StringIO(texto))
    filas = []
    saltados_anulados = 0
    for reg in lector:
        anulado = (reg.get("Anulado") or "").strip().lower() == "true"
        if anulado and not args.incluir_anulados:
            saltados_anulados += 1
            continue
        tipo_raw = (reg.get("Persona Humana/Jurídica") or "").strip()
        tipo = "juridica" if tipo_raw.lower().startswith("jur") else ("humana" if tipo_raw else None)
        destino = (reg.get("Destino") or "").strip()
        filas.append({
            "aportante_nombre": (reg.get("Aportante") or "").strip()[:300] or "(sin nombre)",
            "aportante_cuit": (reg.get("Cuil/Cuit") or "").strip() or None,
            "aportante_cuit_norm": norm_cuit(reg.get("Cuil/Cuit")),
            "aportante_tipo": tipo,
            "monto": parse_monto(reg.get("Monto")),
            "banco_origen": (reg.get("Banco Origen") or "").strip() or None,
            "fecha": parse_fecha(reg.get("Fecha")),
            "recurrencia": (reg.get("Recurrente") or "").strip() or None,
            "destino": destino or None,
            "anio": parse_anio_destino(destino),
            "distrito": (reg.get("Distrito") or "").strip() or None,
            "agrupacion_politica": (reg.get("Agrupacion") or "").strip() or None,
            "fuente_url": FUENTE_URL,
            "fuente_nombre": FUENTE_NOMBRE,
        })

    print(f"   registros a cargar: {len(filas)} (saltados por anulado: {saltados_anulados})")
    if not filas:
        print("Nada para cargar.")
        return

    if not args.no_reset:
        print("-> Reset: borrando aporte_campana previo...")
        rr = requests.delete(
            f"{SUPABASE_URL}/rest/v1/aporte_campana",
            headers={**HEADERS, "Prefer": "return=minimal"},
            params={"id": "gte.0"},
            timeout=120,
        )
        if rr.status_code >= 400:
            print(f"ERROR en reset: {rr.status_code} {rr.text[:300]}")
            sys.exit(1)

    print("-> Insertando en lotes de 500...")
    for i in range(0, len(filas), 500):
        lote = filas[i:i + 500]
        h = dict(HEADERS)
        h["Prefer"] = "return=minimal"
        rr = requests.post(f"{SUPABASE_URL}/rest/v1/aporte_campana", headers=h, json=lote, timeout=180)
        if rr.status_code >= 400:
            print(f"ERROR lote {i}: {rr.status_code} {rr.text[:400]}")
            sys.exit(1)
        print(f"  lote {i}-{i + len(lote)} OK")

    h = dict(HEADERS)
    h["Prefer"] = "return=minimal"
    requests.post(f"{SUPABASE_URL}/rest/v1/fuente_log", headers=h, json=[{
        "url": CSV_URL,
        "workflow": "ingesta_aportes_cne.py",
    }], timeout=60)
    print(f"OK — {len(filas)} aportes cargados.")


if __name__ == "__main__":
    main()
