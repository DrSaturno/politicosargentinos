# Políticos Argentinos (TransparenciaAR)

Plataforma pública de transparencia política argentina: ficha de cada diputado,
senador, gobernador, presidente y ministro, con sueldos, proyectos presentados,
votaciones nominales y adhesión provincial a leyes nacionales (caso testigo:
**Súper RIGI**).

**Regla de oro: ningún dato se publica sin fuente oficial verificable**
(`fuente_url` + `fecha_captura` en cada registro).

## Estructura

```
├── scripts/          # ingesta Python (nómina, fotos, votaciones, proyectos, sueldos)
├── web/              # frontend estático (HTML/CSS/JS vanilla contra Supabase REST)
├── n8n/              # workflows de ingesta programada (VPS)
├── sql/              # RLS y mantenimiento
└── scripts/schema.sql# schema de la base (Supabase/Postgres)
```

## Stack

- **Base:** Supabase (Postgres + Storage para fotos)
- **Ingesta:** scripts Python 3.12 + n8n (cron en VPS)
- **Frontend:** HTML/CSS/JS vanilla (MVP), consulta directa a la API REST de
  Supabase con anon key + RLS de solo lectura

## Arranque rápido

1. **Base:** crear proyecto en Supabase, correr `scripts/schema.sql` y luego
   `sql/rls.sql` en el SQL Editor. Crear bucket `fotos` (público).
2. **Credenciales:** `scripts/.env` con `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`.
3. **Datos:**
   ```bash
   cd scripts && pip install -r requirements.txt
   python fetch_nomina_oficial.py --salida personas_congreso.csv
   python unir_csvs.py personas_congreso.csv gobernadores_template.csv gabinete_template.csv --salida personas_completo.csv
   python fetch_fotos.py personas_completo.csv
   python cargar_supabase.py personas_completo.csv --fotos-dir fotos
   python cargar_ley_rigi.py          # leyes RIGI/Súper RIGI + votación + adhesiones
   python cargar_sueldos.py           # dietas con fuente oficial
   python ingesta_proyectos_hcdn.py --desde 2026-01-01
   ```
4. **Frontend:** pegar la anon key en `web/config.js` y servir `web/` como
   estático (Vercel, Cloudflare Pages o cualquier hosting).
5. **Ingesta programada:** importar los workflows de `n8n/` (ver `n8n/README.md`).

## Fuentes oficiales

| Dato | Fuente |
|---|---|
| Nómina y votaciones Diputados | hcdn.gob.ar / votaciones.hcdn.gob.ar / datos.hcdn.gob.ar |
| Nómina y votaciones Senado | senado.gob.ar |
| Proyectos | datos.hcdn.gob.ar (CKAN) |
| Sueldos | recibos oficiales HCDN y Senado |
| Adhesión RIGI | argentina.gob.ar + boletines provinciales |
| Fotos | Wikidata/Wikimedia Commons + fotos oficiales de cámara |

Sin juicios de valor: solo datos con su fuente.
