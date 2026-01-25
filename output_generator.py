"""
Generates organized output files for Cursor agent review.
"""

from pathlib import Path
from typing import List, Optional

from config import Config
from diff_processor import DiffChunk
from file_filter import FilteredFile
from gitlab_fetcher import MRData


class OutputGenerator:
    """generates output files for review."""

    def __init__(self, output_dir: Optional[str] = None):
        """initialize output generator.

        Args:
            output_dir: output directory path (defaults to config)
        """
        self.output_dir = Path(output_dir or Config.DEFAULT_OUTPUT_DIR)
        self.diffs_dir = self.output_dir / "diffs"

    def generate_output(self, mr_data: MRData, filtered_files: List[FilteredFile], chunks: List[DiffChunk]) -> str:
        """generate all output files.

        Args:
            mr_data: merge request metadata
            filtered_files: list of filtered files
            chunks: list of diff chunks

        Returns:
            path to output directory
        """
        # create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.diffs_dir.mkdir(parents=True, exist_ok=True)

        # generate files
        self._generate_mr_info(mr_data)
        self._generate_review_prompt(mr_data, filtered_files, chunks)
        self._generate_skipped_files(filtered_files)
        self._generate_diff_files(chunks)

        return str(self.output_dir)

    def _generate_mr_info(self, mr_data: MRData):
        """generate MR metadata file."""
        info_path = self.output_dir / f"MR_{mr_data.iid}_info.md"

        content = f"""# Merge Request Information

## Basic Info
- **IID**: {mr_data.iid}
- **Title**: {mr_data.title}
- **Author**: {mr_data.author}
- **Source Branch**: `{mr_data.source_branch}`
- **Target Branch**: `{mr_data.target_branch}`
"""

        if mr_data.web_url:
            content += f"- **URL**: {mr_data.web_url}\n"

        if mr_data.description:
            content += f"\n## Description\n\n{mr_data.description}\n"

        with open(info_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(content)

    def _generate_review_prompt(self, mr_data: MRData, filtered_files: List[FilteredFile], chunks: List[DiffChunk]):
        """generate review prompt for Cursor agent."""
        prompt_path = self.output_dir / "review_prompt.md"

        # get files to review
        review_files = [f for f in filtered_files if f.should_review]
        critical_files = [f for f in review_files if f.priority == "critical"]
        normal_files = [f for f in review_files if f.priority == "normal"]
        low_files = [f for f in review_files if f.priority == "low"]

        # get chunk file paths
        chunk_files = []
        for chunk in chunks:
            filepath = chunk.filepath.replace("/", "__")
            filename = f"{filepath}_chunk_{chunk.chunk_number}.diff" if chunk.total_chunks > 1 else f"{filepath}.diff"
            chunk_files.append(f"diffs/{filename}")

        content = """# Code Review Instructions

## Role
You are a senior code reviewer with expertise in software engineering, security, performance, and best practices. Your role is to conduct a thorough, constructive review of the merge request changes.

## Review Guidelines

### What to Look For

1. **Bugs & Logic Errors**
   - Off-by-one errors, null pointer exceptions, unhandled edge cases
   - Incorrect conditionals, loop issues, state management problems
   - Race conditions, concurrency issues

2. **Security Issues**
   - SQL injection, XSS, CSRF vulnerabilities
   - Authentication/authorization flaws
   - Sensitive data exposure
   - Insecure dependencies or configurations

3. **Performance**
   - N+1 queries, inefficient algorithms
   - Missing indexes, unnecessary computations
   - Memory leaks, resource cleanup issues
   - Large file operations without streaming

4. **Maintainability**
   - Code duplication, magic numbers/strings
   - Poor naming, unclear intent
   - Missing or inadequate comments
   - Overly complex functions/classes

5. **Best Practices**
   - Error handling and logging
   - Input validation and sanitization
   - Testing considerations
   - Documentation and type hints

## Review Tag System

Use the following tags to categorize findings:

- **nitpick**: Minor style or formatting issues (e.g., spacing, naming conventions)
- **suggestion**: Improvement ideas that aren't critical (e.g., refactoring opportunities)
- **question**: Clarification needed (e.g., "Why was this approach chosen?")
- **concern**: Potential issues that need attention (e.g., unclear error handling)
- **issue**: Definite problems that should be fixed (e.g., bugs, missing validation)
- **critical**: Serious issues requiring immediate attention (e.g., data loss, security holes)
- **security**: Security-related concerns (e.g., authentication, data exposure)
- **performance**: Performance-related issues (e.g., slow queries, inefficient algorithms)
- **best-practice**: Violations of coding standards or best practices

### Tag Examples

- `[security]` - Missing input validation on user email field
- `[performance]` - N+1 query issue in user list endpoint
- `[issue]` - Null pointer exception possible when user is None
- `[suggestion]` - Consider extracting this logic into a helper function
- `[nitpick]` - Variable name `tmp` could be more descriptive

## Output Format

For each issue found, provide:

```markdown
### [tag] File: `path/to/file.py` (Line X)

**Issue**: Brief description of the issue

**Details**: More detailed explanation

**Suggested Fix**: Code example or explanation of how to fix

**Priority**: 1-5 (1 = low, 5 = critical)
```

## Files to Review

### Critical Priority Files
"""

        for f in critical_files:
            filepath = f.file_change.new_path or f.file_change.old_path
            content += f"- `{filepath}`\n"

        if normal_files:
            content += "\n### Normal Priority Files\n"
            for f in normal_files:
                filepath = f.file_change.new_path or f.file_change.old_path
                content += f"- `{filepath}`\n"

        if low_files:
            content += "\n### Low Priority Files\n"
            for f in low_files:
                filepath = f.file_change.new_path or f.file_change.old_path
                content += f"- `{filepath}`\n"

        content += """

## Diff Files

Review the following diff files in the `diffs/` directory:

"""

        for chunk_file in sorted(chunk_files):
            content += f"- `{chunk_file}`\n"

        content += """

## Review Process

1. Review each diff file systematically
2. Look for the issues mentioned in the guidelines above
3. Pay special attention to critical priority files
4. Provide structured feedback using the output format
5. Be constructive and educational in your feedback
6. Prioritize findings by severity and impact

## Notes

- Focus on code quality, security, and maintainability
- Consider the context of the changes (what problem is being solved?)
- Suggest improvements, not just point out problems
- If something is unclear, ask questions rather than making assumptions

Begin your review now. Review all diff files and provide your findings in the structured format above.
"""

        with open(prompt_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(content)

    def _generate_skipped_files(self, filtered_files: List[FilteredFile]):
        """generate skipped files documentation."""
        skipped_path = self.output_dir / "skipped_files.md"

        # collect skipped files
        skipped = []
        for f in filtered_files:
            if not f.should_review or f.note_only:
                filepath = f.file_change.new_path or f.file_change.old_path
                reason = f.skip_reason or ("noted but not reviewed" if f.note_only else "skipped")
                skipped.append((filepath, reason))

        content = "# Skipped Files\n\n"
        content += "The following files were excluded from AI review:\n\n"

        if not skipped:
            content += "No files were skipped.\n"
        else:
            content += "| File Path | Reason |\n"
            content += "|-----------|--------|\n"
            for filepath, reason in skipped:
                content += f"| `{filepath}` | {reason} |\n"

        with open(skipped_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(content)

    def _generate_diff_files(self, chunks: List[DiffChunk]):
        """generate individual diff files."""
        for chunk in chunks:
            # sanitize filepath for filename
            filepath = chunk.filepath.replace("/", "__").replace("\\", "__")

            filename = f"{filepath}_chunk_{chunk.chunk_number}.diff" if chunk.total_chunks > 1 else f"{filepath}.diff"

            diff_path = self.diffs_dir / filename

            # add chunk header
            header = f"# Diff: {chunk.filepath}"
            if chunk.total_chunks > 1:
                header += f" (Chunk {chunk.chunk_number} of {chunk.total_chunks})"
            header += f"\n# Lines {chunk.start_line}-{chunk.end_line}\n\n"

            content = header + chunk.content

            with open(diff_path, "w", encoding="utf-8") as file_handle:
                file_handle.write(content)
