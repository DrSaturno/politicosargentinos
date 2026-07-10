#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cargar_supabase.py - TransparenciaAR
Carga masiva a Supabase: sube las fotos al bucket 'fotos' (Storage) e
inserta/actualiza (upsert) los datos de personas_completo.csv en la tabla
`persona`, cruzando con fotos/manifest_fotos.csv para citar fuente/licencia
de cada foto.

Requisitos previos (correr en el SQL Editor de Supabase antes de esto):
  ALTER TYPE cargo_t ADD VALUE IF NOT EXISTS 'ministro';
  ALTER TYPE cargo_t ADD VALUE IF NOT EXISTS 'jefe_gabinete';
  ALTER TYPE cargo_t ADD VALUE IF NOT EXISTS 'funcionario';
  ALTER TABLE persona ADD COLUMN IF NOT EXISTS ministerio text;
  ALTER TABLE persona ADD COLUMN IF NOT EXISTS partido text;

Credenciales: NUNCA se piden por linea de comandos ni se hardcodean.
Se leen de un archivo .env en la misma carpeta (o pasado con --env-file):
  SUPABASE_URL=https://xxxxx.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=eyJ...

Uso:
  pip install requests
  python cargar_supabase.py personas_completo.csv --fotos-dir fotos

Es reanudable: usa upsert (on_conflict=slug), asi que se puede correr de
nuevo sin duplicar filas ni volver a subir fotos que ya estan en el bucket
(usa x-upsert para sobreescribir solo si cambio el archivo local).
"""

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

BUCKET = "fotos"
LOTE = 50  # cuantas personas se insertan por request a /rest/v1/persona


def cargar_env(path: Path) -> dict:
    """Parser minimo de .env (KEY=VALUE por linea, sin dependencias extra).
    Usa utf-8-sig porque PowerShell (Out-File -Encoding UTF8) agrega BOM."""
    valores = {}
    if not path.exists():
        return valores
    for linea in path.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def slugify(texto: str) -> str:
    """Mismo criterio que fetch_fotos.py: apellido-nombre sin tildes."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^\w\s-]", "", texto).strip().lower()
    return re.sub(r"[\s_]+", "-", texto)


def none_si_vacio(valor):
    valor = (valor or "").strip()
    return valor if valor else None


def subir_foto(sesion, supabase_url, service_key, cargo, slug, ruta_local):
    """Sube un archivo al bucket 'fotos' en storage/{cargo}/{slug}.jpg.
    Devuelve True si subio OK (o si no habia archivo que subir, no es error)."""
    if not ruta_local.exists():
        return False

    url = f"{supabase_url}/storage/v1/object/{BUCKET}/{cargo}/{slug}.jpg"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "image/jpeg",
        "x-upsert": "true",  # permite re-subir/sobreescribir sin error
    }
    with open(ruta_local, "rb") as f:
        r = sesion.post(url, headers=headers, data=f.read(), timeout=60)
    return r.status_code in (200, 201)


def cargar_manifest(ruta: Path) -> dict:
    """manifest_fotos.csv -> dict clave (nombre_completo, cargo) -> fila."""
    indice = {}
    if not ruta.exists():
        return indice
    with open(ruta, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            clave = (fila["nombre"].strip(), fila["cargo"].strip().lower())
            indice[clave] = fila
    return indice


def main():
    parser = argparse.ArgumentParser(description="Carga masiva de personas y fotos a Supabase.")
    parser.add_argument("csv_entrada", help="personas_completo.csv")
    parser.add_argument("--fotos-dir", default="fotos", help="Carpeta con las fotos descargadas (default: fotos/)")
    parser.add_argument("--env-file", default=".env", help="Archivo .env con SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY")
    parser.add_argument("--solo-datos", action="store_true", help="Saltear la subida de fotos, solo cargar la tabla persona")
    args = parser.parse_args()

    env = cargar_env(Path(args.env_file))
    supabase_url = env.get("SUPABASE_URL", "").rstrip("/")
    service_key = env.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not supabase_url or not service_key:
        sys.exit(
            "Faltan credenciales. Creá un archivo '.env' (en esta carpeta) con:\n"
            "  SUPABASE_URL=https://tu-proyecto.supabase.co\n"
            "  SUPABASE_SERVICE_ROLE_KEY=tu-service-role-key\n"
        )

    fotos_dir = Path(args.fotos_dir)
    manifest = cargar_manifest(fotos_dir / "manifest_fotos.csv")

    with open(args.csv_entrada, newline="", encoding="utf-8") as f:
        personas = list(csv.DictReader(f))

    print(f"Cargando {len(personas)} personas a Supabase ({supabase_url})\n")

    sesion = requests.Session()

    registros = []
    fotos_subidas, fotos_saltadas = 0, 0

    for i, p in enumerate(personas, 1):
        nombre = p.get("nombre", "").strip()
        apellido = p.get("apellido", "").strip()
        cargo = p.get("cargo", "").strip().lower()
        nombre_completo = f"{nombre} {apellido}"
        slug = slugify(f"{apellido} {nombre}")

        if nombre == "VERIFICAR" or not (nombre and apellido and cargo):
            print(f"[{i}/{len(personas)}] saltada (fila incompleta o VERIFICAR): {nombre_completo}")
            continue

        foto_path = None
        foto_fuente_url = foto_licencia = foto_autor = None

        if not args.solo_datos:
            ruta_local = fotos_dir / cargo / f"{slug}.jpg"
            if subir_foto(sesion, supabase_url, service_key, cargo, slug, ruta_local):
                foto_path = f"{cargo}/{slug}.jpg"
                fotos_subidas += 1
            else:
                fotos_saltadas += 1
            time.sleep(0.15)  # amable con la API de Storage

        fila_manifest = manifest.get((nombre_completo, cargo))
        if fila_manifest and fila_manifest.get("metodo") != "sin_foto":
            foto_fuente_url = none_si_vacio(fila_manifest.get("fuente_url"))
            foto_licencia = none_si_vacio(fila_manifest.get("licencia"))
            foto_autor = none_si_vacio(fila_manifest.get("autor"))

        registro = {
            "nombre": nombre,
            "apellido": apellido,
            "slug": slug,
            "cargo": cargo,
            "partido": none_si_vacio(p.get("partido")),
            "bloque": none_si_vacio(p.get("bloque")),
            "provincia": none_si_vacio(p.get("provincia")),
            "mandato_inicio": none_si_vacio(p.get("mandato_inicio")),
            "mandato_fin": none_si_vacio(p.get("mandato_fin")),
            "wikidata_id": none_si_vacio(p.get("wikidata_id")),
            "foto_path": foto_path,
            "foto_fuente_url": foto_fuente_url,
            "foto_licencia": foto_licencia,
            "foto_autor": foto_autor,
            "fuente_url": p.get("fuente_url", "").strip(),
            "fuente_nombre": p.get("fuente_nombre", "").strip(),
        }
        if "ministerio" in p:
            registro["ministerio"] = none_si_vacio(p.get("ministerio"))

        registros.append(registro)
        estado_foto = "foto OK" if foto_path else "sin foto"
        print(f"[{i}/{len(personas)}] {nombre_completo} ({cargo}) - {estado_foto}")

    print(f"\nFotos: {fotos_subidas} subidas, {fotos_saltadas} sin archivo local para subir")
    print(f"Insertando/actualizando {len(registros)} registros en la tabla persona...")

    url_tabla = f"{supabase_url}/rest/v1/persona?on_conflict=slug"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    errores = []
    for inicio in range(0, len(registros), LOTE):
        lote = registros[inicio:inicio + LOTE]
        r = sesion.post(url_tabla, headers=headers, data=json.dumps(lote), timeout=60)
        if r.status_code not in (200, 201, 204):
            errores.append(f"Lote {inicio}-{inicio+len(lote)}: HTTP {r.status_code} - {r.text[:500]}")
            print(f"  ✗ Error en lote {inicio}-{inicio+len(lote)}: {r.status_code}")
        else:
            print(f"  ✓ Lote {inicio}-{inicio+len(lote)} OK ({len(lote)} registros)")

    print(f"\nListo: {len(registros) - len(errores)*LOTE if errores else len(registros)} registros procesados.")
    if errores:
        print(f"\n{len(errores)} lote(s) con error:")
        for e in errores:
            print(f"  - {e}")
        print("\nRevisá el mensaje de error de Postgres arriba (columna, tipo de dato,")
        print("o valor de enum que falte) antes de volver a correr.")


if __name__ == "__main__":
    main()
