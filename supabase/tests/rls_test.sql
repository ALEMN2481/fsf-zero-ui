-- Paso 05: el usuario A no lee, no escribe y no enlaza datos del usuario B.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(27);

-- ---------------------------------------------------------------- datos (como postgres)
insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-00000000000a', 'a@test.local'),
  ('00000000-0000-0000-0000-00000000000b', 'b@test.local');

insert into public.accounts (id, user_id, name, kind) values
  ('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-00000000000a', 'Débito A', 'debit'),
  ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-00000000000b', 'Débito B', 'debit');
insert into public.categories (id, user_id, name) values
  ('00000000-0000-0000-0000-0000000000b2', '00000000-0000-0000-0000-00000000000b', 'Privada B');
insert into public.transactions (id, user_id, account_id, direction, amount, occurred_at, source) values
  ('00000000-0000-0000-0000-0000000000b3', '00000000-0000-0000-0000-00000000000b',
   '00000000-0000-0000-0000-0000000000b1', 'expense', 50000.00, now(), 'manual');
insert into public.budgets (user_id, period_start, period_end, amount) values
  ('00000000-0000-0000-0000-00000000000b', '2026-11-01', '2026-11-30', 1000000.00);
insert into public.pockets (id, user_id, name) values
  ('00000000-0000-0000-0000-0000000000b5', '00000000-0000-0000-0000-00000000000b', 'Viaje B');
insert into public.pocket_movements (user_id, pocket_id, amount) values
  ('00000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-0000000000b5', 20000.00);

select is((select count(*)::int from public.profiles), 2, 'el trigger crea un profile por usuario');

-- ---------------------------------------------------------------- como usuario A
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}';

-- Lectura
select is_empty($$select 1 from public.profiles where id = '00000000-0000-0000-0000-00000000000b'$$, 'A no ve el profile de B');
select is_empty($$select 1 from public.accounts where user_id = '00000000-0000-0000-0000-00000000000b'$$, 'A no ve cuentas de B');
select is_empty($$select 1 from public.categories where user_id = '00000000-0000-0000-0000-00000000000b'$$, 'A no ve categorías privadas de B');
select is_empty($$select 1 from public.transactions where user_id = '00000000-0000-0000-0000-00000000000b'$$, 'A no ve transacciones de B');
select is_empty($$select 1 from public.budgets where user_id = '00000000-0000-0000-0000-00000000000b'$$, 'A no ve presupuestos de B');
select is_empty($$select 1 from public.pockets where user_id = '00000000-0000-0000-0000-00000000000b'$$, 'A no ve bolsillos de B');
select is_empty($$select 1 from public.pocket_movements where user_id = '00000000-0000-0000-0000-00000000000b'$$, 'A no ve movimientos de bolsillo de B');
select isnt_empty($$select 1 from public.categories where user_id is null$$, 'A ve las categorías globales');

-- Escritura sobre filas de B (no afecta nada; se comprueba abajo como postgres)
select lives_ok($$update public.transactions set amount = 1 where id = '00000000-0000-0000-0000-0000000000b3'$$, 'update de A sobre B no falla pero no afecta filas');
select lives_ok($$delete from public.accounts where id = '00000000-0000-0000-0000-0000000000b1'$$, 'delete de A sobre B no falla pero no afecta filas');
select throws_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source)
  values ('00000000-0000-0000-0000-00000000000b', 'expense', 10, now(), 'manual')$$,
  '42501', null, 'A no inserta filas a nombre de B');
select throws_ok($$insert into public.categories (user_id, name) values (null, 'Global falsa')$$,
  '42501', null, 'A no crea categorías globales');

-- Enlaces a datos de B
select throws_ok($$insert into public.transactions (account_id, direction, amount, occurred_at, source)
  values ('00000000-0000-0000-0000-0000000000b1', 'expense', 10, now(), 'manual')$$,
  '23503', null, 'A no enlaza la cuenta de B (FK compuesta)');
select throws_ok($$insert into public.transactions (category_id, direction, amount, occurred_at, source)
  values ('00000000-0000-0000-0000-0000000000b2', 'expense', 10, now(), 'manual')$$,
  '42501', null, 'A no usa la categoría privada de B al insertar');
select throws_ok($$insert into public.pocket_movements (pocket_id, amount)
  values ('00000000-0000-0000-0000-0000000000b5', 100)$$,
  '23503', null, 'A no mueve dinero al bolsillo de B (FK compuesta)');

-- Operaciones válidas de A
select lives_ok($$insert into public.transactions (id, account_id, category_id, direction, amount, occurred_at, source, source_ref)
  values ('00000000-0000-0000-0000-0000000000a3', '00000000-0000-0000-0000-0000000000a1',
          (select id from public.categories where user_id is null and name = 'Alimentos'),
          'expense', 12500.50, now(), 'email', 'msg-1')$$,
  'A inserta con su cuenta y una categoría global');
select throws_ok($$update public.transactions set category_id = '00000000-0000-0000-0000-0000000000b2'
  where id = '00000000-0000-0000-0000-0000000000a3'$$,
  '42501', null, 'A no asigna la categoría privada de B al actualizar');

-- Restricciones
select throws_ok($$insert into public.transactions (direction, amount, occurred_at, source, source_ref)
  values ('expense', 1, now(), 'email', 'msg-1')$$,
  '23505', null, 'source_ref no se repite por usuario');
select throws_ok($$insert into public.accounts (name, kind, last4) values ('X', 'debit', '12a4')$$,
  '23514', null, 'CHECK last4');
select throws_ok($$insert into public.accounts (name, kind) values ('X', 'crypto')$$,
  '23514', null, 'CHECK kind');
select throws_ok($$insert into public.transactions (direction, amount, occurred_at, source)
  values ('refund', 1, now(), 'manual')$$,
  '23514', null, 'CHECK direction');
select lives_ok($$insert into public.budgets (period_start, period_end, amount) values ('2026-11-01', '2026-11-30', 800000)$$,
  'A crea su presupuesto aunque B tenga uno en las mismas fechas');
select throws_ok($$insert into public.budgets (period_start, period_end, amount) values ('2026-11-15', '2026-12-15', 1)$$,
  '23P01', null, 'no se solapan periodos de presupuesto del mismo usuario');

-- ---------------------------------------------------------------- de vuelta como postgres
reset role;

select is((select amount from public.transactions where id = '00000000-0000-0000-0000-0000000000b3'),
  50000.00::numeric, 'la transacción de B sigue intacta');
select isnt_empty($$select 1 from public.accounts where id = '00000000-0000-0000-0000-0000000000b1'$$,
  'la cuenta de B sigue existiendo');
select throws_ok($$insert into public.categories (user_id, name) values (null, 'Alimentos')$$,
  '23505', null, 'no se duplica una categoría global (NULLS NOT DISTINCT)');

select * from finish();
rollback;
