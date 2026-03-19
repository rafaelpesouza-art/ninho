-- Migration 002: Módulo de Agenda
-- Execute no SQL Editor do Supabase APÓS 001_alunos_extra_cols.sql

-- Novos valores no enum de status
ALTER TYPE status_aula ADD VALUE IF NOT EXISTS 'cancelada_aluno';
ALTER TYPE status_aula ADD VALUE IF NOT EXISTS 'cancelada_professor';

-- Colunas extras na tabela aulas
ALTER TABLE aulas
    ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT,
    ADD COLUMN IF NOT EXISTS aula_origem_id      UUID REFERENCES aulas(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_aulas_origem ON aulas(aula_origem_id);

-- Tabela de feriados por professor
CREATE TABLE IF NOT EXISTS feriados (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    data            DATE NOT NULL,
    nome            TEXT NOT NULL,
    recorrente      BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE = repete todo ano
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_feriados_professor ON feriados(professor_id);
CREATE INDEX IF NOT EXISTS idx_feriados_data      ON feriados(professor_id, data);

ALTER TABLE feriados ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'feriados'
          AND policyname = 'professor gerencia seus feriados'
    ) THEN
        CREATE POLICY "professor gerencia seus feriados"
            ON feriados FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.feriados TO anon, authenticated;

NOTIFY pgrst, 'reload schema';
