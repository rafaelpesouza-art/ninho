-- Migration 007: Módulo Comunicação
-- Execute no SQL Editor do Supabase APÓS 006_personalizacao.sql

ALTER TABLE public.relatorios_evolucao
    ADD COLUMN IF NOT EXISTS tipo           TEXT NOT NULL DEFAULT 'relatorio',
    ADD COLUMN IF NOT EXISTS pontos_atencao TEXT,
    ADD COLUMN IF NOT EXISTS resumo         TEXT,
    ADD COLUMN IF NOT EXISTS fotos_selecionadas JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS texto_whatsapp TEXT;

CREATE INDEX IF NOT EXISTS idx_relatorios_tipo
    ON public.relatorios_evolucao (professor_id, tipo, criado_em DESC);

-- Permissões (idempotente)
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.relatorios_evolucao TO authenticated;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'relatorios_evolucao'
          AND policyname = 'professor acessa seus relatorios'
    ) THEN
        CREATE POLICY "professor acessa seus relatorios"
            ON public.relatorios_evolucao FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
