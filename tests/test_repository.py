import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from git import Actor, Repo

from documentation_detect.cli import main
from documentation_detect.repository import refresh_repository, repository_name


class RepositoryTests(unittest.TestCase):
    def test_names_from_https_and_ssh(self):
        self.assertEqual(repository_name("https://github.com/team/service.git"), "service")
        self.assertEqual(repository_name("git@github.com:team/service.git"), "service")
        self.assertEqual(repository_name("ssh://git@host/team/service.git"), "service")

    def test_refuses_deleting_project_or_other_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for destination in (root, root / "other", root.parent):
                with self.assertRaises(ValueError):
                    refresh_repository("https://example.com/repo", destination, project_root=root)
            self.assertTrue(root.exists())

    def test_refuses_symlink_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "other").mkdir()
            (root / "resource").symlink_to(root / "other", target_is_directory=True)
            with self.assertRaises(ValueError):
                refresh_repository("https://example.com/repo", root / "resource", project_root=root)
            self.assertTrue((root / "other").exists())

    def test_cli_reclones_latest_commit_and_writes_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "lab-service"
            remote.mkdir()
            repo = Repo.init(remote)
            actor = Actor("Test", "test@example.invalid")
            source = remote / "src/main/resources/PSEL_LOCAL.sql"
            source.parent.mkdir(parents=True)
            source.write_text("SELECT * FROM clientes;", encoding="utf-8")
            repo.index.add([str(source.relative_to(remote))])
            repo.index.commit("initial fixture", author=actor, committer=actor)
            project = root / "analyzer"
            project.mkdir()
            with patch("documentation_detect.cli.PROJECT_ROOT", project):
                self.assertEqual(main([str(remote)]), 0)
                (project / "resource/stale.txt").write_text("stale", encoding="utf-8")
                source.write_text("SELECT * FROM pedidos;", encoding="utf-8")
                repo.index.add([str(source.relative_to(remote))])
                repo.index.commit("new fixture", author=actor, committer=actor)
                self.assertEqual(main([str(remote)]), 0)
            self.assertFalse((project / "resource/stale.txt").exists())
            report = json.loads((project / "lab-service.json").read_text())
            self.assertEqual(report, {"servico": "lab-service", "microsservicos": [],
                                      "tabelas": ["pedidos"], "procedures": []})
            repo.close()


if __name__ == "__main__":
    unittest.main()
