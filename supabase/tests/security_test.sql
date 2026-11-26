-- Paso 15: revisión de seguridad de todo el esquema public (RQN 01).
-- Una tabla o función nueva hace fallar esta prueba hasta que se revise su seguridad.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(6);

-- Las tablas revisadas una por una (cada una con su prueba de usuario A contra B).
select is(
  array(select c.relname::text from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind in ('r', 'p') order by c.relname),
  array['accounts', 'budgets', 'categories', 'category_rules', 'coach_messages',
        'device_tokens', 'gmail_connections', 'inbound_emails', 'pocket_movements',
        'pockets', 'profiles', 'transactions'],
  'tablas de public: las revisadas (una nueva exige revisar su RLS)');

select is_empty(
  $$select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity$$,
  'todas las tablas tienen RLS');

select is_empty(
  $$select tablename from pg_policies
    where schemaname = 'public' and roles && array['anon', 'public']::name[]$$,
  'ninguna política para anon ni para public: solo usuarios con sesión');

select is_empty(
  $$select table_name from information_schema.views where table_schema = 'public'$$,
  'sin vistas en public (saltarían la RLS de sus tablas)');

select is_empty(
  $$select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.prosecdef
      and not coalesce(p.proconfig::text[] && array['search_path=""'], false)$$,
  'las funciones security definer fijan search_path vacío');

select is_empty(
  $$select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.prosecdef and p.prorettype <> 'trigger'::regtype
      and (has_function_privilege('anon', p.oid, 'execute')
        or has_function_privilege('authenticated', p.oid, 'execute'))$$,
  'las funciones security definer (que no son de trigger) no las llama el usuario');

select * from finish();
rollback;
