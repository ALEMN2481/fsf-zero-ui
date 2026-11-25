-- Paso 11: columnas del motor y bolsillos que nunca quedan en negativo.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(7);

insert into auth.users (id, email) values ('00000000-0000-0000-0000-0000000000f1', 'f1@test.local');
insert into public.pockets (id, user_id, name) values
  ('00000000-0000-0000-0000-0000000000f2', '00000000-0000-0000-0000-0000000000f1', 'Viaje');

select lives_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source, to_last4)
  values ('00000000-0000-0000-0000-0000000000f1', 'expense', 1, now(), 'email', '9999')$$,
  'una transferencia guarda la cuenta de destino');
select is((select counts_in_budget from public.transactions where user_id = '00000000-0000-0000-0000-0000000000f1'),
  true, 'por defecto el movimiento cuenta en el presupuesto');

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-0000000000f1","role":"authenticated"}';

select lives_ok($$insert into public.pocket_movements (pocket_id, amount)
  values ('00000000-0000-0000-0000-0000000000f2', 50000)$$, 'apartar 50.000');
select lives_ok($$insert into public.pocket_movements (pocket_id, amount)
  values ('00000000-0000-0000-0000-0000000000f2', -50000)$$, 'retirar todo lo apartado');
select throws_ok($$insert into public.pocket_movements (pocket_id, amount)
  values ('00000000-0000-0000-0000-0000000000f2', -0.01)$$,
  '23514', null, 'no se retira más de lo apartado');
select throws_ok($$delete from public.pocket_movements where amount = 50000$$,
  '23514', null, 'borrar un apartado no puede dejar el bolsillo en negativo');

reset role;
-- El borrado en cascada de un usuario lo hace el rol de Auth, sin permisos sobre public.pockets.
select is((select prosecdef from pg_proc where proname = 'check_pocket_balance'), true,
  'el trigger de bolsillos es security definer');

select * from finish();
rollback;
