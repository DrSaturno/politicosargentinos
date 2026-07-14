-- TransparenciaAR — Esquema de Financiamiento de Campaña + cruce con RIGI
-- Regla de oro: toda tabla con datos externos lleva fuente_url, fuente_nombre, fecha_captura.
--
-- Objetivo: materializar el eje "empresa -> político -> ley" cruzando los aportes
-- declarados de campaña (CNE / aportantes.electoral.gob.ar) con las empresas
-- beneficiarias del RIGI.
--
-- MATIZ LEGAL (define el diseño): la Ley 27.504 (2019) prohíbe que las PERSONAS
-- JURÍDICAS (empresas) aporten a campañas NACIONALES. Solo pueden aportar personas
-- humanas. Por eso el cruce por CUIT cubre tres escenarios, no uno:
--   1. Aportes históricos pre-2019 (empresas sí podían).
--   2. Campañas provinciales (según normativa local).
--   3. El caso más relevante hoy: personas humanas que aportan y ADEMÁS son
--      dueños/directivos de una empresa RIGI (requiere capa de vínculo persona->empresa,
--      tabla vinculo_persona_empresa, a poblar en fase posterior con IGJ/AFIP).
-- Conclusión: guardamos el CUIT normalizado en ambos lados y dejamos el cruce como
-- VISTA, para no "hornear" una interpretación en los datos crudos.

-- ---------------------------------------------------------------------------
-- 1. APORTES DE CAMPAÑA (fuente: aportantes.electoral.gob.ar/aportes, CSV oficial)
-- ---------------------------------------------------------------------------
create table aporte_campana (
  id bigint generated always as identity primary key,
  aportante_nombre text not null,        -- nombre/razón social tal como lo declara la CNE
  aportante_cuit text,                   -- CUIL/CUIT tal como viene (con guiones)
  aportante_cuit_norm text,              -- solo dígitos, para JOIN determinístico (ver trigger)
  aportante_tipo text,                   -- 'humana' / 'juridica' si la fuente lo distingue; si no, null
  monto numeric,                         -- monto declarado en ARS
  moneda text not null default 'ARS',
  banco_origen text,                     -- banco desde el que se hizo el aporte
  fecha date,                            -- fecha del aporte
  recurrencia text,                      -- 'único' / 'recurrente' u otro rótulo de la fuente
  destino text,                          -- campaña/elección de destino (ej: "Elecciones 2021 - Generales")
  anio int,                              -- año electoral, derivado de destino para filtrar rápido
  distrito text,                         -- distrito electoral (ej: "Buenos Aires", "CABA")
  agrupacion_politica text,              -- agrupación/alianza que recibió el aporte
  fuente_url text not null,
  fuente_nombre text not null default 'Cámara Nacional Electoral — Consulta de Aportes Declarados',
  fecha_captura timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 2. EMPRESAS BENEFICIARIAS DEL RIGI (fuente: argentina.gob.ar/economia/rigi)
-- ---------------------------------------------------------------------------
create table empresa_rigi (
  id bigint generated always as identity primary key,
  razon_social text not null,
  cuit text,                             -- tal como se publica (con guiones)
  cuit_norm text,                        -- solo dígitos, para JOIN (ver trigger)
  proyecto_nombre text,                  -- nombre del proyecto de inversión aprobado
  sector text,                           -- minería / energía / hidrocarburos / etc.
  monto_inversion numeric,               -- monto de inversión declarado (USD por lo general)
  moneda_inversion text default 'USD',
  provincia text,                        -- provincia donde se radica la inversión
  fecha_adhesion date,                   -- fecha de aprobación/adhesión al RIGI
  estado text,                           -- aprobado / en evaluación / etc.
  fuente_url text not null,
  fuente_nombre text not null default 'Ministerio de Economía — RIGI',
  fecha_captura timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- 3. VÍNCULO PERSONA/APORTANTE -> EMPRESA (fase posterior: IGJ / AFIP / prensa)
--    Permite conectar un aportante humano con la empresa RIGI de la que es
--    dueño/directivo. Se llena manualmente o con scraping dirigido, con fuente.
-- ---------------------------------------------------------------------------
create table vinculo_persona_empresa (
  id bigint generated always as identity primary key,
  persona_nombre text not null,          -- nombre de la persona humana
  persona_cuit_norm text,                -- CUIT normalizado si se conoce (matchea aporte_campana)
  empresa_rigi_id bigint references empresa_rigi(id),
  rol text,                              -- 'titular' / 'director' / 'accionista' / 'apoderado'
  fuente_url text not null,
  fuente_nombre text not null,
  fecha_captura timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Normalización de CUIT: dejar solo dígitos (quita guiones, espacios, puntos).
-- ---------------------------------------------------------------------------
create or replace function normalizar_cuit() returns trigger as $$
begin
  if TG_TABLE_NAME = 'aporte_campana' then
    new.aportante_cuit_norm := nullif(regexp_replace(coalesce(new.aportante_cuit,''), '\D', '', 'g'), '');
  elsif TG_TABLE_NAME = 'empresa_rigi' then
    new.cuit_norm := nullif(regexp_replace(coalesce(new.cuit,''), '\D', '', 'g'), '');
  end if;
  return new;
end;
$$ language plpgsql;

create trigger trg_norm_cuit_aporte
  before insert or update on aporte_campana
  for each row execute function normalizar_cuit();

create trigger trg_norm_cuit_empresa
  before insert or update on empresa_rigi
  for each row execute function normalizar_cuit();

-- ---------------------------------------------------------------------------
-- VISTA de cruce: aportes cuyo CUIT coincide con una empresa RIGI, ya sea
--   (a) match directo aportante<->empresa, o
--   (b) match vía vínculo persona->empresa.
-- No emite juicio: solo expone la coincidencia con ambas fuentes citadas.
-- ---------------------------------------------------------------------------
create or replace view cruce_aporte_rigi as
-- (a) match directo por CUIT del aportante
select
  'directo'::text            as tipo_cruce,
  a.id                       as aporte_id,
  a.aportante_nombre,
  a.aportante_cuit_norm      as cuit,
  a.monto,
  a.fecha                    as fecha_aporte,
  a.anio,
  a.agrupacion_politica,
  a.distrito,
  e.id                       as empresa_rigi_id,
  e.razon_social             as empresa,
  e.proyecto_nombre,
  e.sector,
  a.fuente_url               as fuente_aporte,
  e.fuente_url               as fuente_rigi
from aporte_campana a
join empresa_rigi e on e.cuit_norm = a.aportante_cuit_norm and e.cuit_norm is not null
union all
-- (b) match vía persona (aportante humano vinculado a la empresa)
select
  'via_persona'::text        as tipo_cruce,
  a.id                       as aporte_id,
  a.aportante_nombre,
  a.aportante_cuit_norm      as cuit,
  a.monto,
  a.fecha                    as fecha_aporte,
  a.anio,
  a.agrupacion_politica,
  a.distrito,
  e.id                       as empresa_rigi_id,
  e.razon_social             as empresa,
  e.proyecto_nombre,
  e.sector,
  a.fuente_url               as fuente_aporte,
  e.fuente_url               as fuente_rigi
from aporte_campana a
join vinculo_persona_empresa v on v.persona_cuit_norm = a.aportante_cuit_norm and v.persona_cuit_norm is not null
join empresa_rigi e on e.id = v.empresa_rigi_id;

-- ---------------------------------------------------------------------------
-- Índices para los JOIN por CUIT y filtros habituales.
-- ---------------------------------------------------------------------------
create index idx_aporte_cuit on aporte_campana(aportante_cuit_norm);
create index idx_aporte_anio on aporte_campana(anio);
create index idx_aporte_agrupacion on aporte_campana(agrupacion_politica);
create index idx_empresa_rigi_cuit on empresa_rigi(cuit_norm);
create index idx_vinculo_cuit on vinculo_persona_empresa(persona_cuit_norm);
