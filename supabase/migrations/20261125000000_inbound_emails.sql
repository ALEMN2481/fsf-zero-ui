-- Paso 08A: correos recibidos (bancos y facturas electrónicas), cifrados y sin extraer todavía.
-- El contenido solo lo escribe y lee la ingesta (service_role, D4); el usuario ve solo metadatos.

create table public.inbound_emails (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.profiles (id) on delete cascade,
  received_at    timestamptz not null default now(),
  source         text not null check (source in ('gmail', 'forward')),
  rule           text not null,  -- regla del filtro que lo aceptó (p. ej. 'bancolombia', 'factura_electronica')
  sender_domain  text not null,
  message_hash   text not null check (message_hash ~ '^[0-9a-f]{64}$'),  -- sha256 del Message-ID
  status         text not null default 'pending_extraction'
                 check (status in ('pending_extraction', 'extracted', 'failed')),
  extracted_at   timestamptz,
  key_version    smallint check (key_version > 0),  -- versión de la clave AES-GCM usada
  raw_encrypted  bytea,                              -- nonce || ciphertext; null tras la retención
  check ((raw_encrypted is null) = (key_version is null)),
  unique (user_id, message_hash)                     -- un mismo correo no se guarda dos veces
);

alter table public.inbound_emails enable row level security;

-- El usuario solo lee metadatos de sus correos: nunca el contenido ni puede escribir.
revoke all on public.inbound_emails from anon, authenticated;
grant select (id, user_id, received_at, source, rule, sender_domain, status, extracted_at)
  on public.inbound_emails to authenticated;
create policy inbound_emails_select on public.inbound_emails for select to authenticated
  using (user_id = auth.uid());

-- Retención: borra el contenido 30 días después de extraído y, como máximo, 90 días después de recibido.
-- Devuelve cuántos correos se vaciaron. La programación periódica queda para los Pasos 15-16.
create function public.purge_inbound_emails() returns integer
language sql security definer set search_path = '' as $$
  with purged as (
    update public.inbound_emails
       set raw_encrypted = null, key_version = null
     where raw_encrypted is not null
       and ((status = 'extracted' and extracted_at < now() - interval '30 days')
            or received_at < now() - interval '90 days')
    returning 1
  )
  select count(*)::integer from purged;
$$;
revoke execute on function public.purge_inbound_emails() from public, anon, authenticated;
