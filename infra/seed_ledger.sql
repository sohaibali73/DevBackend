-- Mark all repo migrations as already-applied so the backend's startup
-- migration runner is a no-op (the schema now comes from the Supabase dump).
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename   text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations(filename)
SELECT unnest(ARRAY[
  '000_azure_bootstrap.sql','001_incremental_missing.sql','001_initial_schema.sql',
  '001_training_data.sql','002_feedback_analytics.sql','003_researcher_tables.sql',
  '004_history_tables.sql','004_history_tables_FIXED.sql','005_afl_uploaded_files.sql',
  '006_afl_settings_presets.sql','007_conversation_files.sql','008_missing_tables.sql',
  '009_brain_tables_and_embeddings.sql','010_supabase_auth_migration.sql',
  '010_v4_feature_tables.sql','011_fix_foreign_keys.sql','012_clean_slate_auth_fix.sql',
  '013_security_hardening.sql','014_secure_rebuild.sql',
  '015_add_storage_path_to_brain_documents.sql','016_fix_brain_chunks_and_storage_path.sql',
  '017_multi_provider_keys.sql','018_agent_teams.sql','019_generative_ui_persistence.sql',
  '020_pptx_programs_and_assets.sql','023_yang.sql','024_knowledge_stacks.sql',
  '025_file_chunks.sql','026_fix_brain_chunks_dimension.sql','027_studio_projects.sql',
  '028_studio_writing_styles.sql','029_studio_humanization_runs.sql','030_studio_sites.sql',
  '031_user_skills.sql','032_yang_autopilot.sql','033_yang_artifacts.sql',
  '034_workspace_files.sql','035_azure_selfhosted_auth.sql','agent_teams_v2.sql',
  'create_slide_library.sql'
]) ON CONFLICT DO NOTHING;
