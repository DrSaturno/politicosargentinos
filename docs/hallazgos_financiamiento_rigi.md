# Hallazgo: financiamiento de campaña vs. beneficiarios del RIGI

_Última actualización: 2026-07-14. Todos los datos con fuente oficial (regla de oro)._

## Qué se cruzó

- **Aportes de campaña declarados**: 79.033 registros descargados de la Cámara
  Nacional Electoral ([aportantes.electoral.gob.ar](https://aportantes.electoral.gob.ar/aportes/)),
  cubriendo campañas 2019, 2021, 2023 y 2025. Cada aporte trae CUIT/CUIL del aportante.
- **Empresas beneficiarias del RIGI**: 10 proyectos (7 aprobados, 3 en evaluación).
  Para 5 se obtuvo el CUIT del Vehículo de Proyecto Único (VPU) desde las
  resoluciones del Ministerio de Economía en el Boletín Oficial:

  | Empresa (VPU) | CUIT | Proyecto | Resolución |
  |---|---|---|---|
  | Rincón Mining PTY LTD | 30-70708643-9 | Rincón (litio, Salta) | Res. 735/2025 |
  | Andes Corporación Minera SA | 30-70952278-3 | Los Azules (cobre, San Juan) | Res. 1553/2025 |
  | VMOS SA | 30-71871335-4 | Vaca Muerta Oleoducto Sur (Río Negro) | adhesión RIGI |
  | Southern Energy SA | 30-71858062-1 | FLNG Golfo San Matías (Río Negro) | Res. 559/2025 |
  | Sidersa SA | 30-61536829-2 | Acería San Nicolás (Bs. As.) | Res. 1028/2025 |

## Resultado del cruce por CUIT

**Cero coincidencias directas.** Ninguna empresa RIGI (ni sus accionistas conocidos:
YPF, Vista, Pampa, Pan American, Techint, Glencore, Barrick, Rio Tinto) aparece
como aportante en las 809 donaciones de personas jurídicas del padrón. La búsqueda
por apellido de dueños/directivos conocidos (Galuccio, Mindlin, Bulgheroni, Rocca,
etc.) tampoco arrojó coincidencias reales (solo homónimos descartados a mano).

## Por qué da vacío (y por qué eso importa)

1. **Los VPU son sociedades nuevas (2024-2025)**, creadas para el RIGI. No existían
   durante la mayoría de las campañas del padrón de aportes.
2. **Las multinacionales no aportan bajo su CUIT** a campañas argentinas.
3. **Desde la Ley 27.504 (2019), las personas jurídicas no pueden aportar a
   campañas nacionales** — solo humanas. Los aportes de empresas que sí existen
   (809) son mayormente PyMEs locales en campañas provinciales.

**Conclusión factual:** con los datos públicos de financiamiento declarado, no se
puede trazar una línea directa "empresa RIGI → aporte → agrupación". La influencia
corporativa sobre el RIGI, de existir, no pasa por el aporte de campaña declarado.

## Dónde podría estar la conexión (trabajo futuro)

El único puente plausible es la capa **persona→empresa**: dueños o directivos de las
empresas RIGI que aporten como personas humanas. Eso requiere datos de composición
societaria (IGJ / inspecciones de personas jurídicas), que no son de acceso masivo.
La tabla `vinculo_persona_empresa` y el segundo `UNION ALL` de la vista
`cruce_aporte_rigi` ya están preparados para ese cruce cuando se consiga esa capa.

## Estado técnico

Pipeline completo y verificado en Supabase:
- `aporte_campana` (79.033) · `empresa_rigi` (10, 5 con CUIT) · vista `cruce_aporte_rigi` (live, 0 filas hoy)
- Scripts: `scripts/ingesta_aportes_cne.py`, `scripts/ingesta_empresas_rigi.py`
- Esquema: `sql/financiamiento.sql`
