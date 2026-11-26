-- Paso 14 (ajuste): marca de la pregunta de categoría.
-- Ejecutar: npx supabase test db
begin;
create extension if not exists pgtap with schema extensions;
select plan(2);

select has_column('public', 'transactions', 'category_asked_at', 'transactions tiene category_asked_at');
select col_is_null('public', 'transactions', 'category_asked_at', 'sin pregunta por defecto');

select * from finish();
rollback;
