"""MkDocs hook — resolve repo identity from git remote at build time.

When someone forks and clones, all %%PLACEHOLDER%% tokens in site/ docs
are automatically replaced with the correct GitHub owner/repo URLs.
No manual editing required.
"""

import os
import re
import subprocess


def _resolve_repo():
    """Return (owner, repo) from GITHUB_REPOSITORY env, git remote, or fallback."""
    gh_repo = os.environ.get("GITHUB_REPOSITORY")
    if gh_repo and "/" in gh_repo:
        return gh_repo.split("/", 1)

    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if "github.com" in url:
            repo = re.sub(r".*github\.com[:/]", "", url).rstrip("/").removesuffix(".git")
            if "/" in repo:
                return repo.split("/", 1)
    except Exception:
        pass

    return "adibirzu", "octo-apm-demo"


_owner, _repo = _resolve_repo()

_VARS = {
    "%%GITHUB_REPO_URL%%": f"https://github.com/{_owner}/{_repo}",
    "%%GITHUB_PAGES_URL%%": f"https://{_owner}.github.io/{_repo}",
    "%%SHOP_REPO_URL%%": f"https://github.com/{_owner}/octo-drone-shop",
    "%%SHOP_PAGES_URL%%": f"https://{_owner}.github.io/octo-drone-shop",
    "%%CRM_REPO_URL%%": f"https://github.com/{_owner}/enterprise-crm-portal",
    "%%GITHUB_OWNER%%": _owner,
    "%%GITHUB_REPO%%": _repo,
}


def on_page_markdown(markdown, **kwargs):
    """Replace %%PLACEHOLDER%% tokens with resolved values."""
    for placeholder, value in _VARS.items():
        markdown = markdown.replace(placeholder, value)
    return markdown
