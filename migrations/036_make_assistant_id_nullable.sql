-- Make assistant_id nullable since we no longer use OpenAI Assistants
ALTER TABLE assistant_threads ALTER COLUMN assistant_id DROP NOT NULL;
