"""File boundaries apply to both model results and interrupted local writes."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import pipeline
from scripts.errors import InputDataError
from scripts.safe_files import atomic_writer, confined_path


def test_file_boundary_rejects_a_sibling_with_a_similar_name(tmp_path):
    root = tmp_path / 'runs'
    with pytest.raises(ValueError, match='configured directory'):
        confined_path(root, tmp_path / 'runs-private' / 'secret.json')
    assert confined_path(root, Path('job/result.json')) == root / 'job/result.json'


def test_model_output_stays_json_data_even_when_it_contains_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, 'RUNS_DIR', tmp_path / 'runs')
    target = pipeline.RUNS_DIR / 'job' / 'result.json'
    response = {'source_path': '../../private.json', 'reason': 'C:\\private\\secret; $HOME; é'}

    pipeline.save_json(target, response)

    assert pipeline.read_json(target) == response
    assert list(target.parent.iterdir()) == [target]
    assert not (tmp_path / 'private.json').exists()


def test_json_cannot_read_or_write_outside_the_runs_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, 'RUNS_DIR', tmp_path / 'runs')
    outside = tmp_path / 'private' / 'result.json'

    with pytest.raises(InputDataError, match='runs directory'):
        pipeline.save_json(outside, {'result': 'unsafe'})
    with pytest.raises(InputDataError, match='runs directory'):
        pipeline.read_json(outside)

    assert not outside.parent.exists()


def test_incomplete_json_does_not_replace_a_previous_result(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, 'RUNS_DIR', tmp_path)
    target = tmp_path / 'result.json'
    pipeline.save_json(target, {'status': 'complete'})

    with pytest.raises(TypeError):
        pipeline.save_json(target, {'invalid': object()})

    assert pipeline.read_json(target) == {'status': 'complete'}
    assert list(tmp_path.iterdir()) == [target]


def test_failed_binary_copy_preserves_the_destination_and_removes_the_temp_file(tmp_path):
    target = tmp_path / 'mapping.xlsx'
    target.write_bytes(b'previous workbook')

    with pytest.raises(OSError, match='interrupted'):
        with atomic_writer(target, binary=True) as handle:
            handle.write(b'partial workbook')
            raise OSError('copy interrupted')

    assert target.read_bytes() == b'previous workbook'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('directory_link', [True, False])
def test_run_files_cannot_follow_symlinks_outside_the_runs_directory(tmp_path, monkeypatch, directory_link):
    root = tmp_path / 'runs'
    root.mkdir()
    outside = tmp_path / 'private'
    outside.mkdir()
    secret = outside / 'secret.json'
    secret.write_text('{"secret": true}')
    link = root / ('job' if directory_link else 'result.json')
    try:
        link.symlink_to(outside if directory_link else secret, target_is_directory=directory_link)
    except OSError as error:
        pytest.skip(f'This machine cannot create symlinks: {error}')
    monkeypatch.setattr(pipeline, 'RUNS_DIR', root)
    target = link / 'secret.json' if directory_link else link

    with pytest.raises(InputDataError):
        pipeline.read_json(target)
    with pytest.raises(InputDataError):
        pipeline.save_json(target, {'overwrite': True})

    assert secret.read_text() == '{"secret": true}'
