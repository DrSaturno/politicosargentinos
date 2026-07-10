# HOW_TO_START.md — TransparenciaAR

## 1. Base de datos
1. Crear proyecto en Supabase.
2. Correr `schema.sql` en el SQL Editor.
3. Crear bucket `fotos` en Storage (público de solo lectura).

## 2. Fotos (script masivo)
```bash
cd scripts
pip install -r requirements.txt
python fetch_fotos.py personas_ejemplo.csv          # prueba con 4 personas
python fetch_fotos.py personas_completo.csv         # corrida real
```
- `personas_completo.csv` se genera desde la nómina de datos.hcdn.gob.ar (diputados)
  y senado.gob.ar (senadores). Si el dataset trae URL de foto oficial, agregarla
  en la columna `foto_url` como fallback.
- Salida: `fotos/{cargo}/{slug}.jpg` + `manifest_fotos.csv` con fuente, licencia
  y autor de CADA imagen (esto es lo que después se muestra en el front como cita).
- Subir la carpeta `fotos/` al bucket de Supabase y el manifest a la tabla `persona`
  (columnas foto_path, foto_fuente_url, foto_licencia, foto_autor).

## 3. Ingesta con n8n
Un workflow por fuente (ver SPEC.md sección 4 y 5). Arrancar por:
1. Nómina diputados (semanal)
2. Votaciones diputados (diaria)
3. Votaciones senado (diaria, scraping)

## 4. Front
MVP: reutilizar el directorio político HTML existente apuntando a Supabase.
Fase 2: migrar a Next.js 14 con ISR.

## 5. Caso testigo: Súper RIGI
1. Cargar la ley en tabla `ley`.
2. El día de la votación: correr ingesta de votos nominales → página de la ley.
3. Ir cargando `provincia_adhesion` a medida que las legislaturas provinciales adhieran
   (fuente: boletín oficial provincial, siempre con link).

## 6. Nómina completa (diputados, senadores, gobernadores)

Nuevo script: `scripts/fetch_nomina.py`

```powershell
cd scripts
pip install requests beautifulsoup4 lxml

# Diputados (API oficial CKAN de datos.hcdn.gob.ar) + Senadores (Wikipedia)
python -u fetch_nomina.py --salida personas_congreso.csv
```

Esto genera `personas_congreso.csv` con diputados y senadores, cada fila con
su `fuente_url` y `fuente_nombre`. También genera `personas_congreso_errores.txt`
si algo no se pudo mapear — revisarlo antes de dar por buena la nómina.

**Importante:** la nómina de diputados sale de una API real que puede cambiar
de estructura con el tiempo. El script imprime en pantalla los campos crudos
que detectó en el primer registro — si algo no cierra (provincia vacía, bloque
vacío, etc.) avisame con ese output y ajusto el mapeo de campos.

Para **gobernadores**, no vale la pena scrapear (son 24): usar
`scripts/gobernadores_template.csv`, que ya trae ~12 confirmados con fuente
(Wikipedia - Anexo Gobernadores de Argentina) y el resto marcado `VERIFICAR`
para completar contra esa misma fuente antes de cargar a Supabase.

Una vez que tengas `personas_congreso.csv` + `gobernadores_template.csv`
completo, uní todo en un solo `personas_completo.csv` (mismas columnas) y
corré `fetch_fotos.py` sobre ese archivo para bajar las ~350 fotos.
