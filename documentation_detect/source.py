import os
from pathlib import Path

from .models import SourceFile


IGNORED_DIRECTORIES = {".git", ".idea", ".gradle", "target", "build", "out",
                       "node_modules", "test", "tests", "generated", "generated-sources"}
EXTENSIONS = {".java", ".sql", ".properties", ".yaml", ".yml"}


def read_sources(repository: Path) -> list[SourceFile]:
    """Lê src/main de todos os módulos, sem seguir links simbólicos."""
    files = []
    for directory, subdirectories, filenames in os.walk(repository, followlinks=False):
        subdirectories[:] = sorted(name for name in subdirectories
                                   if name not in IGNORED_DIRECTORIES
                                   and not Path(directory, name).is_symlink())
        directory = Path(directory)
        relative = directory.relative_to(repository)
        parts = relative.parts
        roots = [index for index in range(len(parts) - 1)
                 if parts[index:index + 2] == ("src", "main")]
        if not roots:
            continue
        main_root = repository.joinpath(*parts[:roots[-1] + 2])
        for name in sorted(filenames):
            path = directory / name
            if path.suffix.lower() in EXTENSIONS and not path.is_symlink():
                raw = path.read_bytes()
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                files.append(SourceFile(path, main_root, text))
    return files
