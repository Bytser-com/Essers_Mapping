#!/usr/bin/env python3
"""Run project tests and local quality checks on Windows, Linux, or macOS.

From repository root:
    python Scripts/run-tests.py
    python Scripts/run-tests.py --skip-e2e
    python Scripts/run-tests.py --only-e2e
    python Scripts/run-tests.py --only-quality
    python Scripts/run-tests.py --skip-quality

Requires Python, Java 21, Node.js and npm for the full suite.
Additional quality tools: Semgrep, Gitleaks and jscpd (see README-test-runner.md).
SonarQube for IDE (formerly SonarLint) is a separate manual IDE check.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sysconfig
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == 'nt'
Result = tuple[str, str, str]


def java_command(directory: str) -> list[str]:
    """Use the project's Maven wrapper on the current operating system."""
    if IS_WINDOWS:
        return [str(ROOT / directory / 'mvnw.cmd'), 'clean', 'verify']
    # Wrapper scripts in ZIP archives often lose their executable permission.
    return ['bash', './mvnw', 'clean', 'verify']


def npm_command(*arguments: str) -> list[str]:
    return ['npm.cmd' if IS_WINDOWS else 'npm', *arguments]


def run_check(name: str, directory: str, command: list[str], results: list[Result]) -> bool:
    print('\n' + '=' * 72)
    print(name)
    print('=' * 72)
    workdir = ROOT / directory

    if not workdir.is_dir():
        detail = f'Missing directory: {workdir}'
        print('FAIL:', detail)
        results.append((name, 'FAIL', detail))
        return False

    print(f'Directory: {workdir}')
    print('Command:   ' + ' '.join(command), flush=True)
    try:
        completed = subprocess.run(command, cwd=workdir, check=False)
    except OSError as error:
        detail = str(error)
        print('FAIL:', detail)
        results.append((name, 'FAIL', detail))
        return False

    if completed.returncode == 0:
        print(f'PASS: {name}', flush=True)
        results.append((name, 'PASS', ''))
        return True

    detail = f'Exit code {completed.returncode}'
    print(f'FAIL: {name} ({detail})', flush=True)
    results.append((name, 'FAIL', detail))
    return False


def skip(name: str, reason: str, results: list[Result]) -> None:
    print(f'SKIP: {name} ({reason})')
    results.append((name, 'SKIP', reason))


def manual(name: str, reason: str, results: list[Result]) -> None:
    print(f'MANUAL: {name} ({reason})')
    results.append((name, 'MANUAL', reason))


def find_tool(executable: str) -> str | None:
    """Find a CLI installed through pip (current interpreter) or on PATH."""
    suffix = '.exe' if IS_WINDOWS else ''
    local = Path(sysconfig.get_path('scripts')) / (executable + suffix)
    if local.is_file():
        return str(local)
    return shutil.which(executable)


def require_tool(name: str, executable: str, install_hint: str,
                 results: list[Result]) -> str | None:
    found = find_tool(executable)
    if found:
        return found
    detail = f'{executable} not found. {install_hint}'
    print(f'FAIL: {name}: {detail}')
    results.append((name, 'FAIL', detail))
    return None


def run_quality_checks(results: list[Result]) -> None:
    """Execute local CLI checks; flag SonarQube for IDE for human review."""
    print('\nLocal quality checks: see README-test-runner.md for setup and scope.')

    semgrep = require_tool('Quality - Semgrep', 'semgrep',
                           'Install: python -m pip install -r Scripts/requirements-quality.txt', results)
    if semgrep:
        run_check('Quality - Semgrep', '.',
                  [semgrep, 'scan', '--config', 'p/default', '--error', '--metrics', 'off',
                   '--exclude', '.git', '--exclude', 'node_modules',
                   '--exclude', '.venv', '--exclude', 'dist',
                   '--exclude', 'target', '.'], results)

    gitleaks = require_tool('Quality - Gitleaks', 'gitleaks',
                            'Install Gitleaks (see README-test-runner.md).', results)
    if gitleaks:
        run_check('Quality - Gitleaks', '.',
                  [gitleaks, 'dir', '.', '--redact', '--no-banner', '--verbose'], results)

    jscpd_bin = ROOT / 'Scripts' / 'node_modules' / '.bin' / ('jscpd.cmd' if IS_WINDOWS else 'jscpd')
    if jscpd_bin.is_file():
        jscpd = str(jscpd_bin)
    else:
        jscpd = shutil.which('jscpd')
    if jscpd:
        run_check('Quality - jscpd', '.',
                  [jscpd, '.', '--min-lines', '10', '--min-tokens', '70',
                   '--threshold', '10', '--gitignore',
                   '--ignore', '**/node_modules/**,**/.git/**,**/.venv/**,**/target/**,**/dist/**,**/coverage/**,**/data/**,**/output/**',
                   '--reporters', 'console'], results)
    else:
        detail = 'jscpd not found. From Scripts/: run npm install (see README-test-runner.md)'
        print(f'FAIL: Quality - jscpd: {detail}')
        results.append(('Quality - jscpd', 'FAIL', detail))

    manual('Quality - SonarQube for IDE (SonarLint)',
           'Review the project locally in the IDE and resolve relevant findings; '
           'the IDE review cannot be verified by this script.', results)


def run_frontend_e2e(results: list[Result], *, build_passed: bool) -> None:
    name = 'Frontend - Playwright E2E'
    if not build_passed:
        skip(name, 'Frontend build failed', results)
        return
    passed = run_check(name, 'Frontend', npm_command('run', 'test:e2e'), results)
    if not passed:
        print('\nPlaywright diagnostic steps:')
        print('  cd Frontend')
        print('  npx playwright install chromium')
        print('  npm run test:e2e')
        print('  npx playwright show-report')
        print('An E2E failure is NOT necessarily caused by missing Chromium.')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--only-e2e', '-OnlyE2E', action='store_true',
                       help='Only run frontend build + Playwright tests')
    modes.add_argument('--only-quality', '-OnlyQuality', action='store_true',
                       help='Run local Semgrep, Gitleaks and jscpd checks only')
    parser.add_argument('--skip-e2e', '-SkipE2E', action='store_true',
                        help='Skip browser-based Playwright tests')
    parser.add_argument('--skip-quality', '-SkipQuality', action='store_true',
                        help='Skip optional local quality checks')
    args = parser.parse_args(argv)
    if args.only_e2e and args.skip_e2e:
        parser.error('--only-e2e and --skip-e2e cannot be used together')
    if args.only_quality and args.skip_quality:
        parser.error('--only-quality and --skip-quality cannot be used together')

    print('Essers_Mapping - Full local test suite')
    print(f'Repository: {ROOT}')
    print(f'Platform:   {sys.platform}')
    results: list[Result] = []

    if not args.only_e2e and not args.only_quality:
        run_check('Mapping Proposal - pytest', 'Mapping_Proposal',
                  [sys.executable, '-m', 'pytest', '-q'], results)
        run_check('Mapping Proposal - Ruff', 'Mapping_Proposal',
                  [sys.executable, '-m', 'ruff', 'check', '.'], results)

        # Automatically include Mapping Converter once it contains tests.
        if (ROOT / 'Mapping_Converter' / 'tests').is_dir():
            run_check('Mapping Converter - pytest', 'Mapping_Converter',
                      [sys.executable, '-m', 'pytest', '-q'], results)
            run_check('Mapping Converter - Ruff', 'Mapping_Converter',
                      [sys.executable, '-m', 'ruff', 'check', '.'], results)
        else:
            print('Mapping Converter: no tests directory yet (not counted).')

        run_check('Version Control - Maven verify', 'Version_Control',
                  java_command('Version_Control'), results)
        run_check('Runtime - Maven verify', 'Runtime',
                  java_command('Runtime'), results)

        run_check('Scripts - Python unittest', '.',
                  [sys.executable, '-m', 'unittest', 'discover', '-s', 'Scripts/tests',
                   '-p', 'test_*.py'], results)
        run_check('Scripts - Node workflow tests', '.',
                  ['node', 'Scripts/tests/test_service_workflows.cjs'], results)

        run_check('Frontend - ESLint', 'Frontend', npm_command('run', 'lint'), results)
        run_check('Frontend - TypeScript', 'Frontend', npm_command('run', 'typecheck'), results)
        run_check('Frontend - Vitest (all suites + coverage)', 'Frontend',
                  npm_command('run', 'test:coverage'), results)

    if not args.only_quality:
        build_passed = run_check('Frontend - production build', 'Frontend',
                                 npm_command('run', 'build'), results)
        if args.skip_e2e:
            skip('Frontend - Playwright E2E', 'Requested --skip-e2e', results)
        else:
            run_frontend_e2e(results, build_passed=build_passed)

    if not args.only_e2e:
        if args.skip_quality:
            skip('Local quality checks', 'Requested --skip-quality', results)
        else:
            run_quality_checks(results)

    print('\n' + '=' * 72)
    print('FINAL RESULTS')
    print('=' * 72)
    print(f'{"Check":46} {"Status":6} Detail')
    print('-' * 72)
    for name, status, detail in results:
        print(f'{name:46} {status:6} {detail}')

    passed = sum(status == 'PASS' for _, status, _ in results)
    failed = sum(status == 'FAIL' for _, status, _ in results)
    skipped = sum(status == 'SKIP' for _, status, _ in results)
    manual_count = sum(status == 'MANUAL' for _, status, _ in results)
    print(f'\nPassed: {passed} | Failed: {failed} | Skipped: {skipped} | Manual: {manual_count}')
    if failed:
        print('Some checks failed. Review their output above.')
        return 1
    if manual_count:
        print('Automated checks passed; complete the manual IDE quality review separately.')
    else:
        print('All executed checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
