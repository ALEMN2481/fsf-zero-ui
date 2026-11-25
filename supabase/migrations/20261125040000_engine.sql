-- Paso 11: motor financiero GPS (D12).

alter table public.transactions
  -- false: se guarda para el detalle por categoría pero no suma al gasto del presupuesto. Hoy solo
  -- las facturas pagadas en efectivo: ese dinero ya salió con el retiro en cajero, que es gasto.
  add column counts_in_budget boolean not null default true,
  -- Cuenta de destino de una transferencia enviada: si es una cuenta registrada del propio usuario,
  -- es un movimiento entre cuentas propias y no cuenta como gasto (se decide al calcular).
  add column to_last4 text check (to_last4 ~ '^[0-9]{4}$');

update public.transactions set counts_in_budget = false
  where payment_method = 'cash' and invoice_cufe is not null;

-- Un bolsillo nunca queda en negativo: lo apartado es la suma de sus movimientos (D5). El bloqueo
-- de la fila del bolsillo serializa los movimientos simultáneos: el segundo ve al primero al sumar.
create function public.check_pocket_balance()
returns trigger
language plpgsql
-- definer: el borrado en cascada de un usuario lo hace el rol de Auth, que no tiene permiso sobre
-- public.pockets. Solo suma y lanza un error: no expone datos.
security definer
set search_path = ''
as $$
declare
  pid uuid;
begin
  foreach pid in array array_remove(array[
    case when tg_op <> 'INSERT' then old.pocket_id end,
    case when tg_op <> 'DELETE' then new.pocket_id end], null)
  loop
    perform 1 from public.pockets where id = pid for update;
    if (select coalesce(sum(amount), 0) from public.pocket_movements where pocket_id = pid) < 0 then
      raise exception 'el bolsillo quedaría en negativo' using errcode = 'check_violation';
    end if;
  end loop;
  return null;
end;
$$;

create trigger pocket_movements_balance
  after insert or update or delete on public.pocket_movements
  for each row execute function public.check_pocket_balance();
