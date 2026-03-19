-- Migration 004: Módulo Financeiro
-- Execute no SQL Editor do Supabase APÓS 003_fotos.sql
-- ATENÇÃO: Execute o ALTER TYPE sozinho primeiro (não funciona dentro de transação).

-- 1. Adiciona 'parcial' ao enum de status das faturas
ALTER TYPE status_fatura ADD VALUE IF NOT EXISTS 'parcial';

-- 2. Novas colunas em configuracoes_financeiras
ALTER TABLE public.configuracoes_financeiras
    ADD COLUMN IF NOT EXISTS nome_recebedor TEXT;

-- 3. Novas colunas em faturas
ALTER TABLE public.faturas
    ADD COLUMN IF NOT EXISTS mes_referencia  DATE,
    ADD COLUMN IF NOT EXISTS valor_pago      NUMERIC(10,2) NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS familia_id      UUID;

-- 4. Índices úteis
CREATE INDEX IF NOT EXISTS idx_faturas_mes_referencia  ON public.faturas (professor_id, mes_referencia);
CREATE INDEX IF NOT EXISTS idx_faturas_status          ON public.faturas (professor_id, status);
CREATE INDEX IF NOT EXISTS idx_faturas_familia         ON public.faturas (professor_id, familia_id);

-- 5. Permissões
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.faturas                  TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.configuracoes_financeiras TO authenticated;

-- 6. RLS — faturas
ALTER TABLE public.faturas ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'faturas'
          AND policyname = 'professor acessa suas faturas'
    ) THEN
        CREATE POLICY "professor acessa suas faturas"
            ON public.faturas FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

-- 7. RLS — configuracoes_financeiras
ALTER TABLE public.configuracoes_financeiras ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'configuracoes_financeiras'
          AND policyname = 'professor acessa suas configuracoes'
    ) THEN
        CREATE POLICY "professor acessa suas configuracoes"
            ON public.configuracoes_financeiras FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
