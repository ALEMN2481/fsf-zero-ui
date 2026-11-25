-- Paso 09B: columnas de extracción en transactions y estado de revisión en inbound_emails.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(5);

insert into auth.users (id, email) values ('00000000-0000-0000-0000-00000000000c', 'c@test.local');

select lives_ok($$insert into public.inbound_emails (user_id, source, rule, sender_domain, message_hash, status)
  values ('00000000-0000-0000-0000-00000000000c', 'gmail', 'bancolombia', 'x.com', repeat('a', 64), 'pending_review')$$,
  'un correo puede quedar pendiente de revisión');
select lives_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source, source_ref, payment_method, invoice_cufe)
  values ('00000000-0000-0000-0000-00000000000c', 'expense', 45900, now(), 'email', 'cufe:1', 'credit_card', repeat('a', 96))$$,
  'un movimiento guarda medio de pago y CUFE');
select throws_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source, source_ref, invoice_cufe)
  values ('00000000-0000-0000-0000-00000000000c', 'expense', 1, now(), 'email', 'cufe:2', repeat('a', 96))$$,
  '23505', null, 'la misma factura no respalda dos movimientos');
select throws_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source, payment_method)
  values ('00000000-0000-0000-0000-00000000000c', 'expense', 1, now(), 'email', 'bitcoin')$$,
  '23514', null, 'medio de pago fuera de la lista');
select throws_ok($$insert into public.transactions (user_id, direction, amount, occurred_at, source, invoice_cufe)
  values ('00000000-0000-0000-0000-00000000000c', 'expense', 1, now(), 'email', 'abc')$$,
  '23514', null, 'CUFE con formato SHA-384');

select * from finish();
rollback;
