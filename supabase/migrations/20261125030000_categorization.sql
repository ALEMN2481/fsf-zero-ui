-- Paso 10: categorización (D11).

-- Los ingresos (salvo las devoluciones) se categorizan por su dirección, sin reglas ni LLM.
insert into public.categories (name) values ('Ingresos');

-- De dónde salió la categoría. 'pendiente': ninguna regla encajó, está en Otros y el LLM la
-- revisará en segundo plano; el LLM solo escribe si sigue en 'pendiente'.
alter table public.transactions
  add column category_source text check (category_source in
    ('direccion', 'regla_usuario', 'regla', 'pendiente', 'llm', 'otros', 'usuario'));

-- Reglas aprendidas: cuando el usuario corrige la categoría de un movimiento, su comercio
-- (normalizado: mayúsculas, sin tildes, espacios unificados) queda asociado a esa categoría.
create table public.category_rules (
  user_id      uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  merchant_key text not null check (merchant_key <> '' and length(merchant_key) <= 200),
  category_id  uuid not null references public.categories (id) on delete cascade,
  created_at   timestamptz not null default now(),
  primary key (user_id, merchant_key)
);

alter table public.category_rules enable row level security;

-- Solo reglas propias y solo hacia categorías globales o propias (como en transactions).
create policy category_rules_select on public.category_rules for select to authenticated
  using (user_id = (select auth.uid()));
create policy category_rules_insert on public.category_rules for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and exists (select 1 from public.categories c
      where c.id = category_id and (c.user_id is null or c.user_id = (select auth.uid())))
  );
create policy category_rules_update on public.category_rules for update to authenticated
  using (user_id = (select auth.uid()))
  with check (
    user_id = (select auth.uid())
    and exists (select 1 from public.categories c
      where c.id = category_id and (c.user_id is null or c.user_id = (select auth.uid())))
  );
create policy category_rules_delete on public.category_rules for delete to authenticated
  using (user_id = (select auth.uid()));
