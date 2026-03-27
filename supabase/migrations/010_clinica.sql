-- ============================================================
-- Migration 010: Módulo Clínico
-- Anamnese · Avaliação · Devolutiva · Plano de Intervenção ·
-- Documentos · Templates
--
-- Execute no SQL Editor do Supabase APÓS 009_alunos_perfil_academico.sql
-- ⚠️  Após executar, atualize as referências a "registros_aula"
--     no código Flask para "registros_sessao".
-- ============================================================


-- ============================================================
-- 1. ALTER TABLE alunos
-- ============================================================

ALTER TABLE public.alunos
    ADD COLUMN IF NOT EXISTS foto_url   TEXT,
    ADD COLUMN IF NOT EXISTS fase_atual TEXT NOT NULL DEFAULT 'anamnese';

ALTER TABLE public.alunos
    DROP CONSTRAINT IF EXISTS alunos_fase_atual_check;

ALTER TABLE public.alunos
    ADD CONSTRAINT alunos_fase_atual_check
        CHECK (fase_atual IN ('anamnese', 'avaliacao', 'intervencao', 'alta'));

-- Remove colunas substituídas (IF EXISTS — podem não existir em todos os ambientes)
ALTER TABLE public.alunos
    DROP COLUMN IF EXISTS observacoes_pedagogicas,
    DROP COLUMN IF EXISTS materias;


-- ============================================================
-- 2. RENAME registros_aula → registros_sessao + ajustes de colunas
-- ============================================================

-- Só renomeia se ainda não foi renomeada
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'registros_aula'
    ) THEN
        ALTER TABLE public.registros_aula RENAME TO registros_sessao;
    END IF;
END $$;

-- Renomeia observacoes → observacoes_internas (se ainda não foi renomeada)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'registros_sessao'
          AND column_name  = 'observacoes'
    ) THEN
        ALTER TABLE public.registros_sessao
            RENAME COLUMN observacoes TO observacoes_internas;
    END IF;
END $$;

-- Renomeia materia → area_trabalhada (se a coluna existir)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'registros_sessao'
          AND column_name  = 'materia'
    ) THEN
        ALTER TABLE public.registros_sessao
            RENAME COLUMN materia TO area_trabalhada;
    END IF;
END $$;

-- Garante as novas colunas (ADD COLUMN IF NOT EXISTS é idempotente)
ALTER TABLE public.registros_sessao
    ADD COLUMN IF NOT EXISTS area_trabalhada     TEXT,
    ADD COLUMN IF NOT EXISTS material_utilizado  TEXT,
    ADD COLUMN IF NOT EXISTS observacoes_internas TEXT,  -- cobre caso de rename já feito
    ADD COLUMN IF NOT EXISTS observacoes_familia TEXT,
    ADD COLUMN IF NOT EXISTS enviado_familia     BOOLEAN NOT NULL DEFAULT FALSE;

-- Remove coluna obsoleta
ALTER TABLE public.registros_sessao
    DROP COLUMN IF EXISTS nota_avaliacao;

-- Recria trigger com nome correto (o antigo continua funcionando mas fica com nome errado)
DROP TRIGGER IF EXISTS set_updated_at_registros_aula    ON public.registros_sessao;
DROP TRIGGER IF EXISTS set_updated_at_registros_sessao  ON public.registros_sessao;
CREATE TRIGGER set_updated_at_registros_sessao
    BEFORE UPDATE ON public.registros_sessao
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Índices
CREATE INDEX IF NOT EXISTS idx_registros_sessao_professor
    ON public.registros_sessao(professor_id);
CREATE INDEX IF NOT EXISTS idx_registros_sessao_aluno
    ON public.registros_sessao(aluno_id);


-- ============================================================
-- 3. CREATE TABLE anamneses
-- ============================================================

CREATE TABLE IF NOT EXISTS public.anamneses (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id     UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id         UUID        NOT NULL REFERENCES public.alunos(id) ON DELETE CASCADE,
    data_realizacao  DATE        NOT NULL,
    -- conteudo e secoes são AMBOS opcionais: profissional usa o que preferir
    conteudo         TEXT,
    secoes           JSONB,      -- [{titulo, texto}, ...]
    observacoes      TEXT,
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_anamneses_professor
    ON public.anamneses(professor_id);
CREATE INDEX IF NOT EXISTS idx_anamneses_aluno
    ON public.anamneses(professor_id, aluno_id);

ALTER TABLE public.anamneses ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'anamneses' AND policyname = 'professor acessa suas anamneses'
    ) THEN
        CREATE POLICY "professor acessa suas anamneses"
            ON public.anamneses FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.anamneses TO authenticated;

DROP TRIGGER IF EXISTS set_updated_at_anamneses ON public.anamneses;
CREATE TRIGGER set_updated_at_anamneses
    BEFORE UPDATE ON public.anamneses
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================
-- 4. CREATE TABLE avaliacoes
-- ============================================================

CREATE TABLE IF NOT EXISTS public.avaliacoes (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id            UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id                UUID        NOT NULL REFERENCES public.alunos(id) ON DELETE CASCADE,
    data_inicio             DATE        NOT NULL,
    data_fim                DATE,
    status                  TEXT        NOT NULL DEFAULT 'em_andamento'
        CHECK (status IN ('em_andamento', 'concluida')),
    -- conteudo e areas são AMBOS opcionais
    conteudo                TEXT,
    areas                   JSONB,      -- [{area, observacao}, ...]
    instrumentos_utilizados TEXT,
    pontos_fortes           TEXT,
    pontos_atencao          TEXT,
    observacoes             TEXT,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_avaliacoes_professor
    ON public.avaliacoes(professor_id);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_aluno
    ON public.avaliacoes(professor_id, aluno_id);

ALTER TABLE public.avaliacoes ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'avaliacoes' AND policyname = 'professor acessa suas avaliacoes'
    ) THEN
        CREATE POLICY "professor acessa suas avaliacoes"
            ON public.avaliacoes FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.avaliacoes TO authenticated;

DROP TRIGGER IF EXISTS set_updated_at_avaliacoes ON public.avaliacoes;
CREATE TRIGGER set_updated_at_avaliacoes
    BEFORE UPDATE ON public.avaliacoes
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================
-- 5. CREATE TABLE devolutivas
-- ============================================================

CREATE TABLE IF NOT EXISTS public.devolutivas (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id            UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id                UUID        NOT NULL REFERENCES public.alunos(id) ON DELETE CASCADE,
    avaliacao_id            UUID        REFERENCES public.avaliacoes(id) ON DELETE SET NULL,
    data_entrega            DATE,
    conteudo                TEXT,       -- texto livre do relatório completo
    encaminhamentos         TEXT,
    recomendacoes_familia   TEXT,
    recomendacoes_escola    TEXT,
    arquivo_pdf_url         TEXT,
    enviado_familia         BOOLEAN     NOT NULL DEFAULT FALSE,
    enviado_escola          BOOLEAN     NOT NULL DEFAULT FALSE,
    criado_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devolutivas_professor
    ON public.devolutivas(professor_id);
CREATE INDEX IF NOT EXISTS idx_devolutivas_aluno
    ON public.devolutivas(professor_id, aluno_id);
CREATE INDEX IF NOT EXISTS idx_devolutivas_avaliacao
    ON public.devolutivas(avaliacao_id);

ALTER TABLE public.devolutivas ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'devolutivas' AND policyname = 'professor acessa suas devolutivas'
    ) THEN
        CREATE POLICY "professor acessa suas devolutivas"
            ON public.devolutivas FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.devolutivas TO authenticated;

DROP TRIGGER IF EXISTS set_updated_at_devolutivas ON public.devolutivas;
CREATE TRIGGER set_updated_at_devolutivas
    BEFORE UPDATE ON public.devolutivas
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================
-- 6. CREATE TABLE planos_intervencao
-- ============================================================

CREATE TABLE IF NOT EXISTS public.planos_intervencao (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id       UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id           UUID        NOT NULL REFERENCES public.alunos(id) ON DELETE CASCADE,
    titulo             TEXT        NOT NULL,
    objetivo_geral     TEXT,
    areas_foco         TEXT[],     -- ex: ARRAY['linguagem', 'motricidade']
    estrategias        TEXT,
    duracao_estimada   TEXT,       -- ex: '3 meses', '10 sessões'
    status             TEXT        NOT NULL DEFAULT 'ativo'
        CHECK (status IN ('ativo', 'concluido', 'pausado')),
    observacoes        TEXT,
    criado_em          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planos_intervencao_professor
    ON public.planos_intervencao(professor_id);
CREATE INDEX IF NOT EXISTS idx_planos_intervencao_aluno
    ON public.planos_intervencao(professor_id, aluno_id);

ALTER TABLE public.planos_intervencao ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'planos_intervencao'
          AND policyname = 'professor acessa seus planos de intervencao'
    ) THEN
        CREATE POLICY "professor acessa seus planos de intervencao"
            ON public.planos_intervencao FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.planos_intervencao TO authenticated;

DROP TRIGGER IF EXISTS set_updated_at_planos_intervencao ON public.planos_intervencao;
CREATE TRIGGER set_updated_at_planos_intervencao
    BEFORE UPDATE ON public.planos_intervencao
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================
-- 7. CREATE TABLE documentos_aluno
-- ============================================================

CREATE TABLE IF NOT EXISTS public.documentos_aluno (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id     UUID        NOT NULL REFERENCES public.alunos(id) ON DELETE CASCADE,
    titulo       TEXT        NOT NULL,
    tipo         TEXT        NOT NULL DEFAULT 'outro'
        CHECK (tipo IN ('laudo', 'relatorio_externo', 'encaminhamento', 'outro')),
    arquivo_url  TEXT,
    observacoes  TEXT,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documentos_aluno_professor
    ON public.documentos_aluno(professor_id);
CREATE INDEX IF NOT EXISTS idx_documentos_aluno_aluno
    ON public.documentos_aluno(professor_id, aluno_id);

ALTER TABLE public.documentos_aluno ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'documentos_aluno'
          AND policyname = 'professor acessa seus documentos'
    ) THEN
        CREATE POLICY "professor acessa seus documentos"
            ON public.documentos_aluno FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.documentos_aluno TO authenticated;

DROP TRIGGER IF EXISTS set_updated_at_documentos_aluno ON public.documentos_aluno;
CREATE TRIGGER set_updated_at_documentos_aluno
    BEFORE UPDATE ON public.documentos_aluno
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================
-- 8. CREATE TABLE templates_profissional
-- ============================================================

CREATE TABLE IF NOT EXISTS public.templates_profissional (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    professor_id UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tipo         TEXT        NOT NULL
        CHECK (tipo IN ('anamnese', 'avaliacao')),
    nome         TEXT        NOT NULL,
    -- secoes: [{titulo, texto}] para anamnese; [{area, observacao}] para avaliacao
    secoes       JSONB       NOT NULL DEFAULT '[]'::jsonb,
    padrao       BOOLEAN     NOT NULL DEFAULT FALSE,
    criado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Garante no máximo 1 template padrão por professor + tipo
CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_padrao_unico
    ON public.templates_profissional(professor_id, tipo)
    WHERE padrao = TRUE;

CREATE INDEX IF NOT EXISTS idx_templates_professor
    ON public.templates_profissional(professor_id);

ALTER TABLE public.templates_profissional ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'templates_profissional'
          AND policyname = 'professor acessa seus templates'
    ) THEN
        CREATE POLICY "professor acessa seus templates"
            ON public.templates_profissional FOR ALL
            USING  (professor_id = auth.uid())
            WITH CHECK (professor_id = auth.uid());
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.templates_profissional TO authenticated;

DROP TRIGGER IF EXISTS set_updated_at_templates_profissional ON public.templates_profissional;
CREATE TRIGGER set_updated_at_templates_profissional
    BEFORE UPDATE ON public.templates_profissional
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================
-- Storage: buckets para documentos e avatares
-- ============================================================

-- Bucket privado para documentos clínicos
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'documentos-alunos', 'documentos-alunos', FALSE, 10485760,
    ARRAY['application/pdf','image/jpeg','image/png','image/webp',
          'application/msword',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
) ON CONFLICT (id) DO NOTHING;

-- Bucket público para avatares dos alunos
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'avatares-alunos', 'avatares-alunos', TRUE, 5242880,
    ARRAY['image/jpeg','image/png','image/webp']
) ON CONFLICT (id) DO NOTHING;

-- Políticas storage: documentos (privado)
DROP POLICY IF EXISTS "professor acessa documentos de seus alunos" ON storage.objects;
CREATE POLICY "professor acessa documentos de seus alunos"
    ON storage.objects FOR ALL
    USING (bucket_id = 'documentos-alunos' AND (storage.foldername(name))[1] = auth.uid()::TEXT)
    WITH CHECK (bucket_id = 'documentos-alunos' AND (storage.foldername(name))[1] = auth.uid()::TEXT);

-- Políticas storage: avatares (leitura pública, upload apenas do dono)
DROP POLICY IF EXISTS "avatares publicos para leitura" ON storage.objects;
CREATE POLICY "avatares publicos para leitura"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'avatares-alunos');

DROP POLICY IF EXISTS "professor faz upload de avatares" ON storage.objects;
CREATE POLICY "professor faz upload de avatares"
    ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'avatares-alunos' AND (storage.foldername(name))[1] = auth.uid()::TEXT);

DROP POLICY IF EXISTS "professor deleta seus avatares" ON storage.objects;
CREATE POLICY "professor deleta seus avatares"
    ON storage.objects FOR DELETE
    USING (bucket_id = 'avatares-alunos' AND (storage.foldername(name))[1] = auth.uid()::TEXT);

-- ============================================================
-- Recarrega schema do PostgREST
-- ============================================================
NOTIFY pgrst, 'reload schema';
