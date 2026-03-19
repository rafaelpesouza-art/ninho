-- Migration 009: Perfil Acadêmico do Aluno
-- Executar no SQL Editor APÓS 008_planejamento.sql

ALTER TABLE public.alunos
    ADD COLUMN IF NOT EXISTS materia_foco TEXT,
    ADD COLUMN IF NOT EXISTS serie TEXT;

NOTIFY pgrst, 'reload schema';
