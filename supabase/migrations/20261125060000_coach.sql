-- Paso 13: historial del Coach (D15).

-- Las respuestas del Coach se guardan con marcadores ({disponible_hoy}), nunca con cifras como
-- texto fijo. «valores» es la instantánea de los marcadores ya formateados en ese momento, solo
-- para volver a mostrar el mensaje tal como fue; al LLM nunca le llega.
create table public.coach_messages (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references public.profiles (id) on delete cascade,
  role       text not null check (role in ('user', 'assistant')),
  content    text not null check (length(content) between 1 and 1000),
  source     text check (source in ('llm', 'plantilla')),
  valores    jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check ((role = 'assistant') = (source is not null))
);

create index coach_messages_user_created on public.coach_messages (user_id, created_at desc);

alter table public.coach_messages enable row level security;

-- D15 (excepción a D4): solo el backend inserta, con service_role, para que nadie pueda escribir
-- mensajes «del Coach» por PostgREST. El usuario solo lee y borra lo suyo.
create policy coach_messages_select on public.coach_messages for select to authenticated
  using (user_id = (select auth.uid()));
create policy coach_messages_delete on public.coach_messages for delete to authenticated
  using (user_id = (select auth.uid()));

-- Los nombres de categoría van al prompt del Coach como datos: cortos y sin los caracteres que
-- usan los marcadores y los delimitadores.
alter table public.categories
  add constraint categories_name_safe
  check (length(name) between 1 and 40 and name !~ '[{}«»<>\n\r]');
