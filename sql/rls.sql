-- TransparenciaAR — RLS: lectura pública, escritura solo service_role
-- Correr en el SQL Editor de Supabase.
-- Con RLS habilitado y solo políticas SELECT, la anon key puede leer pero no
-- escribir. El service_role (scripts de ingesta / n8n) bypasea RLS.

alter table persona            enable row level security;
alter table ley                enable row level security;
alter table votacion           enable row level security;
alter table voto               enable row level security;
alter table proyecto           enable row level security;
alter table sueldo             enable row level security;
alter table provincia_adhesion enable row level security;
alter table fuente_log         enable row level security;

create policy "lectura publica" on persona            for select using (true);
create policy "lectura publica" on ley                for select using (true);
create policy "lectura publica" on votacion           for select using (true);
create policy "lectura publica" on voto               for select using (true);
create policy "lectura publica" on proyecto           for select using (true);
create policy "lectura publica" on sueldo             for select using (true);
create policy "lectura publica" on provincia_adhesion for select using (true);
-- fuente_log es auditoría interna: sin política de lectura (solo service_role)
