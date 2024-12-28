import logging
import re

from github import Github
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings

site_domain = "sqlmodel.tiangolo.com"


class Settings(BaseSettings):
    github_repository: str
    github_token: SecretStr
    deploy_url: str | None = None
    commit_sha: str
    run_id: int
    is_done: bool = False


class LinkData(BaseModel):
    previous_link: str
    preview_link: str


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()

    logging.info(f"Using config: {settings.model_dump_json()}")
    g = Github(settings.github_token.get_secret_value())
    repo = g.get_repo(settings.github_repository)
    use_pr = next(
        (pr for pr in repo.get_pulls() if pr.head.sha == settings.commit_sha), None
    )
    if not use_pr:
        logging.error(f"No PR found for hash: {settings.commit_sha}")
        return
    commits = list(use_pr.get_commits())
    current_commit = [c for c in commits if c.sha == settings.commit_sha][0]
    run_url = f"https://github.com/{settings.github_repository}/actions/runs/{settings.run_id}"
    if settings.is_done and not settings.deploy_url:
        current_commit.create_status(
            state="success",
            description="No Docs Changes",
            context="deploy-docs",
            target_url=run_url,
        )
        logging.info("No docs changes found")
        return
    if not settings.deploy_url:
        current_commit.create_status(
            state="pending",
            description="Deploying Docs",
            context="deploy-docs",
            target_url=run_url,
        )
        logging.info("No deploy URL available yet")
        return
    current_commit.create_status(
        state="success",
        description="Docs Deployed",
        context="deploy-docs",
        target_url=run_url,
    )

    files = list(use_pr.get_files())
    docs_files = [f for f in files if f.filename.startswith("docs/")]

    deploy_url = settings.deploy_url.rstrip("/")
    links: list[LinkData] = []
    for f in docs_files:
        match = re.match(r"docs/(.*)", f.filename)
        if not match:
            continue
        path = match.group(1)
        if path.endswith("index.md"):
            use_path = path.replace("index.md", "")
        else:
            use_path = path.replace(".md", "/")
        link = LinkData(
            previous_link=f"https://{site_domain}/{use_path}",
            preview_link=f"{deploy_url}/{use_path}",
        )
        links.append(link)
        links.sort(key=lambda x: x.preview_link)

    message = f"📝 Docs preview for commit {settings.commit_sha} at: {deploy_url}"

    if links:
        message += "\n\n### Modified Pages\n\n"
        for link in links:
            message += f"* {link.preview_link}"
            message += f" - ([before]({link.previous_link}))"
            message += "\n"

    print(message)
    use_pr.as_issue().create_comment(message)

    logging.info("Finished")


if __name__ == "__main__":
    main()