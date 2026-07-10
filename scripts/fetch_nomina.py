#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_nomina.py - TransparenciaAR
Arma la nomina de diputados y senadores combinando:
  - DIPUTADOS: API de datos.hcdn.gob.ar, con fallback automatico a Wikipedia
  - SENADORES: tabla de Wikipedia

El parser de Wikipedia tiene tres defensas contra la estructura de esas tablas:
  1. Elimina spans ocultos (sortkeys) que duplican el texto de los nombres.
  2. Salta filas de subtitulo de seccion (encabezados de provincia o bloque).
  3. Toma el nombre del primer link valido de la fila, descartando provincias.
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

HEADERS = {
    "User-Agent": "TransparenciaAR/0.1 (proyecto de transparencia civica; contacto: admin@crecermas.agency)"
}

HCDN_API = "https://datos.hcdn.gob.ar/api/3/action/datastore_search"
HCDN_RESOURCE_ID = "bed68ccd-81f4-4165-89b5-2b3ff9720cac"
HCDN_DATASET_URL = "https://datos.hcdn.gob.ar/dataset/legisladores"

WIKI_API = "https://es.wikipedia.org/w/api.php"
WIKI_PAGE_SENADORES = "Anexo:Senadores nacionales de Argentina (2025-2027)"
WIKI_PAGE_SENADORES_URL = "https://es.wikipedia.org/wiki/Anexo:Senadores_nacionales_de_Argentina_(2025-2027)"
WIKI_PAGE_DIPUTADOS = "Anexo:Diputados nacionales de Argentina (2025-2027)"
WIKI_PAGE_DIPUTADOS_URL = "https://es.wikipedia.org/wiki/Anexo:Diputados_nacionales_de_Argentina_(2025-2027)"

PROVINCIAS = {
    "buenos aires", "ciudad de buenos aires", "caba", "ciudad autonoma de buenos aires",
    "catamarca", "chaco", "chubut", "cordoba", "corrientes", "entre rios", "formosa",
    "jujuy", "la pampa", "la rioja", "mendoza", "misiones", "neuquen", "rio negro",
    "salta", "san juan", "san luis", "santa cruz", "santa fe", "santiago del estero",
    "tierra del fuego", "tucuman", "argentina",
}

NO_PERSONA = {
    "en el cargo", "vicepresidencia", "presidencia", "sin bloque",
}


def normalizar(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii").lower().strip()


def buscar_campo(record, candidatos):
    claves_norm = {normalizar(k): k for k in record.keys()}
    for cand in candidatos:
        for k_norm, k_orig in claves_norm.items():
            if cand in k_norm:
                return str(record[k_orig] or "").strip()
    return ""


def obtener_diputados(sesion, timeout=60, reintentos=3):
    personas, errores = [], []
    print("-> Consultando API de datos.hcdn.gob.ar (diputados)...")

    for intento in range(1, reintentos + 1):
        try:
            offset, limite, total = 0, 100, None
            registros_crudos = []
            while total is None or offset < total:
                params = {"resource_id": HCDN_RESOURCE_ID, "limit": limite, "offset": offset}
                r = sesion.get(HCDN_API, params=params, timeout=timeout)
                r.raise_for_status()
                data = r.json()
                if not data.get("success"):
                    errores.append("La API respondio success=false: " + str(data))
                    return personas, errores
                resultado = data["result"]
                total = resultado.get("total", 0)
                registros_crudos.extend(resultado.get("records", []))
                offset += limite

            if not registros_crudos:
                errores.append("No se obtuvieron registros. Verificar resource_id en " + HCDN_DATASET_URL)
                return personas, errores

            print("  Campos crudos detectados: " + str(list(registros_crudos[0].keys())))

            for reg in registros_crudos:
                nombre_completo = buscar_campo(reg, ["nombre"])
                apellido = buscar_campo(reg, ["apellido"])
                provincia = buscar_campo(reg, ["distrito", "provincia"])
                bloque = buscar_campo(reg, ["bloque"])
                mandato = buscar_campo(reg, ["mandato", "periodo"])

                if nombre_completo and not apellido:
                    partes = nombre_completo.rsplit(" ", 1)
                    if len(partes) == 2:
                        nombre_completo, apellido = partes[0], partes[1]

                if not (nombre_completo and apellido):
                    errores.append("No se pudo extraer nombre/apellido de: " + str(reg))
                    continue

                personas.append({
                    "nombre": nombre_completo.title(),
                    "apellido": apellido.title(),
                    "cargo": "diputado",
                    "provincia": provincia.title(),
                    "bloque": bloque,
                    "mandato": mandato,
                    "foto_url": "",
                    "wikidata_id": "",
                    "fuente_url": HCDN_DATASET_URL,
                    "fuente_nombre": "Datos Abiertos - H. Camara de Diputados de la Nacion",
                })
            return personas, errores

        except requests.RequestException as e:
            if intento < reintentos:
                print("  Intento " + str(intento) + "/" + str(reintentos) + " fallo, reintentando en 5s...")
                time.sleep(5)
            else:
                errores.append("Error de red con la API de HCDN tras " + str(reintentos) + " intentos: " + str(e))

    return personas, errores


def obtener_de_wikipedia(sesion, page, page_url, cargo, minimo_esperado):
    from bs4 import BeautifulSoup

    personas, errores = [], []
    print("-> Consultando Wikipedia (" + cargo + "s)...")

    try:
        params = {"action": "parse", "page": page, "format": "json", "prop": "text"}
        r = sesion.get(WIKI_API, params=params, timeout=30)
        r.raise_for_status()
        data = json.loads(r.content.decode("utf-8"))
        if "error" in data:
            errores.append("Wikipedia no encontro la pagina '" + page + "': " + str(data["error"]))
            return personas, errores

        html = data["parse"]["text"]["*"]
        soup = BeautifulSoup(html, "lxml")

        # DEFENSA 1: eliminar elementos ocultos (sortkeys que duplican nombres)
        for el in soup.select('[style*="display:none"]'):
            el.decompose()
        for el in soup.select("span.sortkey"):
            el.decompose()

        tablas = soup.find_all("table", class_="wikitable")
        if not tablas:
            errores.append("No se encontraron tablas wikitable en " + page)
            return personas, errores

        for tabla in tablas:
            filas = tabla.find_all("tr")
            if not filas:
                continue
            encabezado = " ".join(c.get_text(strip=True).lower() for c in filas[0].find_all(["th", "td"]))
            tiene_distrito = "distrito" in encabezado or "provincia" in encabezado
            tiene_mandato = "mandato" in encabezado or "periodo" in encabezado
            if not (tiene_distrito and tiene_mandato):
                continue

            for fila in filas[1:]:
                celdas_tags = fila.find_all(["td", "th"])
                # DEFENSA 2: saltar filas de subtitulo de seccion
                if any(t.name == "th" for t in celdas_tags):
                    continue
                if any(t.has_attr("colspan") for t in celdas_tags):
                    continue

                # DEFENSA 3: nombre = primer link con texto valido, no-provincia
                nombre_persona = None
                for a in fila.find_all("a"):
                    txt = a.get_text(strip=True)
                    if not txt or len(txt) < 4 or re.search(r"\d", txt):
                        continue
                    if "(" in txt or ":" in txt:
                        continue
                    palabras = txt.split()
                    if not (2 <= len(palabras) <= 5):
                        continue
                    txt_norm = normalizar(txt)
                    if txt_norm in PROVINCIAS or txt_norm in NO_PERSONA:
                        continue
                    nombre_persona = txt
                    break

                if not nombre_persona:
                    continue

                if "," in nombre_persona:
                    apellido, nombre = [p.strip() for p in nombre_persona.split(",", 1)]
                else:
                    partes = nombre_persona.split(" ")
                    nombre, apellido = partes[0], " ".join(partes[1:])

                personas.append({
                    "nombre": nombre,
                    "apellido": apellido,
                    "cargo": cargo,
                    "provincia": "",
                    "bloque": "",
                    "mandato": "",
                    "foto_url": "",
                    "wikidata_id": "",
                    "fuente_url": page_url,
                    "fuente_nombre": "Wikipedia - " + page,
                })

        # Dedup por nombre normalizado (las tablas repiten personas en varias vistas)
        vistos = set()
        unicos = []
        for p in personas:
            clave = normalizar(p["nombre"] + " " + p["apellido"])
            if clave not in vistos:
                vistos.add(clave)
                unicos.append(p)
        personas = unicos

        if len(personas) < minimo_esperado:
            errores.append("Solo se extrajeron " + str(len(personas)) + " " + cargo + "s (se esperan ~" + str(minimo_esperado) + "). Revisar: " + page_url)

    except requests.RequestException as e:
        errores.append("Error de red consultando Wikipedia: " + str(e))
    except ImportError:
        errores.append("Falta beautifulsoup4/lxml. Correr: pip install beautifulsoup4 lxml")

    return personas, errores


def main():
    parser = argparse.ArgumentParser(description="Arma la nomina de diputados y senadores.")
    parser.add_argument("--solo", choices=["diputados", "senadores"], help="Traer solo un cargo")
    parser.add_argument("--salida", default="personas_completo.csv", help="CSV de salida")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout en segundos por request a HCDN")
    parser.add_argument("--reintentos", type=int, default=3, help="Reintentos ante error de red con HCDN")
    args = parser.parse_args()

    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    todas_personas, todos_errores = [], []

    if args.solo in (None, "diputados"):
        p, e = obtener_diputados(sesion, timeout=args.timeout, reintentos=args.reintentos)
        if not p:
            print("  La API de HCDN no respondio - usando Wikipedia como fallback para diputados...")
            p, e_fallback = obtener_de_wikipedia(sesion, WIKI_PAGE_DIPUTADOS, WIKI_PAGE_DIPUTADOS_URL, "diputado", 200)
            e = e + e_fallback
        todas_personas += p
        todos_errores += e
        print("  Diputados obtenidos: " + str(len(p)))

    if args.solo in (None, "senadores"):
        p, e = obtener_de_wikipedia(sesion, WIKI_PAGE_SENADORES, WIKI_PAGE_SENADORES_URL, "senador", 60)
        todas_personas += p
        todos_errores += e
        print("  Senadores obtenidos: " + str(len(p)))

    salida = Path(args.salida)
    campos = ["nombre", "apellido", "cargo", "provincia", "bloque", "mandato",
              "foto_url", "wikidata_id", "fuente_url", "fuente_nombre"]
    with open(salida, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(todas_personas)

    print("CSV generado: " + str(salida) + " (" + str(len(todas_personas)) + " personas)")

    if todos_errores:
        errores_path = salida.with_name(salida.stem + "_errores.txt")
        with open(errores_path, "w", encoding="utf-8") as f:
            f.write("\n".join(todos_errores))
        print("Hubo " + str(len(todos_errores)) + " advertencias/errores - revisar: " + str(errores_path))
        for e in todos_errores[:5]:
            print("  - " + e)


if __name__ == "__main__":
    main()
