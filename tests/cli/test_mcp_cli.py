"""Tests for agent_os.cli MCP commands."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def isolated_home(monkeypatch, tmp_path):
    """Create an isolated home directory for testing."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


class TestMCPCLISubcommand:
    """Tests for the mcp CLI subcommand."""

    def test_mcp_help(self, isolated_home):
        """Should show MCP help text."""
        from agent_os.cli import build_parser

        parser = build_parser()
        # --help causes SystemExit(0), which is expected
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["mcp", "--help"])
        assert exc_info.value.code == 0

    def test_mcp_serve_help(self, isolated_home):
        """Should show MCP serve help."""
        from agent_os.cli import build_parser

        parser = build_parser()
        # Should parse without error
        args = parser.parse_args(["mcp", "serve"])
        assert args.command == "mcp"
        assert args.mcp_command == "serve"

    def test_mcp_install_help(self, isolated_home):
        """Should show MCP install help."""
        from agent_os.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "claude"])
        assert args.command == "mcp"
        assert args.mcp_command == "install"
        assert args.client == "claude"
        assert args.dry_run is False
        assert args.force is False

    def test_mcp_install_dry_run(self, isolated_home):
        """Should parse dry-run flag."""
        from agent_os.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "codex", "--dry-run"])
        assert args.dry_run is True

    def test_mcp_install_force(self, isolated_home):
        """Should parse force flag."""
        from agent_os.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "opencode", "--force"])
        assert args.force is True

    def test_mcp_uninstall_help(self, isolated_home):
        """Should show MCP uninstall help."""
        from agent_os.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["mcp", "uninstall", "--client", "claude"])
        assert args.command == "mcp"
        assert args.mcp_command == "uninstall"
        assert args.client == "claude"
        assert args.dry_run is False
        assert args.force is False

    def test_mcp_uninstall_dry_run(self, isolated_home):
        """Should parse dry-run flag."""
        from agent_os.cli import build_parser

        parser = build_parser()
        args = parser.parse_args(["mcp", "uninstall", "--client", "codex", "--dry-run"])
        assert args.dry_run is True


class TestMCPInstallCommand:
    """Tests for the mcp install command."""

    def test_install_dry_run_claude(self, isolated_home, capsys):
        """Should show dry-run output for Claude."""
        from agent_os.cli import build_parser, cmd_mcp_install

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "claude", "--dry-run"])
        cmd_mcp_install(args)
        captured = capsys.readouterr()
        assert "Would install MCP config for claude" in captured.out
        assert "dry_run" in captured.out

    def test_install_dry_run_codex(self, isolated_home, capsys):
        """Should show dry-run output for Codex."""
        from agent_os.cli import build_parser, cmd_mcp_install

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "codex", "--dry-run"])
        cmd_mcp_install(args)
        captured = capsys.readouterr()
        assert "Would install MCP config for codex" in captured.out

    def test_install_dry_run_opencode(self, isolated_home, capsys):
        """Should show dry-run output for OpenCode."""
        from agent_os.cli import build_parser, cmd_mcp_install

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "opencode", "--dry-run"])
        cmd_mcp_install(args)
        captured = capsys.readouterr()
        assert "Would install MCP config for opencode" in captured.out

    def test_install_invalid_client(self, isolated_home, capsys):
        """Should reject invalid client."""
        from agent_os.cli import build_parser, cmd_mcp_install

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "invalid"])
        with pytest.raises(SystemExit):
            cmd_mcp_install(args)

    def test_install_actual_claude(self, isolated_home, capsys):
        """Should install config for Claude."""
        from agent_os.cli import build_parser, cmd_mcp_install

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "claude"])
        cmd_mcp_install(args)
        captured = capsys.readouterr()
        assert "Installed MCP config for agent-os" in captured.out

        # Verify config file was created
        config_file = isolated_home / ".claude" / "settings.json"
        assert config_file.exists()
        with open(config_file) as f:
            config = json.load(f)
        assert "mcpServers" in config
        assert "agent-os" in config["mcpServers"]
        entry = config["mcpServers"]["agent-os"]
        assert entry["command"] == sys.executable
        assert entry["args"] == ["-m", "agent_os.mcp_server"]

    def test_install_actual_codex(self, isolated_home, capsys):
        """Should install config for Codex."""
        from agent_os.cli import build_parser, cmd_mcp_install

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "codex"])
        cmd_mcp_install(args)
        captured = capsys.readouterr()
        assert "Installed MCP config for agent-os" in captured.out

        # Verify config file was created
        config_file = isolated_home / ".codex" / "config.json"
        assert config_file.exists()
        with open(config_file) as f:
            config = json.load(f)
        assert "mcp_servers" in config
        assert "agent-os" in config["mcp_servers"]

    def test_install_actual_opencode(self, isolated_home, capsys):
        """Should install config for OpenCode."""
        from agent_os.cli import build_parser, cmd_mcp_install

        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "opencode"])
        cmd_mcp_install(args)
        captured = capsys.readouterr()
        assert "Installed MCP config for agent-os" in captured.out

        # Verify config file was created
        config_file = isolated_home / ".opencode" / "config.json"
        assert config_file.exists()
        with open(config_file) as f:
            config = json.load(f)
        assert "mcp_servers" in config
        assert "agent-os" in config["mcp_servers"]

    def test_install_idempotent(self, isolated_home, capsys):
        """Should not overwrite existing config."""
        from agent_os.cli import build_parser, cmd_mcp_install

        # Install once
        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "claude"])
        cmd_mcp_install(args)
        captured = capsys.readouterr()
        assert "Installed MCP config for agent-os" in captured.out

        # Install again
        args = parser.parse_args(["mcp", "install", "--client", "claude"])
        cmd_mcp_install(args)
        captured = capsys.readouterr()
        assert "already exists" in captured.out


class TestMCPUninstallCommand:
    """Tests for the mcp uninstall command."""

    def test_uninstall_dry_run_claude(self, isolated_home, capsys):
        """Should show dry-run output for Claude."""
        from agent_os.cli import build_parser, cmd_mcp_uninstall

        # Create config file first
        config_dir = isolated_home / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        with open(config_file, "w") as f:
            json.dump({"mcpServers": {"agent-os": {"command": "echo"}}}, f)

        parser = build_parser()
        args = parser.parse_args(["mcp", "uninstall", "--client", "claude", "--dry-run"])
        cmd_mcp_uninstall(args)
        captured = capsys.readouterr()
        assert "Would uninstall MCP config for agent-os" in captured.out

    def test_uninstall_invalid_client(self, isolated_home, capsys):
        """Should reject invalid client."""
        from agent_os.cli import build_parser, cmd_mcp_uninstall

        parser = build_parser()
        args = parser.parse_args(["mcp", "uninstall", "--client", "invalid"])
        with pytest.raises(SystemExit):
            cmd_mcp_uninstall(args)

    def test_uninstall_not_found(self, isolated_home, capsys):
        """Should handle missing config file."""
        from agent_os.cli import build_parser, cmd_mcp_uninstall

        parser = build_parser()
        args = parser.parse_args(["mcp", "uninstall", "--client", "claude"])
        cmd_mcp_uninstall(args)
        captured = capsys.readouterr()
        assert "No config file found" in captured.out

    def test_uninstall_actual(self, isolated_home, capsys):
        """Should uninstall config."""
        from agent_os.cli import build_parser, cmd_mcp_install, cmd_mcp_uninstall

        # Install first
        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "claude"])
        cmd_mcp_install(args)

        # Uninstall
        args = parser.parse_args(["mcp", "uninstall", "--client", "claude"])
        cmd_mcp_uninstall(args)
        captured = capsys.readouterr()
        assert "Uninstalled MCP config for agent-os" in captured.out

        # Verify config file was modified
        config_file = isolated_home / ".claude" / "settings.json"
        assert config_file.exists()
        with open(config_file) as f:
            config = json.load(f)
        assert "mcpServers" not in config or "agent-os" not in config.get("mcpServers", {})

    def test_uninstall_preserves_other_entries(self, isolated_home, capsys):
        """Should preserve other config entries."""
        from agent_os.cli import build_parser, cmd_mcp_install, cmd_mcp_uninstall

        # Create config with existing entry
        config_dir = isolated_home / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        with open(config_file, "w") as f:
            json.dump({"mcpServers": {"other-server": {"command": "echo"}}}, f)

        # Install agent-os
        parser = build_parser()
        args = parser.parse_args(["mcp", "install", "--client", "claude"])
        cmd_mcp_install(args)

        # Uninstall agent-os
        args = parser.parse_args(["mcp", "uninstall", "--client", "claude"])
        cmd_mcp_uninstall(args)

        # Verify other server is preserved
        with open(config_file) as f:
            config = json.load(f)
        assert "other-server" in config["mcpServers"]
        assert "agent-os" not in config["mcpServers"]


class TestMCPCLIServeCommand:
    """Tests for the mcp serve command."""

    def test_serve_import(self, isolated_home):
        """Should import mcp serve function."""
        from agent_os.cli import cmd_mcp_serve
        assert callable(cmd_mcp_serve)

    def test_serve_json_output(self, isolated_home, capsys):
        """Should show JSON output when requested."""
        from agent_os.cli import build_parser, cmd_mcp_serve

        parser = build_parser()
        # --json is a top-level flag, not a subcommand flag
        args = parser.parse_args(["--json", "mcp", "serve"])
        # We can't actually run the server, but we can check the parser
        assert args.json is True
        assert args.command == "mcp"
        assert args.mcp_command == "serve"
