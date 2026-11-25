-- Paso 12: pantalla «Disponible diario».

-- «No es un gasto mío»: el movimiento se descarta en vez de borrarse (queda registro y un reproceso
-- del correo no lo vuelve a crear, porque su source_ref sigue ocupado). El motor no lo cuenta.
alter table public.transactions drop constraint transactions_status_check;
alter table public.transactions add constraint transactions_status_check
  check (status in ('confirmed', 'pending_review', 'dismissed'));

-- La app escucha sus propios movimientos (RLS) para refrescar la pantalla ante un gasto nuevo.
-- Solo es una señal: las cifras se vuelven a pedir al backend.
alter publication supabase_realtime add table public.transactions;
