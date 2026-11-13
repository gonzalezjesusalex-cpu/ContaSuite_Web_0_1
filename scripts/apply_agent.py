"""Agent update using the tested reversible local updater."""

FILES = (
    'app/agent/agent.py',
    'app/scripts/managed_agent.py',
    'app/scripts/local_runtime.py',
    'app/scripts/windows_service.py',
    'app/backend/app/main.py',
    'app/backend/app/storage/indexer.py',
    'app/backend/app/models.py',
    'app/backend/migrations/versions/0005_index_job_status.py',
)
if __name__ == '__main__':
    from apply_excel_fix import main

    main(FILES)
