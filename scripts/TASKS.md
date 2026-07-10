# TASKS.md — TransparenciaAR

## Fase 0 — Infra y datos base
- [ ] Crear proyecto en Supabase y correr `schema.sql`
- [ ] Crear bucket `fotos` en Supabase Storage (público, solo lectura)
- [ ] Configurar `.env` (SUPABASE_URL, SUPABASE_SERVICE_KEY)
- [ ] Importar nómina de diputados desde datos.hcdn.gob.ar → tabla `persona`
- [ ] Importar nómina de senadores desde senado.gob.ar → tabla `persona`
- [ ] Cargar 24 gobernadores + presidente (manual asistido, con fuente)
- [ ] Cargar gabinete nacional: jefe de Gabinete + ministros (`scripts/gabinete_template.csv`, completar los `VERIFICAR` de Interior y Defensa contra Boletín Oficial)
- [ ] Correr `scripts/fetch_fotos.py` → verificar cobertura ≥ 95%
- [ ] Completar fotos faltantes con foto oficial de cámara (fallback del script) o manual
- [ ] Subir fotos + `manifest_fotos.csv` a Supabase Storage

## Fase 1 — MVP funcional
- [ ] Workflow n8n: ingesta diaria de votaciones HCDN (JSON → `votacion` + `voto`)
- [ ] Workflow n8n: scraping votaciones Senado (HTML → `votacion` + `voto`)
- [ ] Workflow n8n: proyectos presentados por legislador → `proyecto`
- [ ] Cargar tabla `sueldo` (dietas actuales por cargo, fuente: resoluciones de cámara / Boletín Oficial)
- [ ] Cargar ley "Súper RIGI" en `ley` + seguimiento en `provincia_adhesion`
- [ ] Front: ficha de persona (foto, cargo, bloque, provincia, sueldo, proyectos, votos)
- [ ] Front: buscador + filtros (cargo, provincia, partido, bloque) — reutilizar directorio existente
- [ ] Front: página de ley → tabla de votos nominales con filtros y export
- [ ] Front: mapa de Argentina (SVG) coloreado por adhesión RIGI, click → gobernador + norma + fuente
- [ ] Componente `<Fuente>`: ícono + link + fecha de captura, presente en toda card
- [ ] Deploy (Vercel o VPS + Cloudflare)

## Fase 2 — Profundidad
- [ ] Ingesta DDJJ Oficina Anticorrupción → patrimonio asumir vs. actual
- [ ] Ausentismo por legislador (asistencias / sesiones)
- [ ] Detector de transfuguismo (histórico de bloque por persona)
- [ ] "Cementerio de proyectos": presentados sin tratamiento > 1 año
- [ ] Proyectos ingresados bajo RIGI por provincia
- [ ] SEO: página estática por persona (`/persona/[slug]`) con metadata

## Fase 3 — Escala y comunidad
- [ ] Intendentes (arrancar por los 40 municipios más grandes)
- [ ] Score de desempeño + ranking compartible en redes
- [ ] Alertas: "seguí a tu diputado" (email/Telegram vía n8n)
- [ ] Comparador entre provincias
- [ ] API pública de solo lectura

## Deuda técnica / riesgos
- Votaciones del Senado no tienen API limpia → scraping frágil, monitorear roturas con alertas n8n
- Recambio legislativo (dic.): workflow de detección de altas/bajas en nómina
- Sueldos se actualizan por resolución → revisar mensualmente
- Gabinete nacional: altísima rotación (varios cambios en 2025-2026) → revisar mensualmente contra Boletín Oficial; hoy Interior y Defensa quedaron `VERIFICAR` en la carga inicial por cambios en curso al momento de armar la nómina
