import json
import os
import re
import shutil
import subprocess
from pathlib import Path

GITHUB_USER = os.environ["GITHUB_USER"]
AUTHOR_REGEX = os.environ["AUTHOR_REGEX"]

ROOT = Path.cwd()
WORKDIR = ROOT / ".loc-repos"
README = ROOT / "README.md"

START = "<!-- LOC-CHANGED:START -->"
END = "<!-- LOC-CHANGED:END -->"

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".kts", ".scala",
    ".html", ".css", ".scss", ".sass", ".sql", ".sh", ".bash", ".zsh",
    ".yml", ".yaml", ".json", ".xml", ".toml", ".ini"
}

SKIP_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "composer.lock",
}

SKIP_PATH_PARTS = {
    "node_modules",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
}


def run(cmd):
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def should_count_file(path_str):
    path = Path(path_str)

    if path.name in SKIP_FILENAMES:
        return False

    if any(part in SKIP_PATH_PARTS for part in path.parts):
        return False

    if path.suffix.lower() in CODE_EXTENSIONS:
        return True

    if path.name.lower() == "dockerfile":
        return True

    return False


def get_repos():
    output = run([
        "gh", "repo", "list", GITHUB_USER,
        "--limit", "1000",
        "--source",
        "--no-archived",
        "--json", "nameWithOwner"
    ])

    return [repo["nameWithOwner"] for repo in json.loads(output)]


def count_repo(repo):
    repo_dir = WORKDIR / repo.replace("/", "__")

    run([
        "gh", "repo", "clone", repo, str(repo_dir),
        "--",
        "--bare",
        "--quiet"
    ])

    log = run([
        "git", "-C", str(repo_dir),
        "log",
        "--all",
        "--numstat",
        f"--author={AUTHOR_REGEX}",
        "--pretty=tformat:"
    ])

    added = 0
    deleted = 0

    for line in log.splitlines():
        parts = line.split("\t")

        if len(parts) < 3:
            continue

        a, d, path = parts[0], parts[1], parts[2]

        if a == "-" or d == "-":
            continue

        if not should_count_file(path):
            continue

        added += int(a)
        deleted += int(d)

    return added, deleted


def update_readme(added, deleted):
    new_block = f"""**Lines Added:** {added:,}  
**Lines Deleted:** {deleted:,}
"""

    text = README.read_text(encoding="utf-8")

    pattern = re.compile(
        rf"{re.escape(START)}.*?{re.escape(END)}",
        re.DOTALL
    )

    replacement = f"{START}\n{new_block}{END}"

    if not pattern.search(text):
        raise RuntimeError("README markers not found.")

    README.write_text(pattern.sub(replacement, text), encoding="utf-8")


def main():
    if WORKDIR.exists():
        shutil.rmtree(WORKDIR)

    WORKDIR.mkdir()

    repos = get_repos()

    total_added = 0
    total_deleted = 0

    for repo in repos:
        try:
            added, deleted = count_repo(repo)
            total_added += added
            total_deleted += deleted
            print(f"{repo}: +{added} -{deleted}")
        except subprocess.CalledProcessError as e:
            print(f"Skipping {repo}: {e.stderr}")

    update_readme(total_added, total_deleted)

    shutil.rmtree(WORKDIR)


if __name__ == "__main__":
    main()