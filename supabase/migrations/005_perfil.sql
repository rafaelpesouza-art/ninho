-- Migration 005: Perfil do Professor
-- Execute no SQL Editor do Supabase APÓS 004_financeiro.sql

CREATE TABLE IF NOT EXISTS public.perfis_professor (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id      UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    nome_completo     TEXT NOT NULL DEFAULT '',
    apelido           TEXT,
    data_nascimento   DATE,
    cpf               TEXT,
    telefone          TEXT,
    email_contato     TEXT,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_perfis_professor_id ON public.perfis_professor (professor_id);

ALTER TABLE public.perfis_professor ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'set_updated_at_perfis_professor'
    ) THEN
        CREATE TRIGGER set_updated_at_perfis_professor
            BEFORE UPDATE ON public.perfis_professor
            FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'perfis_professor' AND policyname = 'professor acessa seu perfil'
    ) THEN
        CREATE POLICY "professor acessa seu perfil"
            ON public.perfis_professor FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.perfis_professor TO authenticated;

NOTIFY pgrst, 'reload schema';
