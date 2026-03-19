-- Migration 008: Módulo Planejamento
-- Execute no SQL Editor do Supabase APÓS 007_comunicacao.sql

-- Banco de atividades
CREATE TABLE IF NOT EXISTS public.atividades (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    titulo       TEXT NOT NULL,
    descricao    TEXT,
    materia      TEXT,
    serie        TEXT,
    dificuldade  TEXT CHECK (dificuldade IN ('facil', 'medio', 'dificil', '')),
    tags         JSONB DEFAULT '[]'::jsonb,
    criado_em    TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Planos de aula
CREATE TABLE IF NOT EXISTS public.planos_aula (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id     UUID REFERENCES public.alunos(id) ON DELETE SET NULL,
    titulo       TEXT NOT NULL,
    descricao    TEXT,
    materia      TEXT,
    serie        TEXT,
    criado_em    TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

-- Atividades dentro de um plano (junction)
CREATE TABLE IF NOT EXISTS public.planos_atividades (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plano_id     UUID NOT NULL REFERENCES public.planos_aula(id) ON DELETE CASCADE,
    atividade_id UUID NOT NULL REFERENCES public.atividades(id) ON DELETE CASCADE,
    ordem        INT DEFAULT 0,
    UNIQUE(plano_id, atividade_id)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_atividades_professor ON public.atividades(professor_id);
CREATE INDEX IF NOT EXISTS idx_atividades_materia   ON public.atividades(professor_id, materia);
CREATE INDEX IF NOT EXISTS idx_planos_professor     ON public.planos_aula(professor_id);
CREATE INDEX IF NOT EXISTS idx_planos_aluno         ON public.planos_aula(professor_id, aluno_id);

-- RLS
ALTER TABLE public.atividades      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.planos_aula     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.planos_atividades ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='atividades' AND policyname='professor acessa suas atividades') THEN
        CREATE POLICY "professor acessa suas atividades"
            ON public.atividades FOR ALL
            USING (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='planos_aula' AND policyname='professor acessa seus planos') THEN
        CREATE POLICY "professor acessa seus planos"
            ON public.planos_aula FOR ALL
            USING (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='planos_atividades' AND policyname='acesso planos_atividades via plano') THEN
        CREATE POLICY "acesso planos_atividades via plano"
            ON public.planos_atividades FOR ALL
            USING (EXISTS (
                SELECT 1 FROM public.planos_aula p
                WHERE p.id = plano_id AND p.professor_id = auth.uid()
            ));
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.atividades       TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.planos_aula      TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.planos_atividades TO authenticated;

NOTIFY pgrst, 'reload schema';
