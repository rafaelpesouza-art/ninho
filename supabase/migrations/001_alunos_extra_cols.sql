-- Migration 001: Adiciona colunas extras em alunos
-- Execute no SQL Editor do Supabase APÓS o schema.sql inicial

ALTER TABLE alunos
    ADD COLUMN IF NOT EXISTS familia_id        UUID,
    ADD COLUMN IF NOT EXISTS dia_semana_fixo   SMALLINT CHECK (dia_semana_fixo BETWEEN 0 AND 6),
    ADD COLUMN IF NOT EXISTS horario_fixo      TIME,
    ADD COLUMN IF NOT EXISTS duracao_padrao_min SMALLINT DEFAULT 60,
    ADD COLUMN IF NOT EXISTS valor_aula        NUMERIC(10,2);

-- Index para buscar irmãos pelo mesmo familia_id
CREATE INDEX IF NOT EXISTS idx_alunos_familia_id ON alunos(familia_id);

COMMENT ON COLUMN alunos.dia_semana_fixo IS '0=Segunda 1=Terça 2=Quarta 3=Quinta 4=Sexta 5=Sábado 6=Domingo';
COMMENT ON COLUMN alunos.familia_id IS 'UUID compartilhado entre alunos da mesma família (irmãos)';
