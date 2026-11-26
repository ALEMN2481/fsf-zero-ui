-- Paso 14 (ajuste, D16): preguntar la categoría cuando ni las reglas ni el LLM la saben.
-- category_asked_at: cuándo el backend avisó «¿En qué categoría va este gasto?». La app abre sola la
-- hoja de categorías mientras siga en Otros por descarte (category_source = 'otros'); al elegir, la
-- categoría pasa a 'usuario' y la pregunta desaparece. Una pregunta por movimiento: el backend la
-- reclama en la misma escritura (category_asked_at is null).
alter table public.transactions add column category_asked_at timestamptz;
