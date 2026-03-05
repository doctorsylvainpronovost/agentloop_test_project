import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MigrationSetupTests(unittest.TestCase):
    def _run_alembic(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.setdefault("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/weather")
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_python3_runtime_is_available(self) -> None:
        self.assertGreaterEqual(sys.version_info.major, 3)

    def test_required_packages_are_importable(self) -> None:
        import alembic  # noqa: F401
        import psycopg  # noqa: F401
        import sqlalchemy  # noqa: F401

    def test_requirements_include_migration_dependencies(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("alembic", requirements)
        self.assertIn("sqlalchemy", requirements)
        self.assertIn("psycopg[binary]", requirements)

    def test_database_url_is_postgresql(self) -> None:
        from app.config import get_database_url, is_postgresql_url

        db_url = get_database_url()
        self.assertTrue(is_postgresql_url(db_url))

    def test_alembic_uses_application_database_url(self) -> None:
        from alembic.config import Config
        from app.config import get_database_url

        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", get_database_url())
        self.assertEqual(cfg.get_main_option("sqlalchemy.url"), get_database_url())

    def test_single_head_and_baseline_revision_discoverable(self) -> None:
        heads = self._run_alembic("heads")
        self.assertEqual(heads.returncode, 0, heads.stderr)
        self.assertEqual(heads.stdout.count("(head)"), 1)
        self.assertIn("0001_baseline", heads.stdout)

    def test_migration_commands_history_and_upgrade_sql(self) -> None:
        history = self._run_alembic("history")
        self.assertEqual(history.returncode, 0, history.stderr)
        self.assertIn("0001_baseline", history.stdout)

        upgrade_sql = self._run_alembic("upgrade", "head", "--sql")
        self.assertEqual(upgrade_sql.returncode, 0, upgrade_sql.stderr)
        self.assertIn("0001_baseline", upgrade_sql.stdout)

        repeat_upgrade_sql = self._run_alembic("upgrade", "head", "--sql")
        self.assertEqual(repeat_upgrade_sql.returncode, 0, repeat_upgrade_sql.stderr)


if __name__ == "__main__":
    unittest.main()
