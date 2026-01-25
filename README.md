# MR Bot

A Python tool that extracts GitLab merge request diffs and prepares them for review by a Cursor AI agent. The tool generates organized diff files and a comprehensive prompt file that can be fed directly to Cursor's agent mode.

## Features

- **Dual Source Support**: Fetch MRs from GitLab API or use local git repository diffs
- **Intelligent File Filtering**: Automatically skips lock files, build artifacts, generated code, and binaries
- **Smart Chunking**: Splits large files into reviewable chunks at logical breakpoints
- **Priority-Based Organization**: Categorizes files by priority (critical, normal, low)
- **Comprehensive Review Prompt**: Generates detailed instructions for AI code review
- **Structured Output**: Creates organized directory structure ready for Cursor agent

## Installation

1. Clone or download this repository
2. Install dependencies using `uv`:

```bash
uv sync
```

Or if you prefer to install globally:

```bash
uv pip install -r requirements.txt
```

1. (Optional) Create a `.env` file with your GitLab credentials:

```bash
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your_token_here
```

## Usage

### Using GitLab API

Fetch a merge request by IID:

```bash
# Using uv (recommended)
uv run main.py --mr 42

# Or with python directly (after uv sync)
python main.py --mr 42
```

### Using Local Git Repository

Compare two branches locally:

```bash
uv run main.py --branch feature/new-feature --target main
```

### Custom Output Directory

Specify a custom output directory:

```bash
uv run main.py --mr 42 --output ./review_output
```

### Command Line Options

```text
--mr MR_ID              GitLab merge request IID (requires GitLab token and project ID)
--branch BRANCH          Source branch for local git diff
--target TARGET          Target branch for local git diff (default: main)
--output OUTPUT_DIR      Output directory (default: ./output)
--project-id PROJECT_ID  GitLab project ID (required when using --mr)
--token TOKEN            GitLab access token (overrides env var)
--url URL                GitLab instance URL (overrides env var)
```

## Output Structure

The tool generates the following structure:

```text
output/
├── MR_<iid>_info.md          # MR metadata (title, author, branches, etc.)
├── review_prompt.md           # Comprehensive instructions for Cursor agent
├── skipped_files.md           # List of files skipped with reasons
└── diffs/
    ├── src__main.py.diff
    ├── src__utils.py_chunk_1.diff
    ├── src__utils.py_chunk_2.diff
    └── ...
```

## Workflow

1. **Run the tool**: `uv run main.py --mr 42` or `uv run main.py --branch feature/x`
2. **Review the output**: Check the generated files in the output directory
3. **Open Cursor agent mode**: In Cursor, open the agent mode
4. **Provide files**: Give the agent:
   - The `review_prompt.md` file
   - The entire `diffs/` directory
5. **Get review**: The agent will review all diffs and output structured findings
6. **Save results**: Save the agent's output as your final review report

## File Filtering

The tool automatically skips:

- **Lock files**: `package-lock.json`, `yarn.lock`, `poetry.lock`, etc.
- **Build artifacts**: `dist/`, `build/`, `target/`, `*.min.js`, etc.
- **Generated code**: `*_pb2.py`, `*.generated.*`, etc.
- **Binaries**: Images, PDFs, archives, fonts, etc.
- **Large data files**: CSV, TSV, Parquet (noted but not reviewed)

## Chunking

Large files (>300 lines or >500KB) are automatically chunked at logical breakpoints:

- Function/class definitions
- Empty lines
- Closing braces/brackets

Each chunk includes context lines for continuity.

## Review Tags

The generated review prompt uses these tags:

- `nitpick` - Minor style issues
- `suggestion` - Improvement ideas
- `question` - Clarification needed
- `concern` - Potential issues
- `issue` - Definite problems
- `critical` - Serious issues
- `security` - Security concerns
- `performance` - Performance issues
- `best-practice` - Coding standards violations

## Configuration

You can configure the tool via environment variables:

- `GITLAB_URL` - GitLab instance URL (default: <https://gitlab.com>)
- `GITLAB_TOKEN` - GitLab access token
- `MAX_FILE_SIZE_KB` - Maximum file size before chunking (default: 500)
- `CHUNK_SIZE_LINES` - Lines per chunk (default: 300)
- `CONTEXT_LINES` - Context lines between chunks (default: 5)
- `DEFAULT_OUTPUT_DIR` - Default output directory (default: ./output)

## Examples

### Review a GitLab MR

```bash
export GITLAB_TOKEN=glpat-xxxxx
uv run main.py --mr 42 --project-id 12345
```

### Review local branch changes

```bash
uv run main.py --branch feature/auth-improvements --target main
```

### Custom output location

```bash
uv run main.py --branch feature/new-api --output ~/reviews/mr_123
```

## Requirements

- Python 3.11+
- `uv` (recommended) or `pip`
- Dependencies (managed via `pyproject.toml` or `requirements.txt`):
  - `python-gitlab>=3.15.0`
  - `gitpython>=3.1.40`
  - `python-dotenv>=1.0.0`

## Project Structure

```text
mr-bot/
├── pyproject.toml            # Project configuration and dependencies (uv)
├── requirements.txt          # Python dependencies (alternative)
├── config.py                 # Configuration and file patterns
├── gitlab_fetcher.py         # GitLab API and git diff fetching
├── file_filter.py            # File filtering and prioritization
├── diff_processor.py          # Diff chunking logic
├── output_generator.py        # Output file generation
├── main.py                   # CLI entry point
└── README.md                 # This file
```

## License

This project is provided as-is for use in code review workflows.

## Contributing

Feel free to submit issues or pull requests for improvements!
