-- Paso 08A: el usuario solo ve metadatos de sus propios correos; nunca el contenido cifrado.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(12);

-- ---------------------------------------------------------------- datos (como postgres)
insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-00000000000a', 'a@test.local'),
  ('00000000-0000-0000-0000-00000000000b', 'b@test.local');

insert into public.inbound_emails (id, user_id, source, rule, sender_domain, message_hash, key_version, raw_encrypted,
                                   status, extracted_at, received_at) values
  ('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-00000000000a', 'gmail', 'bancolombia',
   'notificacionesbancolombia.com', repeat('a', 64), 1, '\x0102', 'pending_extraction', null, now()),
  ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-00000000000b', 'gmail', 'bancolombia',
   'notificacionesbancolombia.com', repeat('b', 64), 1, '\x0304', 'pending_extraction', null, now()),
  -- para la retención: extraído hace 31 días, pendiente hace 91 días y extraído hace 5 días
  ('00000000-0000-0000-0000-0000000000b2', '00000000-0000-0000-0000-00000000000b', 'gmail', 'bancolombia',
   'notificacionesbancolombia.com', repeat('c', 64), 1, '\x05', 'extracted', now() - interval '31 days', now() - interval '32 days'),
  ('00000000-0000-0000-0000-0000000000b3', '00000000-0000-0000-0000-00000000000b', 'gmail', 'bancolombia',
   'notificacionesbancolombia.com', repeat('d', 64), 1, '\x06', 'pending_extraction', null, now() - interval '91 days'),
  ('00000000-0000-0000-0000-0000000000b4', '00000000-0000-0000-0000-00000000000b', 'gmail', 'bancolombia',
   'notificacionesbancolombia.com', repeat('e', 64), 1, '\x07', 'extracted', now() - interval '5 days', now() - interval '6 days');

select throws_ok($$insert into public.inbound_emails (user_id, source, rule, sender_domain, message_hash)
  values ('00000000-0000-0000-0000-00000000000a', 'gmail', 'bancolombia', 'x.com', repeat('a', 64))$$,
  '23505', null, 'el mismo correo no se guarda dos veces para el mismo usuario');
select lives_ok($$insert into public.inbound_emails (user_id, source, rule, sender_domain, message_hash)
  values ('00000000-0000-0000-0000-00000000000b', 'gmail', 'bancolombia', 'x.com', repeat('a', 64))$$,
  'otro usuario sí puede recibir un correo con el mismo Message-ID');
select throws_ok($$insert into public.inbound_emails (user_id, source, rule, sender_domain, message_hash, raw_encrypted)
  values ('00000000-0000-0000-0000-00000000000a', 'gmail', 'bancolombia', 'x.com', repeat('f', 64), '\x01')$$,
  '23514', null, 'no hay contenido cifrado sin versión de clave');

-- ---------------------------------------------------------------- como usuario A
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}';

select is((select count(*)::int from public.inbound_emails), 1, 'A ve solo su correo');
select is_empty($$select 1 from public.inbound_emails where user_id = '00000000-0000-0000-0000-00000000000b'$$,
  'A no ve correos de B');
select lives_ok($$select id, rule, sender_domain, status from public.inbound_emails$$, 'A lee los metadatos');
select throws_ok($$select raw_encrypted from public.inbound_emails$$, '42501', null, 'A no lee el contenido cifrado');
select throws_ok($$select key_version from public.inbound_emails$$, '42501', null, 'A no lee la versión de clave');
select throws_ok($$insert into public.inbound_emails (user_id, source, rule, sender_domain, message_hash)
  values ('00000000-0000-0000-0000-00000000000a', 'gmail', 'x', 'x.com', repeat('9', 64))$$,
  '42501', null, 'A no inserta correos (solo la ingesta)');
select throws_ok($$select public.purge_inbound_emails()$$, '42501', null, 'A no ejecuta la retención');

-- ---------------------------------------------------------------- retención (como postgres)
reset role;
select is(public.purge_inbound_emails(), 2, 'la retención vacía 2 correos (extraído > 30 días y pendiente > 90 días)');
select results_eq(
  $$select id::text from public.inbound_emails where raw_encrypted is not null
      and user_id in ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-00000000000b') order by id$$,
  $$values ('00000000-0000-0000-0000-0000000000a1'), ('00000000-0000-0000-0000-0000000000b1'), ('00000000-0000-0000-0000-0000000000b4')$$,
  'conserva el contenido de los recientes');

select * from finish();
rollback;
