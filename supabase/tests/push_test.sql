-- Paso 14: RLS de device_tokens (D16) y notified_at.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(5);

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-0000000000a7', 'a7@test.local'),
  ('00000000-0000-0000-0000-0000000000a8', 'a8@test.local');
insert into public.device_tokens (token, user_id) values
  ('token-a7', '00000000-0000-0000-0000-0000000000a7'),
  ('token-a8', '00000000-0000-0000-0000-0000000000a8');

select has_column('public', 'transactions', 'notified_at', 'transactions tiene notified_at');

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-0000000000a7","role":"authenticated"}';

select results_eq($$select token from public.device_tokens$$, $$values ('token-a7')$$,
  'A7 solo ve su dispositivo');
select throws_ok($$insert into public.device_tokens (token, user_id)
  values ('robado', '00000000-0000-0000-0000-0000000000a7')$$,
  '42501', null, 'el usuario no escribe tokens: solo el backend');
select is_empty($$update public.device_tokens set user_id = '00000000-0000-0000-0000-0000000000a7'
  where token = 'token-a8' returning 1$$, 'A7 no se apropia del token de A8');
select is_empty($$delete from public.device_tokens returning 1$$, 'el usuario no borra tokens directamente');

select * from finish();
rollback;
