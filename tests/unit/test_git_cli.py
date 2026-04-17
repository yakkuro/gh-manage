"""Unit tests for git CLI subprocess transport and error handling.

Theme A (internal hygiene): ensure GitError includes stderr context.
Doctor relies on git errors surfacing actual git output instead of
a bare 'git command failed'.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from gh_manage.git_cli import (
    GitError,
    GitNotInstalledError,
    NotAGitRepoError,
    NoOriginRemoteError,
    UnsupportedOriginError,
    _raise_classified_git_error,
    _run_git,
    get_origin_owner_repo,
    parse_origin_url,
)


class TestGitErrorPreservesStderr:
    """GitError must carry stderr context (Theme A)."""

    def test_git_error_preserves_stderr(self):
        """Generic git failure includes stderr in exception message."""
        with pytest.raises(GitError) as exc_info:
            _raise_classified_git_error(
                stderr="fatal: something went wrong\n",
                returncode=128,
            )
        assert "something went wrong" in str(exc_info.value).lower()

    def test_not_a_git_repo_error_includes_stderr(self):
        """NotAGitRepoError includes stderr context."""
        with pytest.raises(NotAGitRepoError) as exc_info:
            _raise_classified_git_error(
                stderr="fatal: not a git repository (or any of the parent directories): .git",
                returncode=128,
            )
        exc_msg = str(exc_info.value)
        assert "not a git repository" in exc_msg.lower()
        assert "git exit 128" in exc_msg

    def test_no_origin_remote_error_includes_stderr(self):
        """NoOriginRemoteError includes stderr context."""
        with pytest.raises(NoOriginRemoteError) as exc_info:
            _raise_classified_git_error(
                stderr="error: No such remote 'origin'",
                returncode=1,
            )
        exc_msg = str(exc_info.value)
        assert "origin" in exc_msg.lower()

    def test_generic_git_error_truncates_long_stderr(self):
        """Generic GitError truncates very long stderr (300 char limit)."""
        long_stderr = "X" * 500  # Longer than 300 char limit
        with pytest.raises(GitError) as exc_info:
            _raise_classified_git_error(
                stderr=long_stderr,
                returncode=1,
            )
        exc_msg = str(exc_info.value)
        # Should contain truncated stderr, not the full 500 chars
        assert "XXXXX" in exc_msg  # Some of the X's are present
        assert len(exc_msg) < len(long_stderr) + 100  # Message is bounded


class TestGitNotInstalledError:
    """GitNotInstalledError when git CLI is missing."""

    def test_git_not_installed_error(self):
        """GitNotInstalledError raised when git command not found."""
        with patch(
            "gh_manage.git_cli.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            with pytest.raises(GitNotInstalledError) as exc_info:
                _run_git(["rev-parse", "HEAD"], cwd=Path("/tmp"))
            assert "git" in str(exc_info.value).lower()
            assert "path" in str(exc_info.value).lower()


class TestParseOriginUrl:
    """Parse git remote URLs into owner/repo form."""

    def test_https_github_com_url(self):
        """Parse HTTPS GitHub URL."""
        assert parse_origin_url("https://github.com/owner/repo") == "owner/repo"

    def test_https_github_com_url_with_git_suffix(self):
        """Parse HTTPS GitHub URL with .git suffix."""
        assert parse_origin_url("https://github.com/owner/repo.git") == "owner/repo"

    def test_ssh_github_com_url(self):
        """Parse explicit SSH GitHub URL."""
        assert parse_origin_url("ssh://git@github.com/owner/repo") == "owner/repo"

    def test_scp_form_github_com_url(self):
        """Parse SCP-form GitHub URL (git@host:path)."""
        assert parse_origin_url("git@github.com:owner/repo") == "owner/repo"

    def test_scp_form_github_com_url_with_git_suffix(self):
        """Parse SCP-form GitHub URL with .git suffix."""
        assert parse_origin_url("git@github.com:owner/repo.git") == "owner/repo"

    def test_ssh_github_com_alternate_port_443(self):
        """Parse SSH GitHub alternate hostname (ssh.github.com:443)."""
        assert (
            parse_origin_url("ssh://git@ssh.github.com:443/owner/repo") == "owner/repo"
        )

    def test_unsupported_scheme_raises_value_error(self):
        """Unsupported scheme raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_origin_url("git://github.com/owner/repo")
        assert "unsupported" in str(exc_info.value).lower()

    def test_non_github_host_raises_value_error(self):
        """Non-GitHub host raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_origin_url("https://gitlab.com/owner/repo")
        assert "github" in str(exc_info.value).lower()

    def test_malformed_path_raises_value_error(self):
        """Malformed path (not owner/repo) raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_origin_url("https://github.com/only-owner")
        assert "extract" in str(exc_info.value).lower()

    def test_invalid_characters_in_owner_raises_value_error(self):
        """Invalid characters in owner raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_origin_url("https://github.com/bad@owner/repo")
        assert "character" in str(exc_info.value).lower()

    def test_invalid_characters_in_repo_raises_value_error(self):
        """Invalid characters in repo raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_origin_url("https://github.com/owner/bad@repo")
        assert "character" in str(exc_info.value).lower()


class TestGetOriginOwnerRepo:
    """get_origin_owner_repo runs git and parses the URL."""

    def test_get_origin_owner_repo_success(self):
        """Successfully fetch and parse origin remote."""
        fake = subprocess.CompletedProcess(
            args=["git", "-C", "/repo", "remote", "get-url", "origin"],
            returncode=0,
            stdout="git@github.com:owner/repo.git\n",
            stderr="",
        )
        with patch("gh_manage.git_cli.subprocess.run", return_value=fake):
            result = get_origin_owner_repo(Path("/repo"))
            assert result == "owner/repo"

    def test_get_origin_owner_repo_not_a_git_repo(self):
        """NotAGitRepoError when target is not a git repo."""
        fake = subprocess.CompletedProcess(
            args=["git", "-C", "/tmp", "remote", "get-url", "origin"],
            returncode=128,
            stdout="",
            stderr="fatal: not a git repository (or any of the parent directories): .git",
        )
        with patch("gh_manage.git_cli.subprocess.run", return_value=fake):
            with pytest.raises(NotAGitRepoError):
                get_origin_owner_repo(Path("/tmp"))

    def test_get_origin_owner_repo_no_origin(self):
        """NoOriginRemoteError when origin remote is not configured."""
        fake = subprocess.CompletedProcess(
            args=["git", "-C", "/repo", "remote", "get-url", "origin"],
            returncode=1,
            stdout="",
            stderr="error: No such remote 'origin'",
        )
        with patch("gh_manage.git_cli.subprocess.run", return_value=fake):
            with pytest.raises(NoOriginRemoteError):
                get_origin_owner_repo(Path("/repo"))

    def test_get_origin_owner_repo_empty_url(self):
        """NoOriginRemoteError when origin URL is empty."""
        fake = subprocess.CompletedProcess(
            args=["git", "-C", "/repo", "remote", "get-url", "origin"],
            returncode=0,
            stdout="",
            stderr="",
        )
        with patch("gh_manage.git_cli.subprocess.run", return_value=fake):
            with pytest.raises(NoOriginRemoteError) as exc_info:
                get_origin_owner_repo(Path("/repo"))
            assert "empty" in str(exc_info.value).lower()

    def test_get_origin_owner_repo_unsupported_url(self):
        """UnsupportedOriginError when origin is not a GitHub URL."""
        fake = subprocess.CompletedProcess(
            args=["git", "-C", "/repo", "remote", "get-url", "origin"],
            returncode=0,
            stdout="https://gitlab.com/owner/repo.git\n",
            stderr="",
        )
        with patch("gh_manage.git_cli.subprocess.run", return_value=fake):
            with pytest.raises(UnsupportedOriginError):
                get_origin_owner_repo(Path("/repo"))
