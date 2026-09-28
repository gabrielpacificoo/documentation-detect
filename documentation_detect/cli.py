import argparse
import logging
from pathlib import Path

import yaml
from git.exc import GitCommandError

from .analyzer import analyze
from .report import write_report
from .repository import refresh_repository, repository_name


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPOSITORY = "https://github.com/Projeto-de-extencao-Grupo-3/back-end"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Documenta dependências de um repositório Spring Boot.")
    parser.add_argument("repository", nargs="?", default=DEFAULT_REPOSITORY,
                        help="URL Git; padrão: repositório do laboratório")
    parser.add_argument("--branch", help="Branch ou tag a clonar; padrão: branch padrão do remoto")
    parser.add_argument("--profile", help="Perfil Spring, ou perfis separados por vírgula")
    parser.add_argument("--dialect", choices=["mysql"], default="mysql")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        service = repository_name(args.repository)
        print("Substituindo resource/ por um clone atualizado...", flush=True)
        repository = refresh_repository(args.repository, PROJECT_ROOT / "resource",
                                        project_root=PROJECT_ROOT, branch=args.branch)
        findings = analyze(repository, profile=args.profile, dialect=args.dialect)
        output = write_report(findings, service, PROJECT_ROOT)
    except GitCommandError:
        logging.error("Falha ao clonar o repositório. Verifique URL, autenticação, rede e branch.")
        return 1
    except (OSError, ValueError, yaml.YAMLError) as error:
        logging.error("Não foi possível gerar o relatório (%s).", type(error).__name__)
        return 1
    print(f"Relatório: {output}")
    print(f"{len(findings.microsservicos)} microsserviços, {len(findings.tabelas)} tabelas, "
          f"{len(findings.procedures)} procedures.")
    return 0
