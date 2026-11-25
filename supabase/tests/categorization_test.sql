-- Paso 10: categoría Ingresos, category_source y RLS de category_rules.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(9);

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-0000000000d1', 'd1@test.local'),
  ('00000000-0000-0000-0000-0000000000d2', 'd2@test.local');
insert into public.categories (id, user_id, name) values
  ('00000000-0000-0000-0000-0000000000e2', '00000000-0000-0000-0000-0000000000d2', 'Privada D2');
insert into public.category_rules (user_id, merchant_key, category_id) values
  ('00000000-0000-0000-0000-0000000000d2', 'GIMNASIO X', '00000000-0000-0000-0000-0000000000e2');

select is((select count(*)::int from public.categories where name = 'Ingresos' and user_id is null), 1,
  'existe la categoría global Ingresos');
select throws_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source, category_source)
  values ('00000000-0000-0000-0000-0000000000d1', 'expense', 1, now(), 'email', 'adivinada')$$,
  '23514', null, 'category_source fuera de la lista');

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-0000000000d1","role":"authenticated"}';

select is_empty($$select 1 from public.category_rules$$, 'D1 no ve las reglas de D2');
select lives_ok($$insert into public.category_rules (merchant_key, category_id)
  select 'PANADERIA Y', id from public.categories where name = 'Alimentos' and user_id is null$$,
  'D1 crea una regla hacia una categoría global');
select throws_ok($$insert into public.category_rules (merchant_key, category_id)
  values ('OTRA', '00000000-0000-0000-0000-0000000000e2')$$,
  '42501', null, 'D1 no puede apuntar a una categoría privada de D2');
select throws_ok($$insert into public.category_rules (user_id, merchant_key, category_id)
  select '00000000-0000-0000-0000-0000000000d2', 'INYECTADA', id from public.categories where name = 'Otros' and user_id is null$$,
  '42501', null, 'D1 no crea reglas a nombre de D2');
select is_empty($$update public.category_rules set merchant_key = 'X' where user_id = '00000000-0000-0000-0000-0000000000d2' returning 1$$,
  'D1 no modifica reglas de D2');
select is_empty($$delete from public.category_rules where user_id = '00000000-0000-0000-0000-0000000000d2' returning 1$$,
  'D1 no borra reglas de D2');
select throws_ok($$insert into public.category_rules (merchant_key, category_id)
  select 'PANADERIA Y', id from public.categories where name = 'Otros' and user_id is null$$,
  '23505', null, 'una sola regla por comercio');

select * from finish();
rollback;
