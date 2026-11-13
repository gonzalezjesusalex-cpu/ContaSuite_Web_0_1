# Inventario exacto CS-INTEGRATION-RECOVERY-001

Contra before.zip/baseline.json; omite caches de pruebas y bytecode. Incluye capturas y artefactos compilados.

Los dos archivos frontend/tests preexistentes no estaban en el ZIP inicial; no se modificaron y sus SHA-256 se contrastaron con los manifiestos de Lote 2 y FINALIZATION. Véase preexisting_verified.json junto al respaldo.

## modified (20)

- `AGENTS.md`
- `CONTINUAR_EN_CODEX.md`
- `backend/app/credential_alerts.py`
- `backend/app/database.py`
- `backend/app/integral_api.py`
- `backend/app/lote4_lifecycle.py`
- `backend/app/lote4_summary.py`
- `backend/app/main.py`
- `backend/app/storage/worker.py`
- `backend/tests/test_api.py`
- `backend/tests/test_credentials.py`
- `backend/tests/test_integral.py`
- `backend/tests/test_storage_core.py`
- `docs/CS_LOTE3.md`
- `docs/CS_LOTE4.md`
- `frontend/dist/contasuite-build.json`
- `frontend/dist/index.html`
- `frontend/src/modules/Credentials.tsx`
- `frontend/src/modules/FiscalCalendar.tsx`
- `frontend/src/modules/IntegralDashboard.tsx`

## added (39)

- `backend/app/alert_query.py`
- `backend/app/evidence_history.py`
- `backend/app/schema_compatibility.py`
- `backend/integral_migrations/002_evidence_history.py`
- `backend/requirements-recovery.lock.txt`
- `backend/tests/recovery_defects.py`
- `backend/tests/run_recovery_isolated.py`
- `deploy/windows/Backup-ContaSuite.ps1`
- `deploy/windows/Install-ContaSuite.cmd`
- `deploy/windows/Install-ContaSuite.ps1`
- `deploy/windows/Start-ContaSuite.cmd`
- `deploy/windows/Start-ContaSuite.ps1`
- `deploy/windows/service.example.xml`
- `docs/CS_INTEGRATION_RECOVERY.md`
- `docs/CS_INTEGRATION_RECOVERY_FILES.md`
- `docs/INSTALL_RECOVERY_WINDOWS.md`
- `docs/qa-recovery/calendar-mobile-final.jpg`
- `docs/qa-recovery/calendar-mobile.jpg`
- `docs/qa-recovery/calendar-month-final.jpg`
- `docs/qa-recovery/calendar-month.jpg`
- `docs/qa-recovery/dashboard-counters.jpg`
- `docs/qa-recovery/dashboard-final.jpg`
- `docs/qa-recovery/dashboard.jpg`
- `docs/qa-recovery/manual-date-saved.jpg`
- `frontend/dist/assets/index-C6kFgQOY.js`
- `frontend/dist/assets/index-ZJDwdYrD.css`
- `frontend/src/modules/calendar-view.css`
- `scripts/backup_postgres.py`
- `scripts/integration_http.py`
- `scripts/integration_http_followup.py`
- `scripts/integration_package.py`
- `scripts/integration_postgres.py`
- `scripts/integration_runtime.py`
- `scripts/package_recovery.py`
- `scripts/recovery_manifest.py`
- `scripts/run_recovery_pytest.py`
- `scripts/schema_admin.py`
- `scripts/service_runtime.py`
- `scripts/stamp_recovery_build.py`

## deleted (2)

- `frontend/dist/assets/index-BDXKEQhX.js`
- `frontend/dist/assets/index-ZTcUIbQX.css`
