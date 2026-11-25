-- Paso 09B: extracción de movimientos desde los correos guardados.

-- El correo que no se pudo leer con seguridad (sin plantilla, factura sin validar…) queda para revisión.
alter table public.inbound_emails drop constraint inbound_emails_status_check;
alter table public.inbound_emails add constraint inbound_emails_status_check
  check (status in ('pending_extraction', 'extracted', 'pending_review', 'failed'));

alter table public.transactions
  add column payment_method text
    check (payment_method in ('cash', 'credit_card', 'debit_card', 'transfer', 'other')),
  -- CUFE de la factura electrónica que respalda el movimiento (la crea o completa la alerta del banco).
  add column invoice_cufe text check (invoice_cufe ~ '^[0-9a-f]{96}$');

-- La misma factura no respalda dos movimientos del mismo usuario.
create unique index transactions_user_invoice_cufe_key
  on public.transactions (user_id, invoice_cufe) where invoice_cufe is not null;
