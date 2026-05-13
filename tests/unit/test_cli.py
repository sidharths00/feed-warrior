from click.testing import CliRunner
from feed_warrior.cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "digest" in result.output
    assert "bootstrap-corpus" in result.output
    assert "bootstrap-accounts" in result.output


def test_cli_digest_help():
    runner = CliRunner()
    result = runner.invoke(main, ["digest", "--help"])
    assert result.exit_code == 0
    assert "--dry-run" in result.output
