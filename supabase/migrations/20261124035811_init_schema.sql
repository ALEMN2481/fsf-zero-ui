-- Paso 05: modelo de datos inicial (D3, D4, D5 en docs/CONTEXT.md).
-- Montos en NUMERIC(14,2), solo COP. Sin saldos derivados: los calcula el motor (Paso 11).

create extension if not exists btree_gist with schema extensions;

-- ---------------------------------------------------------------- profiles
create table public.profiles (
  id           uuid primary key references auth.users (id) on delete cascade,
  display_name text,
  created_at   timestamptz not null default now()
);

create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id) values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------- accounts
create table public.accounts (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  name       text not null,
  kind       text not null check (kind in ('debit', 'credit', 'cash', 'wallet')),
  last4      text check (last4 ~ '^[0-9]{4}$'),
  created_at timestamptz not null default now(),
  unique (id, user_id) -- destino de la FK compuesta desde transactions
);

-- ---------------------------------------------------------------- categories
create table public.categories (
  id      uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (id) on delete cascade, -- null = global
  name    text not null,
  unique nulls not distinct (user_id, name)
);

insert into public.categories (name) values
  ('Alimentos'), ('Transporte'), ('Entretenimiento'), ('Servicios'), ('Salud'), ('Otros');

-- ---------------------------------------------------------------- transactions
create table public.transactions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  account_id  uuid,
  category_id uuid references public.categories (id) on delete set null,
  direction   text not null check (direction in ('expense', 'income')),
  amount      numeric(14, 2) not null check (amount > 0),
  merchant    text,
  occurred_at timestamptz not null,
  source      text not null check (source in ('email', 'manual')),
  source_ref  text,
  status      text not null default 'confirmed' check (status in ('confirmed', 'pending_review')),
  created_at  timestamptz not null default now(),
  -- la cuenta debe ser del mismo usuario
  foreign key (account_id, user_id) references public.accounts (id, user_id) on delete set null (account_id)
);

create unique index transactions_user_source_ref_key
  on public.transactions (user_id, source_ref) where source_ref is not null;
create index transactions_user_occurred_idx
  on public.transactions (user_id, occurred_at desc);

-- ---------------------------------------------------------------- budgets
create table public.budgets (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  period_start date not null,
  period_end   date not null,
  amount       numeric(14, 2) not null check (amount >= 0),
  check (period_end >= period_start),
  exclude using gist (
    user_id with =,
    daterange(period_start, period_end, '[]') with &&
  )
);

-- ---------------------------------------------------------------- pockets
create table public.pockets (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  name          text not null,
  target_amount numeric(14, 2) check (target_amount > 0),
  created_at    timestamptz not null default now(),
  unique (id, user_id)
);

create table public.pocket_movements (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  pocket_id   uuid not null,
  amount      numeric(14, 2) not null check (amount <> 0), -- + apartar, - retirar
  occurred_at timestamptz not null default now(),
  created_at  timestamptz not null default now(),
  foreign key (pocket_id, user_id) references public.pockets (id, user_id) on delete cascade
);

create index pocket_movements_pocket_idx on public.pocket_movements (pocket_id);

-- ---------------------------------------------------------------- RLS
alter table public.profiles         enable row level security;
alter table public.accounts         enable row level security;
alter table public.categories       enable row level security;
alter table public.transactions     enable row level security;
alter table public.budgets          enable row level security;
alter table public.pockets          enable row level security;
alter table public.pocket_movements enable row level security;

-- profiles: se crean por trigger; el usuario solo lee y edita el suyo.
create policy profiles_select on public.profiles for select to authenticated
  using (id = (select auth.uid()));
create policy profiles_update on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

-- categories: leer globales + propias; escribir solo propias.
create policy categories_select on public.categories for select to authenticated
  using (user_id is null or user_id = (select auth.uid()));
create policy categories_insert on public.categories for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy categories_update on public.categories for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy categories_delete on public.categories for delete to authenticated
  using (user_id = (select auth.uid()));

-- transactions: solo filas propias y solo categorías globales o propias.
create policy transactions_select on public.transactions for select to authenticated
  using (user_id = (select auth.uid()));
create policy transactions_insert on public.transactions for insert to authenticated
  with check (
    user_id = (select auth.uid())
    and (category_id is null or exists (
      select 1 from public.categories c
      where c.id = category_id and (c.user_id is null or c.user_id = (select auth.uid()))))
  );
create policy transactions_update on public.transactions for update to authenticated
  using (user_id = (select auth.uid()))
  with check (
    user_id = (select auth.uid())
    and (category_id is null or exists (
      select 1 from public.categories c
      where c.id = category_id and (c.user_id is null or c.user_id = (select auth.uid()))))
  );
create policy transactions_delete on public.transactions for delete to authenticated
  using (user_id = (select auth.uid()));

-- resto: el dueño hace todo sobre sus filas.
create policy accounts_owner on public.accounts for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy budgets_owner on public.budgets for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy pockets_owner on public.pockets for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy pocket_movements_owner on public.pocket_movements for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
