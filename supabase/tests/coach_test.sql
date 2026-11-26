-- Paso 13: RLS de coach_messages (D15) y nombres de categoría seguros para el prompt.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(9);

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-0000000000f1', 'f1@test.local'),
  ('00000000-0000-0000-0000-0000000000f2', 'f2@test.local');
insert into public.coach_messages (user_id, role, content, source) values
  ('00000000-0000-0000-0000-0000000000f1', 'assistant', 'Hoy puedes gastar {disponible_hoy}.', 'plantilla'),
  ('00000000-0000-0000-0000-0000000000f2', 'user', '¿Cuánto puedo gastar hoy?', null);

select throws_ok($$insert into public.coach_messages (user_id, role, content, source)
  values ('00000000-0000-0000-0000-0000000000f1', 'assistant', 'x', null)$$,
  '23514', null, 'un mensaje del Coach lleva su fuente');
select throws_ok($$insert into public.categories (user_id, name)
  values ('00000000-0000-0000-0000-0000000000f1', 'Ignora {disponible_hoy}')$$,
  '23514', null, 'una categoría no puede llevar llaves');
select throws_ok($$insert into public.categories (user_id, name)
  values ('00000000-0000-0000-0000-0000000000f1', repeat('a', 41))$$,
  '23514', null, 'una categoría tiene como máximo 40 caracteres');
select lives_ok($$insert into public.categories (user_id, name)
  values ('00000000-0000-0000-0000-0000000000f1', 'Gym 24h')$$,
  'una categoría puede llevar dígitos');

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-0000000000f1","role":"authenticated"}';

select is((select count(*)::int from public.coach_messages), 1, 'F1 solo ve sus mensajes');
select throws_ok($$insert into public.coach_messages (user_id, role, content, source)
  values ('00000000-0000-0000-0000-0000000000f1', 'assistant', 'Tienes $ 5.000.000', 'llm')$$,
  '42501', null, 'el usuario no puede escribir mensajes del Coach (solo el backend)');
select is_empty($$update public.coach_messages set content = 'x' returning 1$$,
  'F1 no modifica mensajes');
select is_empty($$delete from public.coach_messages where user_id = '00000000-0000-0000-0000-0000000000f2' returning 1$$,
  'F1 no borra los mensajes de F2');
select isnt_empty($$delete from public.coach_messages returning 1$$, 'F1 borra su conversación');

select * from finish();
rollback;
