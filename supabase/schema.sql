-- ============================================================
-- SCHEMA COMPLETO - Sistema de Gestão de Aulas
-- Execute no SQL Editor do Supabase
-- ============================================================

-- Habilita a extensão UUID (já vem ativa no Supabase)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ============================================================
-- 1. ALUNOS
-- ============================================================
CREATE TABLE IF NOT EXISTS alunos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    data_nascimento DATE,
    responsavel     TEXT,
    telefone        TEXT,
    email           TEXT,
    observacoes     TEXT,
    ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alunos_professor_id  ON alunos(professor_id);
CREATE INDEX idx_alunos_ativo         ON alunos(professor_id, ativo);

ALTER TABLE alunos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê seus alunos"
    ON alunos FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor cria seus alunos"
    ON alunos FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor edita seus alunos"
    ON alunos FOR UPDATE
    USING (professor_id = auth.uid());

CREATE POLICY "professor deleta seus alunos"
    ON alunos FOR DELETE
    USING (professor_id = auth.uid());


-- ============================================================
-- 2. ATIVIDADES
-- ============================================================
CREATE TABLE IF NOT EXISTS atividades (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    nome            TEXT NOT NULL,
    descricao       TEXT,
    categoria       TEXT,
    objetivo        TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_atividades_professor_id ON atividades(professor_id);

ALTER TABLE atividades ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê suas atividades"
    ON atividades FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor cria suas atividades"
    ON atividades FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor edita suas atividades"
    ON atividades FOR UPDATE
    USING (professor_id = auth.uid());

CREATE POLICY "professor deleta suas atividades"
    ON atividades FOR DELETE
    USING (professor_id = auth.uid());


-- ============================================================
-- 3. PLANOS DE AULA
-- ============================================================
CREATE TABLE IF NOT EXISTS planos_aula (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id        UUID REFERENCES alunos(id) ON DELETE SET NULL,
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    objetivos       TEXT,
    observacoes     TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_planos_aula_professor_id ON planos_aula(professor_id);
CREATE INDEX idx_planos_aula_aluno_id     ON planos_aula(aluno_id);

-- Tabela de junção planos_aula <-> atividades
CREATE TABLE IF NOT EXISTS planos_aula_atividades (
    plano_id        UUID NOT NULL REFERENCES planos_aula(id) ON DELETE CASCADE,
    atividade_id    UUID NOT NULL REFERENCES atividades(id) ON DELETE CASCADE,
    ordem           SMALLINT DEFAULT 0,
    duracao_min     SMALLINT,
    PRIMARY KEY (plano_id, atividade_id)
);

ALTER TABLE planos_aula ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê seus planos"
    ON planos_aula FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor cria seus planos"
    ON planos_aula FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor edita seus planos"
    ON planos_aula FOR UPDATE
    USING (professor_id = auth.uid());

CREATE POLICY "professor deleta seus planos"
    ON planos_aula FOR DELETE
    USING (professor_id = auth.uid());


-- ============================================================
-- 4. AULAS
-- ============================================================
CREATE TYPE status_aula AS ENUM ('agendada', 'realizada', 'cancelada', 'remarcada');

CREATE TABLE IF NOT EXISTS aulas (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id        UUID NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    plano_id        UUID REFERENCES planos_aula(id) ON DELETE SET NULL,
    data_hora       TIMESTAMPTZ NOT NULL,
    duracao_min     SMALLINT NOT NULL DEFAULT 60,
    status          status_aula NOT NULL DEFAULT 'agendada',
    observacoes     TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_aulas_professor_id ON aulas(professor_id);
CREATE INDEX idx_aulas_aluno_id     ON aulas(aluno_id);
CREATE INDEX idx_aulas_data_hora    ON aulas(professor_id, data_hora);
CREATE INDEX idx_aulas_status       ON aulas(professor_id, status);

ALTER TABLE aulas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê suas aulas"
    ON aulas FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor cria suas aulas"
    ON aulas FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor edita suas aulas"
    ON aulas FOR UPDATE
    USING (professor_id = auth.uid());

CREATE POLICY "professor deleta suas aulas"
    ON aulas FOR DELETE
    USING (professor_id = auth.uid());


-- ============================================================
-- 5. REGISTROS DE AULA
-- ============================================================
CREATE TABLE IF NOT EXISTS registros_aula (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aula_id         UUID NOT NULL REFERENCES aulas(id) ON DELETE CASCADE,
    aluno_id        UUID NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    descricao       TEXT,
    evolucao        TEXT,
    humor           TEXT,                  -- ex: "animado", "resistente", "neutro"
    participacao    SMALLINT CHECK (participacao BETWEEN 1 AND 5),
    observacoes     TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_registros_professor_id ON registros_aula(professor_id);
CREATE INDEX idx_registros_aula_id      ON registros_aula(aula_id);
CREATE INDEX idx_registros_aluno_id     ON registros_aula(aluno_id);

-- Tabela de junção registros_aula <-> atividades realizadas
CREATE TABLE IF NOT EXISTS registros_aula_atividades (
    registro_id     UUID NOT NULL REFERENCES registros_aula(id) ON DELETE CASCADE,
    atividade_id    UUID NOT NULL REFERENCES atividades(id) ON DELETE CASCADE,
    realizada       BOOLEAN DEFAULT TRUE,
    observacao      TEXT,
    PRIMARY KEY (registro_id, atividade_id)
);

ALTER TABLE registros_aula ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê seus registros"
    ON registros_aula FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor cria seus registros"
    ON registros_aula FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor edita seus registros"
    ON registros_aula FOR UPDATE
    USING (professor_id = auth.uid());

CREATE POLICY "professor deleta seus registros"
    ON registros_aula FOR DELETE
    USING (professor_id = auth.uid());


-- ============================================================
-- 6. FOTOS DE SESSÃO
-- ============================================================
CREATE TABLE IF NOT EXISTS fotos_sessao (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    registro_id     UUID NOT NULL REFERENCES registros_aula(id) ON DELETE CASCADE,
    aluno_id        UUID NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    storage_path    TEXT NOT NULL,         -- caminho no bucket: fotos-sessoes/{professor_id}/{aluno_id}/{uuid}.jpg
    url_publica     TEXT,
    legenda         TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_fotos_professor_id ON fotos_sessao(professor_id);
CREATE INDEX idx_fotos_registro_id  ON fotos_sessao(registro_id);
CREATE INDEX idx_fotos_aluno_id     ON fotos_sessao(aluno_id);

ALTER TABLE fotos_sessao ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê suas fotos"
    ON fotos_sessao FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor insere suas fotos"
    ON fotos_sessao FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor deleta suas fotos"
    ON fotos_sessao FOR DELETE
    USING (professor_id = auth.uid());


-- ============================================================
-- 7. RELATÓRIOS DE EVOLUÇÃO
-- ============================================================
CREATE TABLE IF NOT EXISTS relatorios_evolucao (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id        UUID NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    titulo          TEXT NOT NULL,
    periodo_inicio  DATE NOT NULL,
    periodo_fim     DATE NOT NULL,
    conteudo        TEXT,                  -- texto livre ou JSON com seções
    objetivos_met   TEXT,
    proximos_passos TEXT,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_relatorios_professor_id ON relatorios_evolucao(professor_id);
CREATE INDEX idx_relatorios_aluno_id     ON relatorios_evolucao(aluno_id);
CREATE INDEX idx_relatorios_periodo      ON relatorios_evolucao(professor_id, periodo_inicio, periodo_fim);

ALTER TABLE relatorios_evolucao ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê seus relatórios"
    ON relatorios_evolucao FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor cria seus relatórios"
    ON relatorios_evolucao FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor edita seus relatórios"
    ON relatorios_evolucao FOR UPDATE
    USING (professor_id = auth.uid());

CREATE POLICY "professor deleta seus relatórios"
    ON relatorios_evolucao FOR DELETE
    USING (professor_id = auth.uid());


-- ============================================================
-- 8. CONFIGURAÇÕES FINANCEIRAS
-- ============================================================
CREATE TABLE IF NOT EXISTS configuracoes_financeiras (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id        UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    valor_padrao_aula   NUMERIC(10,2) NOT NULL DEFAULT 0,
    moeda               CHAR(3) NOT NULL DEFAULT 'BRL',
    dia_vencimento      SMALLINT CHECK (dia_vencimento BETWEEN 1 AND 31),
    metodos_pagamento   TEXT[],            -- ex: ARRAY['pix','dinheiro','cartao']
    chave_pix           TEXT,
    observacoes         TEXT,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_config_fin_professor_id ON configuracoes_financeiras(professor_id);

ALTER TABLE configuracoes_financeiras ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê sua configuração"
    ON configuracoes_financeiras FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor cria sua configuração"
    ON configuracoes_financeiras FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor edita sua configuração"
    ON configuracoes_financeiras FOR UPDATE
    USING (professor_id = auth.uid());


-- ============================================================
-- 9. FATURAS
-- ============================================================
CREATE TYPE status_fatura AS ENUM ('pendente', 'paga', 'cancelada', 'vencida');
CREATE TYPE metodo_pagamento AS ENUM ('pix', 'dinheiro', 'cartao_credito', 'cartao_debito', 'transferencia', 'outro');

CREATE TABLE IF NOT EXISTS faturas (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    professor_id        UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    aluno_id            UUID NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
    descricao           TEXT NOT NULL,
    valor               NUMERIC(10,2) NOT NULL,
    data_emissao        DATE NOT NULL DEFAULT CURRENT_DATE,
    data_vencimento     DATE NOT NULL,
    data_pagamento      DATE,
    status              status_fatura NOT NULL DEFAULT 'pendente',
    metodo_pagamento    metodo_pagamento,
    observacoes         TEXT,
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_faturas_professor_id   ON faturas(professor_id);
CREATE INDEX idx_faturas_aluno_id       ON faturas(aluno_id);
CREATE INDEX idx_faturas_status         ON faturas(professor_id, status);
CREATE INDEX idx_faturas_vencimento     ON faturas(professor_id, data_vencimento);

-- Tabela de junção faturas <-> aulas (quais aulas compõem a fatura)
CREATE TABLE IF NOT EXISTS faturas_aulas (
    fatura_id   UUID NOT NULL REFERENCES faturas(id) ON DELETE CASCADE,
    aula_id     UUID NOT NULL REFERENCES aulas(id) ON DELETE CASCADE,
    PRIMARY KEY (fatura_id, aula_id)
);

ALTER TABLE faturas ENABLE ROW LEVEL SECURITY;

CREATE POLICY "professor vê suas faturas"
    ON faturas FOR SELECT
    USING (professor_id = auth.uid());

CREATE POLICY "professor cria suas faturas"
    ON faturas FOR INSERT
    WITH CHECK (professor_id = auth.uid());

CREATE POLICY "professor edita suas faturas"
    ON faturas FOR UPDATE
    USING (professor_id = auth.uid());

CREATE POLICY "professor deleta suas faturas"
    ON faturas FOR DELETE
    USING (professor_id = auth.uid());


-- ============================================================
-- TRIGGERS: atualizado_em automático
-- ============================================================
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at_alunos
    BEFORE UPDATE ON alunos
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_atividades
    BEFORE UPDATE ON atividades
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_planos_aula
    BEFORE UPDATE ON planos_aula
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_aulas
    BEFORE UPDATE ON aulas
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_registros_aula
    BEFORE UPDATE ON registros_aula
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_relatorios_evolucao
    BEFORE UPDATE ON relatorios_evolucao
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_configuracoes_financeiras
    BEFORE UPDATE ON configuracoes_financeiras
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_faturas
    BEFORE UPDATE ON faturas
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ============================================================
-- STORAGE: bucket fotos-sessoes
-- ============================================================
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'fotos-sessoes',
    'fotos-sessoes',
    FALSE,
    5242880,                              -- 5 MB por arquivo
    ARRAY['image/jpeg', 'image/png', 'image/webp']
)
ON CONFLICT (id) DO NOTHING;

-- RLS Storage: professor acessa apenas sua pasta
CREATE POLICY "professor faz upload em sua pasta"
    ON storage.objects FOR INSERT
    WITH CHECK (
        bucket_id = 'fotos-sessoes'
        AND (storage.foldername(name))[1] = auth.uid()::TEXT
    );

CREATE POLICY "professor vê seus arquivos"
    ON storage.objects FOR SELECT
    USING (
        bucket_id = 'fotos-sessoes'
        AND (storage.foldername(name))[1] = auth.uid()::TEXT
    );

CREATE POLICY "professor deleta seus arquivos"
    ON storage.objects FOR DELETE
    USING (
        bucket_id = 'fotos-sessoes'
        AND (storage.foldername(name))[1] = auth.uid()::TEXT
    );
