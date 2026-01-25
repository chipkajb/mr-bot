"""
Fetches merge request data from GitLab API or local git repository.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import gitlab
from git import Repo

from config import Config

logger = logging.getLogger(__name__)


@dataclass
class FileChange:
    """represents a single file change in a merge request."""

    old_path: str
    new_path: str
    diff: str
    status: str  # 'added', 'modified', 'deleted', 'renamed'
    additions: int
    deletions: int


@dataclass
class MRData:
    """represents merge request metadata and changes."""

    iid: str
    title: str
    author: str
    source_branch: str
    target_branch: str
    description: str
    web_url: str
    file_changes: List[FileChange]


class GitLabFetcher:
    """fetches MR data from GitLab API or local git repository."""

    def __init__(self, project_id: Optional[str] = None, token: Optional[str] = None, url: Optional[str] = None):
        """initialize GitLab fetcher.

        Args:
            project_id: GitLab project ID (required for MR fetching)
            token: GitLab access token (defaults to config)
            url: GitLab instance URL (defaults to config)
        """
        self.project_id = project_id
        self.token = token or Config.GITLAB_TOKEN
        self.url = url or Config.GITLAB_URL
        self.gitlab_client: Optional[gitlab.Gitlab] = None

        if self.token:
            try:
                self.gitlab_client = gitlab.Gitlab(self.url, private_token=self.token)
            except Exception as e:
                logger.warning(f"failed to initialize GitLab client: {e}")

    def fetch_mr(self, mr_iid: int) -> MRData:
        """fetch merge request data from GitLab API.

        Args:
            mr_iid: merge request IID (internal ID)

        Returns:
            MRData object with MR information and file changes

        Raises:
            ValueError: if GitLab client or project ID is not configured
        """
        if not self.gitlab_client:
            raise ValueError("GitLab token not configured. Use --branch for local git diff instead.")

        if not self.project_id:
            raise ValueError("GitLab project ID is required. Use --project-id to specify it.")

        project = self.gitlab_client.projects.get(self.project_id)
        mr = project.mergerequests.get(mr_iid)

        # get MR changes
        changes = mr.changes()

        file_changes = []
        for change in changes.get("changes", []):
            file_change = FileChange(
                old_path=change.get("old_path", ""),
                new_path=change.get("new_path", ""),
                diff=change.get("diff", ""),
                status=self._determine_status(change),
                additions=change.get("diff", "").count("\n+") - change.get("diff", "").count("\n+++"),
                deletions=change.get("diff", "").count("\n-") - change.get("diff", "").count("\n---"),
            )
            file_changes.append(file_change)

        return MRData(
            iid=str(mr_iid),
            title=mr.title,
            author=mr.author.get("name", "Unknown"),
            source_branch=mr.source_branch,
            target_branch=mr.target_branch,
            description=mr.description or "",
            web_url=mr.web_url,
            file_changes=file_changes,
        )

    def fetch_local_diff(self, source_branch: str, target_branch: str = "main") -> MRData:
        """fetch diff data from local git repository.

        Args:
            source_branch: source branch name
            target_branch: target branch name (default: 'main')

        Returns:
            MRData object with diff information and file changes
        """
        repo = self._get_repo()
        source_commit, target_commit = self._get_commits(repo, source_branch, target_branch)
        diff_index = target_commit.diff(source_commit, create_patch=True)
        file_changes = self._process_diff_items(diff_index)
        commit_message, author_name = self._extract_commit_info(source_commit, source_branch, target_branch)

        return MRData(
            iid=f"local_{source_branch}",
            title=commit_message,
            author=author_name,
            source_branch=source_branch,
            target_branch=target_branch,
            description=f"Local diff from {source_branch} to {target_branch}",
            web_url="",
            file_changes=file_changes,
        )

    @staticmethod
    def _get_repo() -> Repo:
        """get git repository instance."""
        try:
            return Repo(".", search_parent_directories=True)
        except Exception as e:
            raise ValueError(f"failed to initialize git repository: {e}") from e

    @staticmethod
    def _get_commits(repo: Repo, source_branch: str, target_branch: str) -> Tuple:
        """get source and target commits."""
        try:
            source_commit = repo.commit(source_branch)
            target_commit = repo.commit(target_branch)
            return source_commit, target_commit
        except Exception as e:
            raise ValueError(f"failed to find branches: {e}") from e

    @staticmethod
    def _process_diff_items(diff_index) -> List[FileChange]:
        """process diff items into file changes."""
        file_changes = []
        for diff_item in diff_index:
            old_path = diff_item.a_path if diff_item.a_path else ""
            new_path = diff_item.b_path if diff_item.b_path else ""

            # get diff text
            if diff_item.diff:
                if isinstance(diff_item.diff, bytes):
                    diff_text = diff_item.diff.decode("utf-8", errors="ignore")
                else:
                    diff_text = diff_item.diff
            else:
                diff_text = ""

            # determine status
            if diff_item.new_file:
                status = "added"
            elif diff_item.deleted_file:
                status = "deleted"
            elif diff_item.renamed_file:
                status = "renamed"
            else:
                status = "modified"

            # count additions and deletions
            additions = diff_text.count("\n+") - diff_text.count("\n+++")
            deletions = diff_text.count("\n-") - diff_text.count("\n---")

            file_change = FileChange(
                old_path=old_path,
                new_path=new_path,
                diff=diff_text,
                status=status,
                additions=additions,
                deletions=deletions,
            )
            file_changes.append(file_change)
        return file_changes

    @staticmethod
    def _extract_commit_info(source_commit, source_branch: str, target_branch: str) -> Tuple[str, str]:
        """extract commit message and author name."""
        if source_commit.message:
            if isinstance(source_commit.message, bytes):
                message_str = source_commit.message.decode("utf-8", errors="ignore")
            else:
                message_str = source_commit.message
            commit_message = message_str.split("\n")[0]
        else:
            commit_message = f"Diff: {source_branch} -> {target_branch}"
        author_name: str = (
            source_commit.author.name if source_commit.author and source_commit.author.name else "Unknown"
        )
        return commit_message, author_name

    @staticmethod
    def _determine_status(change: Dict) -> str:
        """determine file change status from GitLab change object."""
        if change.get("new_file", False):
            return "added"
        elif change.get("deleted_file", False):
            return "deleted"
        elif change.get("renamed_file", False):
            return "renamed"
        else:
            return "modified"
