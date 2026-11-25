-- Paso 08B: el usuario ve el estado de su conexión con Gmail, nunca el token.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(6);

insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-00000000000a', 'a@test.local'),
  ('00000000-0000-0000-0000-00000000000b', 'b@test.local');
insert into public.gmail_connections (user_id, gmail_address, key_version, refresh_token_encrypted) values
  ('00000000-0000-0000-0000-00000000000a', 'a@gmail.example', 1, '\x01'),
  ('00000000-0000-0000-0000-00000000000b', 'b@gmail.example', 1, '\x02');

select throws_ok($$insert into public.gmail_connections (user_id, gmail_address, key_version, refresh_token_encrypted)
  values ('00000000-0000-0000-0000-00000000000a', 'otro@gmail.example', 1, '\x03')$$,
  '23505', null, 'una sola conexión por usuario');

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}';

select results_eq($$select status from public.gmail_connections$$, $$values ('active')$$, 'A ve solo su estado');
select throws_ok($$select refresh_token_encrypted from public.gmail_connections$$, '42501', null, 'A no lee el token');
select throws_ok($$select history_id from public.gmail_connections$$, '42501', null, 'A no lee el history_id');
select throws_ok($$update public.gmail_connections set status = 'active'$$, '42501', null, 'A no modifica la conexión');
select throws_ok($$delete from public.gmail_connections$$, '42501', null, 'A no borra la conexión (lo hace el backend)');

select * from finish();
rollback;
