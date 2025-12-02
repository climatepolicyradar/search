"""Tests for git utilities."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from search.config import get_git_commit_hash, get_git_root


@patch("search.config.subprocess.check_output")
def test_whether_get_git_root_returns_path_when_git_command_succeeds(mock_check_output):
    mock_check_output.return_value = "/path/to/repo\n"
    result = get_git_root()
    assert isinstance(result, Path)
    assert str(result) == "/path/to/repo"


@patch("search.config.subprocess.check_output")
def test_whether_get_git_root_calls_git_rev_parse_show_toplevel(mock_check_output):
    mock_check_output.return_value = "/path/to/repo\n"
    get_git_root()
    mock_check_output.assert_called_once_with(
        ["git", "rev-parse", "--show-toplevel"], universal_newlines=True
    )


@patch("search.config.subprocess.check_output")
def test_whether_get_git_root_strips_whitespace_from_git_output(mock_check_output):
    mock_check_output.return_value = "  /path/to/repo  \n"
    result = get_git_root()
    assert isinstance(result, Path)
    assert str(result) == "/path/to/repo"


@pytest.mark.parametrize(
    "exception",
    [subprocess.CalledProcessError(1, "git"), FileNotFoundError()],
    ids=["CalledProcessError", "FileNotFoundError"],
)
@patch("search.config.subprocess.check_output")
def test_whether_get_git_root_returns_fallback_path_when_git_command_fails(
    mock_check_output, exception
):
    mock_check_output.side_effect = exception
    with patch("search.config.__file__", "/some/path/to/search/config.py"):
        result = get_git_root()
        assert isinstance(result, Path)
        assert str(result) == str(Path("/some/path/to/search/config.py").parent.parent)


def test_whether_get_git_commit_hash_returns_environment_variable_when_set():
    with patch.dict(os.environ, {"GIT_COMMIT_HASH": "abc123"}):
        result = get_git_commit_hash()
        assert result == "abc123"


@patch("search.config.subprocess.check_output")
def test_whether_get_git_commit_hash_calls_git_and_returns_stripped_output_when_env_var_not_set(
    mock_check_output,
):
    mock_check_output.return_value = "  def456  \n"
    with patch.dict(os.environ, {}, clear=True):
        result = get_git_commit_hash()
        mock_check_output.assert_called_once_with(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        )
        assert result == "def456"


@pytest.mark.parametrize(
    "exception",
    [subprocess.CalledProcessError(1, "git"), FileNotFoundError()],
    ids=["CalledProcessError", "FileNotFoundError"],
)
@patch("search.config.subprocess.check_output")
def test_whether_get_git_commit_hash_returns_unknown_when_env_var_not_set_and_git_fails(
    mock_check_output, exception
):
    mock_check_output.side_effect = exception
    with patch.dict(os.environ, {}, clear=True):
        result = get_git_commit_hash()
        assert result == "unknown"


@patch("search.config.subprocess.check_output")
def test_whether_get_git_commit_hash_does_not_call_git_when_env_var_is_set(
    mock_check_output,
):
    with patch.dict(os.environ, {"GIT_COMMIT_HASH": "abc123"}):
        get_git_commit_hash()
        mock_check_output.assert_not_called()
