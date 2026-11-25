-- Paso 08B: conexión de cada usuario con su Gmail (D7). El refresh_token se guarda cifrado y solo lo
-- lee el backend (service_role); el usuario ve el estado para saber si debe reconectar.

create table public.gmail_connections (
  user_id                 uuid primary key references public.profiles (id) on delete cascade,
  gmail_address           text not null unique,  -- el aviso de Pub/Sub identifica el buzón por su dirección
  status                  text not null default 'active' check (status in ('active', 'needs_reconnect')),
  key_version             smallint not null check (key_version > 0),
  refresh_token_encrypted bytea not null,        -- nonce || ciphertext (AES-GCM, AAD = user_id)
  history_id              bigint,                -- desde dónde leer novedades de Gmail
  watch_expires_at        timestamptz,
  updated_at              timestamptz not null default now()
);

alter table public.gmail_connections enable row level security;

revoke all on public.gmail_connections from anon, authenticated;
grant select (user_id, gmail_address, status, watch_expires_at, updated_at)
  on public.gmail_connections to authenticated;
create policy gmail_connections_select on public.gmail_connections for select to authenticated
  using (user_id = auth.uid());
