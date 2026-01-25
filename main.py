#!/usr/bin/env python3
"""
Main entry point for MR Bot.
Fetches merge request diffs and prepares them for Cursor AI agent review.
"""

from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

# load environment variables before importing Config
load_dotenv()

from config import Config
from diff_processor import DiffProcessor
from file_filter import FileFilter
from gitlab_fetcher import GitLabFetcher, MRData
from output_generator import OutputGenerator

# configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _print_summary(mr_data: MRData, review_files: list, skipped_count: int, all_chunks: list, output_path: str):
    """print summary of review preparation."""
    logger.info("\n%s", "=" * 70)
    logger.info("MR Bot: Review Preparation Complete")
    logger.info("=" * 70)
    logger.info(f"\nOutput directory: {output_path}")
    logger.info("\nFiles generated:")
    logger.info(f"  - MR_{mr_data.iid}_info.md (MR metadata)")
    logger.info("  - review_prompt.md (instructions for Cursor agent)")
    logger.info("  - skipped_files.md (list of excluded files)")
    logger.info(f"  - diffs/ (directory with {len(all_chunks)} diff files)")

    logger.info("\nStatistics:")
    logger.info(f"  - Total file changes: {len(mr_data.file_changes)}")
    logger.info(f"  - Files to review: {len(review_files)}")
    logger.info(f"  - Files skipped: {skipped_count}")
    logger.info(f"  - Diff files created: {len(all_chunks)}")

    # priority breakdown
    critical = len([f for f in review_files if f.priority == "critical"])
    normal = len([f for f in review_files if f.priority == "normal"])
    low = len([f for f in review_files if f.priority == "low"])

    if critical > 0 or normal > 0 or low > 0:
        logger.info("\nPriority breakdown:")
        if critical > 0:
            logger.info(f"  - Critical: {critical}")
        if normal > 0:
            logger.info(f"  - Normal: {normal}")
        if low > 0:
            logger.info(f"  - Low: {low}")

    logger.info("\nNext steps:")
    logger.info("  1. Open Cursor agent mode")
    logger.info("  2. Provide the review_prompt.md file to the agent")
    logger.info("  3. Include the entire diffs/ directory")
    logger.info("  4. Let the agent review and generate findings")
    logger.info("%s\n", "=" * 70)


def main():
    """main entry point."""
    parser = argparse.ArgumentParser(
        description="MR Bot: Prepare GitLab merge requests for AI code review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch MR from GitLab API
  python main.py --mr 42

  # Use local git diff
  python main.py --branch feature/new-thing --target main

  # Custom output directory
  python main.py --mr 42 --output ./review_output
        """,
    )

    # MR source options (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--mr", type=int, help="GitLab merge request IID (requires GITLAB_TOKEN and --project-id)"
    )
    source_group.add_argument("--branch", type=str, help="Source branch name for local git diff")

    parser.add_argument(
        "--target", type=str, default="main", help="Target branch name for local git diff (default: main)"
    )

    parser.add_argument(
        "--output", type=str, default=None, help=f"Output directory (default: {Config.DEFAULT_OUTPUT_DIR})"
    )

    parser.add_argument("--project-id", type=str, default=None, help="GitLab project ID (required when using --mr)")

    parser.add_argument("--token", type=str, default=None, help="GitLab access token (overrides GITLAB_TOKEN env var)")

    parser.add_argument("--url", type=str, default=None, help="GitLab instance URL (overrides GITLAB_URL env var)")

    args = parser.parse_args()

    try:
        # initialize components
        fetcher = GitLabFetcher(project_id=args.project_id, token=args.token, url=args.url)

        filter_obj = FileFilter()
        processor = DiffProcessor()
        output_dir = args.output or Config.DEFAULT_OUTPUT_DIR
        generator = OutputGenerator(output_dir=output_dir)

        # fetch MR data
        logger.info("Fetching merge request data...")
        if args.mr:
            if not args.project_id:
                raise ValueError("--project-id is required when using --mr option")
            logger.info(f"Fetching MR #{args.mr} from GitLab API")
            mr_data = fetcher.fetch_mr(args.mr)
        else:
            logger.info(f"Fetching local diff: {args.branch} -> {args.target}")
            mr_data = fetcher.fetch_local_diff(args.branch, args.target)

        logger.info(f"Found {len(mr_data.file_changes)} file changes")

        # filter files
        logger.info("Filtering files...")
        filtered_files = filter_obj.filter_files(mr_data.file_changes)
        review_files = [f for f in filtered_files if f.should_review]
        skipped_count = len(filter_obj.get_skipped_files())

        logger.info(f"Files to review: {len(review_files)}")
        logger.info(f"Files skipped: {skipped_count}")

        # process diffs
        logger.info("Processing diffs...")
        all_chunks = []
        chunk_count = 0

        for filtered_file in filtered_files:
            if filtered_file.should_review:
                chunks = processor.process_file(filtered_file)
                all_chunks.extend(chunks)
                if len(chunks) > 1:
                    chunk_count += len(chunks)
                    logger.info(
                        f"  Chunked {filtered_file.file_change.new_path or filtered_file.file_change.old_path} into {len(chunks)} chunks"
                    )

        logger.info(f"Total diff files created: {len(all_chunks)}")
        if chunk_count > 0:
            logger.info(f"  ({chunk_count} chunks from large files)")

        # generate output
        logger.info(f"Generating output in {output_dir}...")
        output_path = generator.generate_output(mr_data, filtered_files, all_chunks)

        # print summary
        _print_summary(mr_data, review_files, skipped_count, all_chunks, output_path)

    except ValueError as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected error")
        sys.exit(1)


if __name__ == "__main__":
    main()
