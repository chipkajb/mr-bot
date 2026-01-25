"""
Filters and prioritizes files for review.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from config import Config
from gitlab_fetcher import FileChange


@dataclass
class FilteredFile:
    """represents a file after filtering and analysis."""

    file_change: FileChange
    should_review: bool
    should_chunk: bool
    priority: str  # 'critical', 'normal', 'low'
    skip_reason: Optional[str] = None
    note_only: bool = False
    size_kb: float = 0.0
    line_count: int = 0


class FileFilter:
    """filters files and determines review priority."""

    def __init__(self):
        """initialize file filter."""
        self.skipped_files: List[Tuple[str, str]] = []  # (filepath, reason)

    def filter_files(self, file_changes: List[FileChange]) -> List[FilteredFile]:
        """filter and analyze file changes.

        Args:
            file_changes: list of file changes from MR

        Returns:
            list of filtered file objects ready for processing
        """
        filtered = []

        for file_change in file_changes:
            filepath = file_change.new_path or file_change.old_path

            # check if should skip
            if Config.should_skip_file(filepath):
                reason = self._get_skip_reason(filepath)
                self.skipped_files.append((filepath, reason))
                continue

            # check if note only
            note_only = Config.should_note_only(filepath)

            # calculate file size and line count
            size_kb = len(file_change.diff.encode("utf-8")) / 1024.0
            line_count = file_change.diff.count("\n")

            # determine if should chunk (based on line count and size)
            should_chunk = line_count > Config.CHUNK_SIZE_LINES or size_kb > Config.MAX_FILE_SIZE_KB

            # get priority
            priority = Config.get_file_priority(filepath)

            # determine if should review (skip if note_only or deleted)
            should_review = not note_only and file_change.status != "deleted"

            filtered_file = FilteredFile(
                file_change=file_change,
                should_review=should_review,
                should_chunk=should_chunk,
                priority=priority,
                note_only=note_only,
                size_kb=size_kb,
                line_count=line_count,
            )

            filtered.append(filtered_file)

            # track note-only files
            if note_only:
                self.skipped_files.append((filepath, "large data file (noted but not reviewed)"))

        return filtered

    def get_skipped_files(self) -> List[Tuple[str, str]]:
        """get list of skipped files with reasons."""
        return self.skipped_files

    @staticmethod
    def _get_skip_reason(filepath: str) -> str:
        """get human-readable reason for skipping a file."""
        if filepath.endswith(".lock") or "lock" in filepath.lower():
            return "lock file"
        elif ".min." in filepath.lower():
            return "minified file"
        elif any(pattern in filepath.lower() for pattern in ["dist/", "build/", "target/"]):
            return "build artifact"
        elif "__pycache__" in filepath or filepath.endswith((".pyc", ".pyo")):
            return "Python cache file"
        elif "_pb2.py" in filepath or ".generated." in filepath:
            return "generated code"
        elif filepath.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico")):
            return "image file"
        elif filepath.endswith((".pdf", ".zip", ".tar", ".gz")):
            return "binary/archive file"
        else:
            return "matches skip pattern"
