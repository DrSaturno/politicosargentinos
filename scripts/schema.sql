-- TransparenciaAR — Schema Supabase (Postgres)
-- Regla: toda tabla con datos externos lleva fuente_url, fuente_nombre, fecha_captura

create type cargo_t as enum ('presidente','senador','diputado','gobernador','intendente','ministro','jefe_gabinete','funcionario');
-- 'funcionario': secretarías de alto perfil sin rango ministerial (ej: Secretaría General de la Presidencia)
create type voto_t as enum ('afirmativo','negativo','abstencion','ausente');
create type adhesion_t as enum ('adherida','no_adherida','en_tratamiento');

create table persona (
  id bigint generated always as identity primary key,
  nombre text not null,
  apellido text not null,
  slug text not null unique,
  cargo cargo_t not null,
  ministerio text,              -- solo aplica a cargo='ministro' (ej: "Economía")
  partido text,
  bloque text,
  provincia text,
  mandato_inicio date,
  mandato_fin date,
  wikidata_id text,
  foto_path text,              -- ruta en Storage: fotos/{cargo}/{slug}.jpg
  foto_fuente_url text,        -- de dónde salió la foto
  foto_licencia text,          -- ej: CC BY-SA 4.0 / Obra oficial HCDN
  foto_autor text,
  fuente_url text not null,
  fuente_nombre text not null,
  fecha_captura timestamptz not null default now(),
  activo boolean not null default true
);

create table ley (
  id bigint generated always as identity primary key,
  titulo text not null,
  slug text not null unique,
  expediente text,
  camara_origen text,
  estado text,                 -- en_tratamiento / media_sancion / sancionada / rechazada
  resumen text,
  fuente_url text not null,
  fuente_nombre text not null,
  fecha_captura timestamptz not null default now()
);

create table votacion (
  id bigint generated always as identity primary key,
  ley_id bigint not null references ley(id),
  camara text not null,        -- diputados / senado
  fecha date not null,
  resultado text,              -- aprobada / rechazada
  fuente_url text not null,
  fecha_captura timestamptz not null default now()
);

create table voto (
  votacion_id bigint not null references votacion(id),
  persona_id bigint not null references persona(id),
  valor voto_t not null,
  primary key (votacion_id, persona_id)
);

create table proyecto (
  id bigint generated always as identity primary key,
  persona_id bigint not null references persona(id),  -- autor principal
  expediente text not null,
  titulo text not null,
  fecha date,
  estado text,
  coautores bigint[],          -- ids de persona
  fuente_url text not null,
  fecha_captura timestamptz not null default now()
);

create table sueldo (
  id bigint generated always as identity primary key,
  cargo cargo_t not null,
  descripcion text,            -- ej: "dieta bruta mensual"
  monto_bruto numeric not null,
  moneda text not null default 'ARS',
  periodo text not null,       -- ej: "2026-07"
  fuente_url text not null,
  fuente_nombre text not null,
  fecha_captura timestamptz not null default now()
);

create table provincia_adhesion (
  id bigint generated always as identity primary key,
  provincia text not null,
  ley_id bigint not null references ley(id),
  estado adhesion_t not null,
  gobernador_id bigint references persona(id),
  norma_provincial text,       -- ej: "Ley provincial 10.XXX"
  fuente_url text not null,
  fecha_captura timestamptz not null default now(),
  unique (provincia, ley_id)
);

create table fuente_log (
  id bigint generated always as identity primary key,
  url text not null,
  fecha timestamptz not null default now(),
  contenido_hash text,
  workflow text                -- qué flujo n8n hizo la captura
);

create index idx_persona_cargo on persona(cargo);
create index idx_persona_provincia on persona(provincia);
create index idx_voto_persona on voto(persona_id);
create index idx_proyecto_persona on proyecto(persona_id);
