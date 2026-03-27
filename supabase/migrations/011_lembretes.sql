-- ============================================================
-- Migration 011: Sistema de Lembretes de Sessão
-- Execute após 010_clinica.sql
-- ============================================================


-- ============================================================
-- 1. Campo lembrete_enviado na tabela aulas
-- ============================================================

ALTER TABLE public.aulas
    ADD COLUMN IF NOT EXISTS lembrete_enviado BOOLEAN NOT NULL DEFAULT FALSE;


-- ============================================================
-- 2. Tabela config_lembretes (um registro por profissional)
-- ============================================================

CREATE TABLE IF NOT EXISTS public.config_lembretes (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id        UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    nome_profissional   TEXT,
    msg_lembrete        TEXT        NOT NULL DEFAULT
        'Olá, {responsavel}! 👋 Passando para lembrar da sessão de *{nome_aluno}* amanhã ({data}) às *{horario}*. Qualquer dúvida é só chamar! 😊',
    msg_confirmacao     TEXT        NOT NULL DEFAULT
        'Olá, {responsavel}! ✅ Confirmando a sessão de *{nome_aluno}* amanhã ({data}) às *{horario}*. Até lá! 🌟',
    msg_cancelamento    TEXT        NOT NULL DEFAULT
        'Olá, {responsavel}! ⚠️ Precisamos cancelar a sessão de *{nome_aluno}* de {data}. Logo entro em contato para reagendarmos. Obrigada pela compreensão! 💙',
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (professor_id)
);

CREATE INDEX IF NOT EXISTS idx_config_lembretes_professor
    ON public.config_lembretes(professor_id);

ALTER TABLE public.config_lembretes ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'config_lembretes'
          AND policyname = 'professor acessa suas configs de lembrete'
    ) THEN
        CREATE POLICY "professor acessa suas configs de lembrete"
            ON public.config_lembretes FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.config_lembretes TO authenticated;

DROP TRIGGER IF EXISTS set_updated_at_config_lembretes ON public.config_lembretes;
CREATE TRIGGER set_updated_at_config_lembretes
    BEFORE UPDATE ON public.config_lembretes
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================
-- Recarrega schema do PostgREST
-- ============================================================
NOTIFY pgrst, 'reload schema';
