"""
Configuration settings for MR Bot.
Defines file patterns, size thresholds, and review tags.
"""

import os
import re
from typing import List, Pattern


class Config:
    """Configuration class for MR Bot settings."""

    # file skip patterns (regex)
    SKIP_PATTERNS: List[Pattern[str]] = [
        # lock files
        re.compile(r".*\.lock$"),
        re.compile(r"package-lock\.json$"),
        re.compile(r"yarn\.lock$"),
        re.compile(r"poetry\.lock$"),
        re.compile(r"Pipfile\.lock$"),
        re.compile(r"composer\.lock$"),
        re.compile(r"Gemfile\.lock$"),
        re.compile(r"Cargo\.lock$"),
        # build artifacts
        re.compile(r".*\.min\.(js|css)$"),
        re.compile(r".*dist/.*"),
        re.compile(r".*build/.*"),
        re.compile(r".*target/.*"),
        re.compile(r".*\.egg-info/.*"),
        re.compile(r".*__pycache__/.*"),
        re.compile(r".*\.pyc$"),
        re.compile(r".*\.pyo$"),
        # generated code
        re.compile(r".*_pb2\.py$"),
        re.compile(r".*\.generated\..*"),
        re.compile(r".*\.pb\.go$"),
        re.compile(r".*\.pb\.js$"),
        # binaries and media
        re.compile(r".*\.(png|jpg|jpeg|gif|svg|ico|webp|bmp)$"),
        re.compile(r".*\.(pdf|zip|tar|gz|bz2|xz)$"),
        re.compile(r".*\.(mp3|mp4|avi|mov|wmv)$"),
        re.compile(r".*\.(woff|woff2|ttf|eot|otf)$"),
    ]

    # files to note but skip AI review (large data files)
    NOTE_ONLY_PATTERNS: List[Pattern[str]] = [
        re.compile(r".*\.csv$"),
        re.compile(r".*\.tsv$"),
        re.compile(r".*\.json\.gz$"),
        re.compile(r".*\.parquet$"),
    ]

    # critical path patterns (higher priority)
    CRITICAL_PATTERNS: List[Pattern[str]] = [
        re.compile(r".*auth.*", re.IGNORECASE),
        re.compile(r".*security.*", re.IGNORECASE),
        re.compile(r".*api.*", re.IGNORECASE),
        re.compile(r".*middleware.*", re.IGNORECASE),
        re.compile(r".*config.*", re.IGNORECASE),
        re.compile(r".*settings.*", re.IGNORECASE),
        re.compile(r".*database.*", re.IGNORECASE),
        re.compile(r".*db.*", re.IGNORECASE),
    ]

    # size thresholds
    MAX_FILE_SIZE_KB: int = int(os.getenv("MAX_FILE_SIZE_KB", "500"))
    CHUNK_SIZE_LINES: int = int(os.getenv("CHUNK_SIZE_LINES", "300"))
    CONTEXT_LINES: int = int(os.getenv("CONTEXT_LINES", "5"))

    # review tags
    REVIEW_TAGS: List[str] = [
        "nitpick",
        "suggestion",
        "question",
        "concern",
        "issue",
        "critical",
        "security",
        "performance",
        "best-practice",
    ]

    # gitlab configuration
    GITLAB_URL: str = os.getenv("GITLAB_URL", "https://gitlab.com")
    GITLAB_TOKEN: str = os.getenv("GITLAB_TOKEN", "")

    # output configuration
    DEFAULT_OUTPUT_DIR: str = os.getenv("DEFAULT_OUTPUT_DIR", "./output")

    @classmethod
    def should_skip_file(cls, filepath: str) -> bool:
        """check if a file should be skipped entirely."""
        return any(pattern.match(filepath) for pattern in cls.SKIP_PATTERNS)

    @classmethod
    def should_note_only(cls, filepath: str) -> bool:
        """check if a file should be noted but not reviewed by AI."""
        return any(pattern.match(filepath) for pattern in cls.NOTE_ONLY_PATTERNS)

    @classmethod
    def is_critical_path(cls, filepath: str) -> bool:
        """check if a file is in a critical path (higher priority)."""
        return any(pattern.match(filepath) for pattern in cls.CRITICAL_PATTERNS)

    @classmethod
    def get_file_priority(cls, filepath: str) -> str:
        """get priority level for a file: 'critical', 'normal', or 'low'."""
        if cls.is_critical_path(filepath):
            return "critical"
        # test files are lower priority
        if "test" in filepath.lower() or "spec" in filepath.lower():
            return "low"
        return "normal"
