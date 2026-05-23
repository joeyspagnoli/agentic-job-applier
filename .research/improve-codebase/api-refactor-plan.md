# API Refactor Plan (api/main.py 4340 → <200 lines)

## Critical: test-compat re-exports
Tests import from `api.main`:
- `app`
- `_source_label`
- `SETTINGS_PROFILE_PATH`
- `TAILORED_RESUME_TOKEN_ENV_KEY`
- `TAILORED_RESUME_TOKEN_HEADER`
- `resolve_database_path`

These MUST stay re-exported from `api/main.py`.

## File layout
```
api/
  __init__.py
  main.py                 # app construction + router includes + lifespan + SPA fallback + re-exports
  config.py               # constants (DASHBOARD_*, SETTINGS_*_PATH, TAILORED_RESUME_*, JOB_HASH_PATTERN, etc.)
  errors.py               # _error_response, _raise_api_error, _http_exception_handler
  schemas/
    __init__.py
    common.py             # ReviewerActionRequest, BudgetUpdateRequest, YamlTextUpdateRequest, YamlPayload, ApiKeyUpsertRequest, ServiceTierUpdateRequest, ProviderConfigRequest, JobImportRequest
    candidate.py          # CandidateContactSectionPayload + nested types (lines 229-457)
  services/
    sources.py            # _source_label, _source_filter_sql
    salary.py             # _salary_display, _parse_gate_result, _parse_unresolved_fields, _build_pipeline_steps
    yaml_files.py         # _read_settings_text, _parse_yaml_mapping, _persist_yaml_mapping, _resolve_settings_file_metadata, _backup_settings_file, _prune_settings_backups, _read_uploaded_text, _validate_candidate_profile_document, _normalize_candidate_profile_output, _validate_resume_document, _resume_counts, _normalize_optional_country_code
    env_keys.py           # _read_env_pairs, _read_env_key_statuses, _write_env_key, _delete_env_key, _build_api_keys_response
    system_scripts.py     # _resolve_system_script_path, _run_system_script, _dispatch_system_lifecycle_action, _load_positive_int_env
    tailored_resume.py    # _validate_job_hash, _require_tailored_resume_access, _is_safe_tailored_resume_path, _resolve_artifact_path, _resolve_latest_tailored_resume_pdf_path
    tex_migration.py      # _normalize_tex_section_headings, _build_fallback_personal_header, _build_fallback_education_section, _ensure_tex_required_sections, _prepare_resume_tex_for_migration
    migrations.py         # _run_startup_migrations, _lifespan
  routers/
    health.py             # GET /api/health
    system.py             # /api/system/{stop,restart,fetch-jobs}
    dashboard.py          # /api/dashboard/{stats,discovery-trend}
    jobs.py               # /api/jobs, /api/jobs/{job_hash}/resume, /api/jobs/import
    human_review.py       # /api/human-review*
    failures.py           # /api/failures*, /api/failures/{id}/retry (owns _serialize_failure_record)
    costs.py              # /api/costs/{stats,daily-trend,by-stage}
    settings_api_keys.py  # /api/settings/api-keys{,/{name}}, /api/settings/service-tier
    settings_budget.py    # /api/budget GET/PUT
    settings_files.py     # /api/settings/files, profile, resume, *_structured, /resume/pdf, /resume/tex, downloads
    settings_filters.py   # /api/settings/{filters,sources}
    settings_provider.py  # /api/settings/{ai-provider,codex-auth/*,onboarding-status}
    pipeline.py           # GET /api/pipeline/progress (SSE)
```

## Migration order (lowest blast radius first)
1. `api/config.py` + `api/errors.py` (pure constants/utilities)
2. `api/schemas/{common,candidate}.py` (pure data classes)
3. `api/services/migrations.py` (lifespan)
4. `api/services/{sources,system_scripts,env_keys,yaml_files,tailored_resume,tex_migration,salary}.py`
5. **Routers in extraction order:** health → system → costs → pipeline → settings_api_keys → settings_filters → settings_provider → dashboard → failures → human_review → jobs → settings_files
6. SPA fallback stays in `api/main.py` (must be registered last)

After each extraction: run targeted test (`uv run --no-dev pytest tests/test_api_*.py -q`).
