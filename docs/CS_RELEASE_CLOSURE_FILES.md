# Inventario exacto CS-RELEASE-CLOSURE-001

Contra before.zip/baseline.json del respaldo CS_RELEASE_CLOSURE_20261111_225752. Excluye .qa, datos/configuración, dependencias, caches y bytecode.

## modified (25)

- `AGENTS.md`
- `CONTINUAR_EN_CODEX.md`
- `backend/app/evidence_history.py`
- `backend/app/fiscal_read.py`
- `backend/app/integral_api.py`
- `backend/app/main.py`
- `backend/app/schema_compatibility.py`
- `backend/app/storage/classifier.py`
- `backend/app/storage/review.py`
- `backend/app/storage/router.py`
- `backend/app/storage/service.py`
- `backend/tests/test_storage_core.py`
- `docs/CS_LOTE3.md`
- `docs/CS_LOTE4.md`
- `frontend/dist/contasuite-build.json`
- `frontend/dist/index.html`
- `frontend/src/App.tsx`
- `frontend/src/components/ui.tsx`
- `frontend/src/main.tsx`
- `frontend/src/modules/CalendarManagement.tsx`
- `frontend/src/modules/Documents.tsx`
- `frontend/src/modules/StorageReview.tsx`
- `scripts/schema_admin.py`
- `scripts/service_runtime.py`
- `scripts/stamp_recovery_build.py`

## added (39)

- `backend/app/document_identity.py`
- `backend/integral_migrations/003_document_identity.py`
- `backend/tests/test_document_identity.py`
- `backend/tests/test_release_runtime.py`
- `deploy/windows/INSTALL.cmd`
- `deploy/windows/START.cmd`
- `deploy/windows/nginx-lan.conf.example`
- `docs/CS_RELEASE_CLOSURE.md`
- `docs/CS_RELEASE_CLOSURE_FILES.md`
- `docs/INSTALL_RELEASE_WINDOWS.md`
- `docs/qa-release/alto-contraste-final.jpg`
- `docs/qa-release/calendario-claro.jpg`
- `docs/qa-release/calendario-editor.jpg`
- `docs/qa-release/calendario-movil.jpg`
- `docs/qa-release/calendario-oscuro.jpg`
- `docs/qa-release/conciliacion.jpg`
- `docs/qa-release/correccion-documental.jpg`
- `docs/qa-release/empresas-claro.jpg`
- `docs/qa-release/empresas-final.jpg`
- `docs/qa-release/historial-decision-final.jpg`
- `docs/qa-release/inicio.jpg`
- `docs/qa-release/modal.jpg`
- `docs/qa-release/visual-results.json`
- `frontend/dist/assets/index-DwIKNN6o.js`
- `frontend/dist/assets/index-WYEkTCQJ.css`
- `frontend/src/modules/DocumentReconciliation.tsx`
- `frontend/src/stitch-refinements.css`
- `scripts/build_private_runtime.py`
- `scripts/install_release.py`
- `scripts/package_release.py`
- `scripts/release_http.py`
- `scripts/release_http_followup.py`
- `scripts/release_lab.py`
- `scripts/release_manifest.py`
- `scripts/release_package_test.py`
- `scripts/release_postgres.py`
- `scripts/release_reopen_http.py`
- `scripts/service_admin.py`
- `scripts/windows_service.py`

## deleted (2)

- `frontend/dist/assets/index-C6kFgQOY.js`
- `frontend/dist/assets/index-ZJDwdYrD.css`
