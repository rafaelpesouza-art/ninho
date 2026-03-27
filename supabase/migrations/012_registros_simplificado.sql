-- ============================================================
-- Migration 012: Simplificação do Registro de Sessão
-- Adiciona proximos_passos (único campo novo — os demais
-- já existem ou ficam no banco sem aparecer no formulário).
-- ============================================================

ALTER TABLE public.registros_sessao
    ADD COLUMN IF NOT EXISTS proximos_passos TEXT;

NOTIFY pgrst, 'reload schema';
