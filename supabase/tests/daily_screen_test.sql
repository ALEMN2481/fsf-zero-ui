-- Paso 12: estado dismissed y publicación de Realtime.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(3);

insert into auth.users (id, email) values ('00000000-0000-0000-0000-0000000000c1', 'c1@test.local');

select lives_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source, status)
  values ('00000000-0000-0000-0000-0000000000c1', 'expense', 1, now(), 'email', 'dismissed')$$,
  'un movimiento puede quedar descartado');
select throws_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source, status)
  values ('00000000-0000-0000-0000-0000000000c1', 'expense', 1, now(), 'email', 'borrado')$$,
  '23514', null, 'estado fuera de la lista');
select ok(exists(select 1 from pg_publication_tables
  where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'transactions'),
  'transactions está publicada en Realtime');

select * from finish();
rollback;
