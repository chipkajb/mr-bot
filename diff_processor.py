"""
Processes file diffs and chunks large files intelligently.
"""

from dataclasses import dataclass
from typing import List

from config import Config
from file_filter import FilteredFile


@dataclass
class DiffChunk:
    """represents a chunk of a diff file."""

    filepath: str
    chunk_number: int
    content: str
    start_line: int
    end_line: int
    total_chunks: int


class DiffProcessor:
    """processes diffs and creates chunks for large files."""

    def __init__(self):
        """initialize diff processor."""
        pass

    def process_file(self, filtered_file: FilteredFile) -> List[DiffChunk]:
        """process a filtered file into chunks if needed.

        Args:
            filtered_file: filtered file to process

        Returns:
            list of diff chunks (single chunk if file is small)
        """
        filepath = filtered_file.file_change.new_path or filtered_file.file_change.old_path
        diff_content = filtered_file.file_change.diff

        if not filtered_file.should_chunk:
            # return single chunk for small files
            return [
                DiffChunk(
                    filepath=filepath,
                    chunk_number=1,
                    content=diff_content,
                    start_line=1,
                    end_line=filtered_file.line_count,
                    total_chunks=1,
                )
            ]

        # chunk large files
        return self._chunk_diff(filepath, diff_content)

    def _chunk_diff(self, filepath: str, diff_content: str) -> List[DiffChunk]:
        """chunk a large diff into smaller pieces.

        Args:
            filepath: path to the file
            diff_content: full diff content

        Returns:
            list of diff chunks
        """
        lines = diff_content.split("\n")
        total_lines = len(lines)
        chunks = []
        chunk_size = Config.CHUNK_SIZE_LINES
        context_lines = Config.CONTEXT_LINES

        current_pos = 0
        chunk_num = 1

        while current_pos < total_lines:
            # determine chunk end
            chunk_end = min(current_pos + chunk_size, total_lines)

            # try to find a good breakpoint (function/class boundary or empty line)
            if chunk_end < total_lines:
                # look for breakpoint within last 50 lines of chunk
                search_start = max(chunk_end - 50, current_pos)
                breakpoint_pos = self._find_breakpoint(lines, search_start, chunk_end)
                if breakpoint_pos > current_pos:
                    chunk_end = breakpoint_pos

            # extract chunk lines
            chunk_lines = lines[current_pos:chunk_end]
            chunk_content = "\n".join(chunk_lines)

            # add context from next chunk if available
            if chunk_end < total_lines and context_lines > 0:
                next_context = lines[chunk_end : min(chunk_end + context_lines, total_lines)]
                if next_context:
                    chunk_content += "\n" + "\n".join(next_context)

            chunks.append(
                DiffChunk(
                    filepath=filepath,
                    chunk_number=chunk_num,
                    content=chunk_content,
                    start_line=current_pos + 1,
                    end_line=chunk_end,
                    total_chunks=0,  # will be set after all chunks are created
                )
            )

            current_pos = chunk_end
            chunk_num += 1

        # update total_chunks for all chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks

    @staticmethod
    def _find_breakpoint(lines: List[str], start: int, end: int) -> int:
        """find a good breakpoint in the diff (function/class boundary or empty line).

        Args:
            lines: list of diff lines
            start: start position to search from
            end: end position to search to

        Returns:
            best breakpoint position (or end if none found)
        """
        # look backwards from end for good breakpoints
        for i in range(end - 1, start - 1, -1):
            line = lines[i]
            stripped = line.strip()

            # empty line is a good breakpoint
            if not stripped:
                return i + 1

            # function/class definitions (common patterns)
            if stripped.startswith(("def ", "class ", "function ", "@")):
                return i + 1

            # closing braces/brackets
            if stripped in ("}", "]", ")"):
                return i + 1

        # no good breakpoint found, use end
        return end
