-- Migration 006: Personalização de Cor e Logo do Usuário
-- Execute no SQL Editor do Supabase APÓS 005_perfil.sql

ALTER TABLE public.perfis_professor
ADD COLUMN IF NOT EXISTS cor_primaria TEXT DEFAULT '#7F77DD',
ADD COLUMN IF NOT EXISTS logo_url TEXT;

-- Notificar o PostgREST para recarregar o schema
NOTIFY pgrst, 'reload schema';
