# CLAUDE.md — TransparenciaAR

## Qué es este proyecto
Plataforma de transparencia política argentina: fichas de diputados, senadores, gobernadores y presidente con fotos, sueldos, proyectos presentados, votaciones nominales y adhesión provincial a leyes nacionales (caso testigo: Súper RIGI). Continuación del directorio político interactivo y del dashboard de ley de glaciares.

## Regla de oro
**Ningún dato se publica sin `fuente_url` + `fecha_captura`.** Si un dato no tiene fuente oficial verificable, no entra a la base.

## Stack
- **Ingesta:** n8n en VPS Contabo (Cloudflare Tunnel), workflows cron por fuente.
- **Base de datos:** Supabase (Postgres + Storage bucket `fotos`).
- **Frontend:** Next.js 14 (o HTML vanilla en MVP reutilizando el directorio político existente).
- **Scripts:** Python 3.12 en `scripts/` (fetch de fotos, importadores one-shot).

## Estructura
```
transparencia-ar/
├── CLAUDE.md          ← este archivo
├── SPEC.md            ← especificación completa
├── TASKS.md           ← backlog por fases
├── HOW_TO_START.md    ← arranque rápido
├── schema.sql         ← schema Supabase
└── scripts/
    ├── fetch_fotos.py ← descarga fotos (Wikidata/Commons + fallback oficial)
    └── requirements.txt
```

## Convenciones
- Idioma del código y comentarios: español.
- Slugs: `apellido-nombre` en minúsculas sin tildes (ej: `fernandez-juan-carlos`).
- Fotos: `fotos/{cargo}/{slug}.jpg`, 400px de ancho, JPEG. Manifest CSV con fuente y licencia por imagen.
- Toda tabla con datos de fuente externa lleva columnas `fuente_url`, `fuente_nombre`, `fecha_captura`.
- Cargos válidos: `presidente`, `senador`, `diputado`, `gobernador`, `ministro`, `jefe_gabinete`, `funcionario` (MVP). `intendente` en Fase 3.
- El gabinete (`ministro`/`jefe_gabinete`) tiene alta rotación → revalidar mensualmente contra Boletín Oficial, no asumir que una carga inicial sigue vigente.
- Valores de voto: `afirmativo`, `negativo`, `abstencion`, `ausente`.

## Fuentes oficiales (no usar otras sin agregarlas al SPEC)
- datos.hcdn.gob.ar — diputados, votaciones, proyectos
- senado.gob.ar — senadores, votaciones
- Wikidata/Wikimedia Commons — fotos (con licencia registrada)
- Boletín Oficial / boletines provinciales — sueldos, adhesiones RIGI
- presupuestoabierto.gob.ar — presupuesto
- Oficina Anticorrupción — DDJJ (Fase 2)

## Qué NO hacer
- No inventar datos ni completar huecos "a ojo".
- No usar fotos de medios privados.
- No emitir juicios de valor en fichas: solo datos + fuente.
- No hardcodear API keys: usar `.env`.
