-- Paso 14: avisos push con FCM (D16).

-- Dispositivos del usuario. Un token es de un solo teléfono: si en ese teléfono entra otra
-- cuenta, el token pasa a la nueva. Solo el backend escribe (service_role, con el user_id del JWT);
-- el usuario solo ve los suyos. El token no es una credencial, pero permite enviar avisos a ese
-- teléfono: no se expone a otros usuarios.
create table public.device_tokens (
  token      text primary key check (length(token) between 1 and 4096),
  user_id    uuid not null references public.profiles (id) on delete cascade,
  platform   text not null default 'android' check (platform in ('android', 'ios')),
  updated_at timestamptz not null default now()
);

create index device_tokens_user on public.device_tokens (user_id);

alter table public.device_tokens enable row level security;

create policy device_tokens_select on public.device_tokens for select to authenticated
  using (user_id = (select auth.uid()));

-- Un aviso por movimiento: el backend lo reclama poniendo notified_at en la misma escritura
-- (where notified_at is null), así un reintento o la factura que completa el movimiento no avisan
-- dos veces. Los movimientos de antes de este paso no avisan.
alter table public.transactions add column notified_at timestamptz;
update public.transactions set notified_at = coalesce(created_at, now());
