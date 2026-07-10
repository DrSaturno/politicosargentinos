# SPEC.md — TransparenciaAR (nombre provisorio)

## 1. Visión

Plataforma web pública que expone de forma clara y verificable la actividad de toda la clase política argentina: presidente, senadores, diputados, gobernadores e intendentes. Cada dato publicado **cita su fuente oficial** con link directo.

Es la evolución/continuación de dos proyectos previos:
- Directorio político interactivo (HTML standalone: senadores, diputados, gobernadores con fotos, búsqueda, filtros, badges de partido).
- Dashboard cívico de seguimiento de votos (ley de glaciares).

## 2. Objetivos

1. Que cualquier ciudadano pueda "verle la cara" a cada político y conocer su actividad.
2. Exponer sueldos, dietas y gastos con fuente oficial.
3. Mostrar proyectos presentados y votaciones nominales de diputados y senadores.
4. Para gobernadores: políticas aplicadas por provincia y adhesión a leyes nacionales (caso testigo: **Súper RIGI** — quién votó a favor en el Congreso y qué gobernador adhirió/tranzó en su provincia).
5. Todo dato con **cita de fuente** (link + fecha de captura). Sin fuente, no se publica.

## 3. Alcance MVP (Fase 1)

| Módulo | Incluye | No incluye (fases futuras) |
|---|---|---|
| Directorio | Ficha de cada diputado (257), senador (72), gobernador (24), presidente y gabinete nacional (jefe de Gabinete + ministros). Foto, partido, bloque, provincia/ministerio, mandato. | Intendentes (Fase 3, ~2300 municipios) |
| Sueldos | Dieta/sueldo nominal por cargo con fuente oficial. | Gastos de representación detallados, viáticos |
| Votaciones | Votaciones nominales de Diputados y Senado (afirmativo/negativo/abstención/ausente) por ley destacada. | Histórico completo de todas las votaciones |
| Proyectos | Proyectos presentados por cada legislador (autor/coautor). | Análisis de texto de proyectos |
| Mapa RIGI | Mapa de Argentina coloreado: provincias adheridas / no adheridas / en tratamiento + gobernador responsable. | Proyectos concretos ingresados bajo RIGI por provincia (Fase 2) |
| Fuentes | Toda card de dato muestra ícono de fuente → link oficial. | — |

**Nota sobre el gabinete:** los cargos ministeriales tienen alta rotación (más que legisladores/gobernadores). El registro `persona` para cargo `ministro`/`jefe_gabinete` necesita revalidación mensual contra Boletín Oficial (decretos de designación) — no alcanza con cargarlo una vez. Ver `scripts/gabinete_template.csv` para el criterio de qué queda marcado `VERIFICAR` cuando hay un cambio en curso sin confirmar.

### Fase 2
- Declaraciones juradas patrimoniales (Oficina Anticorrupción): patrimonio al asumir vs. actual.
- Ausentismo por legislador (sesiones asistidas / totales).
- Transfuguismo (cambios de bloque durante el mandato).
- "Cementerio de proyectos" (presentados y nunca tratados).
- Proyectos ingresados bajo RIGI por provincia.

### Fase 3
- Intendentes.
- Score/ranking de desempeño (asistencia + producción legislativa + DDJJ al día).
- Alertas por email/Telegram: "seguí a tu diputado".
- Comparador entre provincias.

## 4. Fuentes de datos (oficiales)

| Dato | Fuente | Formato |
|---|---|---|
| Diputados (nómina, bloque, foto oficial) | datos.hcdn.gob.ar (portal de datos abiertos HCDN) | CSV/JSON |
| Votaciones Diputados | votaciones.hcdn.gob.ar / datos abiertos HCDN | JSON/CSV |
| Senadores (nómina) | senado.gob.ar — listados oficiales | HTML/JSON |
| Votaciones Senado | senado.gob.ar/votaciones | HTML/PDF (requiere scraping) |
| Proyectos de ley | HCDN + Senado datos abiertos | JSON/CSV |
| Sueldos/dietas | Boletín Oficial + resoluciones de cada cámara | PDF/HTML |
| DDJJ patrimoniales | Oficina Anticorrupción (jdjj.gob.ar) | Consulta web |
| Presupuesto provincial | presupuestoabierto.gob.ar | API/CSV |
| Adhesión provincial RIGI | Boletines oficiales provinciales + legislaturas provinciales | HTML/PDF |
| Gabinete nacional (ministros) | Boletín Oficial (decretos de designación) + mapadelestado.dyte.gob.ar/ministerios + Wikipedia (Anexo Gabinete de Ministros, referenciado a decretos) | HTML |
| Fotos | Wikidata/Wikimedia Commons (con licencia) + foto oficial HCDN/Senado como fallback | Ver `scripts/fetch_fotos.py` |

**Regla de citado:** cada registro en la base guarda `fuente_url`, `fuente_nombre` y `fecha_captura`. El front renderiza siempre el link.

## 5. Arquitectura

```
[Fuentes oficiales]
      │  (scraping / APIs / CSV)
      ▼
[n8n en VPS Contabo] ── flujos programados (cron) de ingesta y actualización
      │
      ▼
[Supabase (Postgres)] ── única fuente de verdad + storage de fotos
      │
      ▼
[Frontend Next.js 14] ── SSG/ISR (contenido mayormente estático, se regenera al actualizar datos)
      │
      ▼
[Cloudflare] ── CDN + tunnel (infra ya existente)
```

- **Ingesta:** n8n (ya corriendo en Contabo con Cloudflare Tunnel). Un workflow por fuente. Frecuencia: diaria para votaciones/proyectos, semanal para nómina, mensual para sueldos.
- **Base:** Supabase. Storage bucket `fotos` para imágenes descargadas por el script.
- **Front:** Next.js 14 (mismo stack que JR Comunicaciones). Alternativa low-cost para MVP: HTML/CSS/JS vanilla reutilizando el directorio político existente, migrando a Next en Fase 2.
- **Fotos:** script Python `scripts/fetch_fotos.py` (Wikidata → Commons, fallback foto oficial de cámara). Corre una vez por recambio legislativo o al detectar altas.

## 6. Modelo de datos (Supabase)

Ver `schema.sql`. Tablas principales:

- `persona` — todos los políticos (id, nombre, apellido, slug, foto_path, foto_fuente, cargo, partido, bloque, provincia, mandato_inicio, mandato_fin, wikidata_id)
- `ley` — leyes/proyectos destacados (id, titulo, slug, expediente, camara_origen, estado, resumen, fuente_url)
- `votacion` — evento de votación (id, ley_id, camara, fecha, resultado, fuente_url)
- `voto` — voto individual (votacion_id, persona_id, valor: afirmativo|negativo|abstencion|ausente)
- `proyecto` — proyectos presentados (id, persona_id autor, expediente, titulo, fecha, estado, fuente_url)
- `sueldo` — (cargo, monto_bruto, moneda, periodo, fuente_url, fecha_captura)
- `provincia_adhesion` — (provincia, ley_id, estado: adherida|no_adherida|en_tratamiento, gobernador_id, norma_provincial, fuente_url)
- `fuente_log` — auditoría de capturas (url, fecha, hash del contenido)

## 7. Consideraciones legales

- Solo información pública de fuentes oficiales. Cero opinión editorial en las fichas: los datos hablan solos.
- Cada afirmación linkea la fuente → defensa ante cualquier reclamo por difamación.
- Fotos: priorizar Wikimedia Commons (licencias libres, se guarda autor y licencia en manifest) y fotos oficiales de las cámaras (obra pública del Estado). Nunca fotos de medios privados.
- DDJJ (Fase 2): son públicas por Ley 25.188, pero mostrar solo lo publicado por la OA, sin inferencias.

## 8. Métricas de éxito MVP

- 100% de diputados y senadores con ficha completa (foto + bloque + provincia).
- Votación nominal del Súper RIGI cargada y navegable el día que se vote.
- Mapa de adhesión provincial RIGI operativo.
- Toda card con link a fuente funcional (0 datos sin fuente).
