# Potomac Analyst Workbench - File Structure

## Root Directory
```
.dockerignore
.gitignore
.railwayignore
config.py
Dockerfile
fix_researcher.py
main.py
nixpacks.toml
Procfile
pyrightconfig.json
railway.json
requirements.txt
test_yfinance_api.py
-p/
```

## API Layer
```
api/
├── __init__.py
├── dependencies.py
├── requirements.txt
└── routes/
    ├── __init__.py
    ├── admin.py
    ├── afl.py
    ├── ai.py
    ├── auth.py
    ├── backtest.py
    ├── brain.py
    ├── chat.py
    ├── content.py
    ├── health.py
    ├── presentations.py
    ├── researcher.py
    ├── reverse_engineer.py
    ├── skills.py
    ├── train.py
    ├── upload.py
    └── yfinance.py
```

## Core Engine
```
core/
├── __init__.py
├── afl_validator.py
├── artifact_parser.py
├── claude_engine_wrapper.py
├── claude_engine.py
├── claude_integration.py
├── claude_tools.py
├── context_manager.py
├── document_classifier.py
├── document_parser.py
├── encryption.py
├── knowledge_base.py
├── pptx_generator.py
├── researcher_engine.py
├── researcher.py
├── skill_gateway.py
├── skills.py
├── storage.py
├── streaming.py
├── tools.py
├── training.py
├── ui_message_stream.py
├── vercel_ai.py
├── vercel_client.py
└── prompts/
    ├── __init__.py
    ├── afl_reference.py
    ├── afl.py
    ├── base.py
    ├── comprehensive_rules.py
    ├── condensed_prompts.py
    ├── reverse_engineer.py
    ├── system_prompts.py
    └── templates.py
```

## Data Layer
```
data/
└── presentations/

db/
├── __init__.py
├── supabase_client.py
└── migrations/
    ├── 001_incremental_missing.sql
    ├── 001_initial_schema.sql
    ├── 001_training_data.sql
    ├── 002_feedback_analytics.sql
    ├── 003_researcher_tables.sql
    ├── 004_history_tables_FIXED.sql
    ├── 004_history_tables.sql
    ├── 005_afl_uploaded_files.sql
    ├── 006_afl_settings_presets.sql
    ├── 007_conversation_files.sql
    ├── 008_missing_tables.sql
    ├── 009_brain_tables_and_embeddings.sql
    ├── 010_supabase_auth_migration.sql
    ├── 011_fix_foreign_keys.sql
    ├── 012_clean_slate_auth_fix.sql
    ├── 013_security_hardening.sql
    ├── 014_secure_rebuild.sql
    ├── MIGRATION_README.md
    └── POLICY_FIX_README.md
```

## Documentation
```
docs/
├── ARCHITECTURE.md
├── CHANGELOG.md
├── MASTER_PLAN.md
├── PERSISTENCE_FIX.md
├── SECURITY.md
└── YFINANCE_API.md