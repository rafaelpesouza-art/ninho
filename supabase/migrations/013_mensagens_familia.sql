-- Migration 013: Tabela de mensagens para família
-- Nota: descricao e enviado_familia já existem em registros_sessao

CREATE TABLE IF NOT EXISTS public.mensagens_familia (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    registro_id      UUID        NOT NULL REFERENCES public.registros_sessao(id) ON DELETE CASCADE,
    aluno_id         UUID        NOT NULL REFERENCES public.alunos(id) ON DELETE CASCADE,
    texto            TEXT,
    fotos_selecionadas UUID[]    DEFAULT ARRAY[]::uuid[],
    enviado          BOOLEAN     NOT NULL DEFAULT FALSE,
    data_envio       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.mensagens_familia ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'mensagens_familia'
          AND policyname = 'professor acessa suas mensagens familia'
    ) THEN
        CREATE POLICY "professor acessa suas mensagens familia"
            ON public.mensagens_familia FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.mensagens_familia TO authenticated;

NOTIFY pgrst, 'reload schema';
