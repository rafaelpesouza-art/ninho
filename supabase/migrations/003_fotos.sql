-- Migration 003: Permissões para fotos_sessao e Storage
-- Execute no SQL Editor do Supabase APÓS 002_agenda.sql

-- GRANT na tabela fotos_sessao (caso não tenha sido aplicado via schema.sql)
GRANT SELECT, INSERT, DELETE ON TABLE public.fotos_sessao TO anon, authenticated;

-- Garante que o bucket fotos-sessoes existe (idempotente)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'fotos-sessoes',
    'fotos-sessoes',
    FALSE,
    5242880,
    ARRAY['image/jpeg', 'image/png', 'image/webp']
)
ON CONFLICT (id) DO NOTHING;

-- Políticas de Storage (idempotentes)
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'storage'
          AND tablename  = 'objects'
          AND policyname = 'professor faz upload em sua pasta'
    ) THEN
        CREATE POLICY "professor faz upload em sua pasta"
            ON storage.objects FOR INSERT
            WITH CHECK (
                bucket_id = 'fotos-sessoes'
                AND (storage.foldername(name))[1] = auth.uid()::TEXT
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'storage'
          AND tablename  = 'objects'
          AND policyname = 'professor vê seus arquivos'
    ) THEN
        CREATE POLICY "professor vê seus arquivos"
            ON storage.objects FOR SELECT
            USING (
                bucket_id = 'fotos-sessoes'
                AND (storage.foldername(name))[1] = auth.uid()::TEXT
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'storage'
          AND tablename  = 'objects'
          AND policyname = 'professor deleta seus arquivos'
    ) THEN
        CREATE POLICY "professor deleta seus arquivos"
            ON storage.objects FOR DELETE
            USING (
                bucket_id = 'fotos-sessoes'
                AND (storage.foldername(name))[1] = auth.uid()::TEXT
            );
    END IF;
END $$;

NOTIFY pgrst, 'reload schema';
