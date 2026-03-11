"""
test_setup_autostart.py
setup_autostart.py の単体テスト。
実際の OS サービス操作は行わず、ファイル生成・内容のみ検証する。
"""

import sys
from pathlib import Path

import pytest

import setup_autostart as sa


FAKE_ROOT = Path("/home/testuser/GoogleDrive")
FAKE_ROOT_OCR = Path("/home/testuser/GoogleDrive")


# ================================================================== #
#  systemd ユニットファイル生成
# ================================================================== #

class TestSystemdUnit:

    def test_unit_contains_watch_flag(self):
        unit = sa._systemd_unit(FAKE_ROOT, use_ocr=False)
        assert "--watch" in unit

    def test_unit_contains_root_path(self):
        unit = sa._systemd_unit(FAKE_ROOT, use_ocr=False)
        assert str(FAKE_ROOT) in unit

    def test_unit_ocr_disabled_by_default(self):
        unit = sa._systemd_unit(FAKE_ROOT, use_ocr=False)
        assert "--ocr" not in unit

    def test_unit_ocr_enabled(self):
        unit = sa._systemd_unit(FAKE_ROOT, use_ocr=True)
        assert "--ocr" in unit

    def test_unit_has_restart_policy(self):
        unit = sa._systemd_unit(FAKE_ROOT, use_ocr=False)
        assert "Restart=on-failure" in unit

    def test_unit_has_install_section(self):
        unit = sa._systemd_unit(FAKE_ROOT, use_ocr=False)
        assert "[Install]" in unit
        assert "WantedBy=default.target" in unit

    def test_unit_log_path_included(self):
        unit = sa._systemd_unit(FAKE_ROOT, use_ocr=False)
        assert "organizer.log" in unit

    def test_unit_python_executable_included(self):
        unit = sa._systemd_unit(FAKE_ROOT, use_ocr=False)
        assert sys.executable in unit


# ================================================================== #
#  launchd plist 生成
# ================================================================== #

class TestLaunchdPlist:

    def test_plist_is_valid_xml_structure(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=False)
        assert "<?xml" in plist
        assert "<plist" in plist
        assert "</plist>" in plist

    def test_plist_contains_label(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=False)
        assert sa.MACOS_LABEL in plist

    def test_plist_contains_watch_flag(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=False)
        assert "--watch" in plist

    def test_plist_contains_root_path(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=False)
        assert str(FAKE_ROOT) in plist

    def test_plist_ocr_disabled_by_default(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=False)
        assert "--ocr" not in plist

    def test_plist_ocr_enabled(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=True)
        assert "--ocr" in plist

    def test_plist_run_at_load(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=False)
        assert "<key>RunAtLoad</key>" in plist
        assert "<true/>" in plist

    def test_plist_keep_alive(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=False)
        assert "<key>KeepAlive</key>" in plist

    def test_plist_log_path_included(self):
        plist = sa._launchd_plist(FAKE_ROOT, use_ocr=False)
        assert "organizer.log" in plist


# ================================================================== #
#  パスヘルパー
# ================================================================== #

class TestPaths:

    def test_systemd_service_path_ends_with_service(self):
        p = sa._systemd_service_path()
        assert p.suffix == ".service"
        assert p.name == f"{sa.SERVICE_NAME}.service"

    def test_systemd_service_in_user_config(self):
        p = sa._systemd_service_path()
        assert ".config/systemd/user" in str(p)

    def test_launchd_plist_path_ends_with_plist(self):
        p = sa._launchd_plist_path()
        assert p.suffix == ".plist"
        assert sa.MACOS_LABEL in p.name

    def test_launchd_plist_in_launch_agents(self):
        p = sa._launchd_plist_path()
        assert "LaunchAgents" in str(p)

    def test_python_executable_is_current_python(self):
        exe = sa._python_executable()
        assert "python" in exe.lower()
        assert Path(exe).exists()


# ================================================================== #
#  install コマンドのファイル書き込み (tmp_path 使用)
# ================================================================== #

class TestInstallFileWrite:

    def test_systemd_unit_file_written(self, tmp_path, monkeypatch):
        """_systemd_install がユニットファイルを書き込むことを確認 (subprocess はモック)。"""
        service_path = tmp_path / "drive-organizer.service"
        monkeypatch.setattr(sa, "_systemd_service_path", lambda: service_path)
        monkeypatch.setattr(sa, "_run", lambda *a, **kw: None)
        monkeypatch.setattr(sa, "LOG_DIR", tmp_path / "logs")

        sa._systemd_install(FAKE_ROOT, use_ocr=False)

        assert service_path.exists()
        content = service_path.read_text()
        assert "--watch" in content
        assert str(FAKE_ROOT) in content

    def test_launchd_plist_written(self, tmp_path, monkeypatch):
        """_launchd_install が plist ファイルを書き込むことを確認 (subprocess はモック)。"""
        plist_path = tmp_path / f"{sa.MACOS_LABEL}.plist"
        monkeypatch.setattr(sa, "_launchd_plist_path", lambda: plist_path)
        monkeypatch.setattr(sa, "_run", lambda *a, **kw: None)
        monkeypatch.setattr(sa, "LOG_DIR", tmp_path / "logs")

        sa._launchd_install(FAKE_ROOT, use_ocr=True)

        assert plist_path.exists()
        content = plist_path.read_text()
        assert "--ocr" in content
        assert sa.MACOS_LABEL in content

    def test_log_dir_created_on_install(self, tmp_path, monkeypatch):
        """インストール時に logs/ フォルダが作成される。"""
        log_dir = tmp_path / "logs"
        service_path = tmp_path / "drive-organizer.service"
        monkeypatch.setattr(sa, "_systemd_service_path", lambda: service_path)
        monkeypatch.setattr(sa, "_run", lambda *a, **kw: None)
        monkeypatch.setattr(sa, "LOG_DIR", log_dir)

        sa._systemd_install(FAKE_ROOT, use_ocr=False)

        assert log_dir.exists()

    def test_uninstall_removes_service_file(self, tmp_path, monkeypatch):
        """アンインストール時にサービスファイルが削除される。"""
        service_path = tmp_path / "drive-organizer.service"
        service_path.write_text("[Unit]\nDescription=test")
        monkeypatch.setattr(sa, "_systemd_service_path", lambda: service_path)
        monkeypatch.setattr(sa, "_run", lambda *a, **kw: None)

        sa._systemd_uninstall()

        assert not service_path.exists()
