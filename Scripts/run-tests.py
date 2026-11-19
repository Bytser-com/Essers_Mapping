#!/usr/bin/env python3
"""Run all project tests and code checks on Windows, Linux, or macOS.

Run from the repository root:

    Windows:
        python Scripts/run-tests.py
        python Scripts/run-tests.py --skip-e2e
        python Scripts/run-tests.py --only-e2e

    Linux/macOS:
        python3 Scripts/run-tests.py
        python3 Scripts/run-tests.py --skip-e2e
        python3 Scripts/run-tests.py --only-e2e

Requires Python, Java 21, Node.js and npm.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == 'nt'


def java_command(directory: str) -> list[str]:
    """Use the project's Maven wrapper on the current operating system."""
    if IS_WINDOWS:
        return [str(ROOT / directory / 'mvnw.cmd'), 'clean', 'verify']
    # Wrapper scripts in ZIP archives often lose their executable permission.
    return ['bash', './mvnw', 'clean', 'verify']


def npm_command(*arguments: str) -> list[str]:
    return ['npm.cmd' if IS_WINDOWS else 'npm', *arguments]


def run_check(name: str, directory: str, command: list[str], results: list[tuple[str, str, str]]) -> bool:
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


def skip(name: str, reason: str, results: list[tuple[str, str, str]]) -> None:
    print(f'SKIP: {name} ({reason})')
    results.append((name, 'SKIP', reason))


def run_frontend_e2e(results: list[tuple[str, str, str]], *, build_passed: bool) -> None:
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
    parser.add_argument('--skip-e2e', '-SkipE2E', action='store_true',
                        help='Skip browser-based Playwright tests')
    parser.add_argument('--only-e2e', '-OnlyE2E', action='store_true',
                        help='Only run frontend build + Playwright tests')
    args = parser.parse_args(argv)
    if args.skip_e2e and args.only_e2e:
        parser.error('--skip-e2e and --only-e2e cannot be used together')

    print('Essers_Mapping - Full local test suite')
    print(f'Repository: {ROOT}')
    print(f'Platform:   {sys.platform}')
    results: list[tuple[str, str, str]] = []

    if not args.only_e2e:
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

    build_passed = run_check('Frontend - production build', 'Frontend',
                             npm_command('run', 'build'), results)
    if args.skip_e2e:
        skip('Frontend - Playwright E2E', 'Requested --skip-e2e', results)
    else:
        run_frontend_e2e(results, build_passed=build_passed)

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
    print(f'\nPassed: {passed} | Failed: {failed} | Skipped: {skipped}')
    if failed:
        print('Some checks failed. Review their output above.')
        return 1
    print('All executed checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
