"""Runs the standalone suites from pytest, each in its own interpreter.

The lote harness patches the whole process (in-memory SQLite engine, no network, no subprocesses) and
verify_live_agent starts real servers, so they cannot share the pytest process with test_api's database.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

TESTS = Path(__file__).resolve().parent


def run(script, timeout):
    env = {**os.environ, 'PYTHON_DOTENV_DISABLED': '1'}
    result = subprocess.run(
        [sys.executable, str(TESTS / script)],
        cwd=TESTS.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=timeout,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-6000:]
    return result


def test_lote_chain_fiscal_companies_calendar_credentials_recovery():
    # run_recovery_isolated inherits lotes 1, 2 and 4 (closure and finalization) through its test classes.
    output = run('run_recovery_isolated.py', 300).stderr
    assert 'Ran 47 tests' in output and output.rstrip().endswith('OK'), output[-2000:]


def test_lote3_classifier():
    assert run('run_lote3_classifier.py', 120).stderr.rstrip().endswith('OK')


def test_recovery_structural_defects():
    assert run('recovery_defects.py', 120).stderr.rstrip().endswith('OK')


@pytest.mark.slow
def test_live_agent_scan_over_http():
    assert 'PASS:' in run('verify_live_agent.py', 300).stdout
