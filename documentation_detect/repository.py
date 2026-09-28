import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from git import Repo


def repository_name(url: str) -> str:
    path = urlsplit(url).path if "://" in url else url
    name = path.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    name = name.removesuffix(".git")
    if not re.fullmatch(r"[\w.-]+", name) or name in {".", ".."}:
        raise ValueError("Não foi possível obter um nome de repositório válido da URL.")
    return name


def refresh_repository(url: str, destination: Path, *, project_root: Path,
                       branch: str | None = None) -> Path:
    """Remove somente a pasta dedicada ao clone, depois clona a versão atual."""
    repository_name(url)
    destination = destination.absolute()
    project_root = project_root.resolve()
    if destination.is_symlink() or destination.resolve() != project_root / "resource":
        raise ValueError("A substituição do clone é permitida somente na pasta resource deste projeto.")
    if destination.exists():
        shutil.rmtree(destination)
    options = {"depth": 1}
    if branch:
        options["branch"] = branch
    Repo.clone_from(url, destination, **options)
    return destination
