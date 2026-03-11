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


# ================================================================== #
#  スケジュールパーサ
# ================================================================== #

class TestParseSchedule:

    def test_valid_time(self):
        assert sa._parse_schedule("05:00") == (5, 0)

    def test_valid_time_midnight(self):
        assert sa._parse_schedule("00:00") == (0, 0)

    def test_valid_time_last_minute(self):
        assert sa._parse_schedule("23:59") == (23, 59)

    def test_valid_time_padded(self):
        assert sa._parse_schedule("09:30") == (9, 30)

    def test_invalid_format_no_colon(self):
        with pytest.raises(ValueError, match="形式"):
            sa._parse_schedule("0500")

    def test_invalid_format_extra_colon(self):
        with pytest.raises(ValueError):
            sa._parse_schedule("05:00:00")

    def test_invalid_hour_out_of_range(self):
        with pytest.raises(ValueError, match="範囲外"):
            sa._parse_schedule("24:00")

    def test_invalid_minute_out_of_range(self):
        with pytest.raises(ValueError, match="範囲外"):
            sa._parse_schedule("12:60")

    def test_invalid_non_numeric(self):
        with pytest.raises(ValueError):
            sa._parse_schedule("ab:cd")


# ================================================================== #
#  Linux: cron エントリ生成
# ================================================================== #

class TestCronEntry:

    def test_cron_entry_format(self):
        entry = sa._cron_entry(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert entry.startswith("0 5 * * *")

    def test_cron_entry_contains_root(self):
        entry = sa._cron_entry(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert str(FAKE_ROOT) in entry

    def test_cron_entry_no_ocr_by_default(self):
        entry = sa._cron_entry(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert "--ocr" not in entry

    def test_cron_entry_with_ocr(self):
        entry = sa._cron_entry(FAKE_ROOT, use_ocr=True, hour=5, minute=0)
        assert "--ocr" in entry

    def test_cron_entry_minute_in_correct_position(self):
        entry = sa._cron_entry(FAKE_ROOT, use_ocr=False, hour=3, minute=30)
        # cron format: minute hour * * *
        assert entry.startswith("30 3 * * *")

    def test_cron_entry_contains_python_executable(self):
        entry = sa._cron_entry(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert sys.executable in entry

    def test_cron_entry_log_redirect(self):
        entry = sa._cron_entry(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert "organizer.log" in entry
        assert ">>" in entry


# ================================================================== #
#  cron install/uninstall (crontab をモック)
# ================================================================== #

class TestCronInstallUninstall:

    def test_cron_install_adds_entry(self, tmp_path, monkeypatch):
        """_cron_install が crontab コマンドを呼び出してエントリを追加する。"""
        import subprocess as sp
        written: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd == ["crontab", "-l"]:
                return sp.CompletedProcess(cmd, 0, stdout="# existing job\n0 * * * * echo hello\n")
            if cmd == ["crontab", "-"]:
                written.append(kwargs.get("input", ""))
                return sp.CompletedProcess(cmd, 0, stdout="")
            return sp.CompletedProcess(cmd, 0, stdout="")

        monkeypatch.setattr(sa.subprocess, "run", fake_run)
        monkeypatch.setattr(sa, "LOG_DIR", tmp_path / "logs")

        sa._cron_install(FAKE_ROOT, use_ocr=False, hour=5, minute=0)

        assert written, "crontab - が呼ばれていない"
        new_crontab = written[0]
        assert sa.CRON_COMMENT in new_crontab
        assert "0 5 * * *" in new_crontab
        # 既存エントリが保持されていること
        assert "echo hello" in new_crontab

    def test_cron_install_overwrites_existing_entry(self, tmp_path, monkeypatch):
        """既存の drive-organizer エントリを上書きする。"""
        import subprocess as sp
        existing = (
            "# other job\n"
            f"{sa.CRON_COMMENT}\n"
            "0 8 * * * /old/python /old/organizer.py\n"
            "# another job\n"
        )
        written: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd == ["crontab", "-l"]:
                return sp.CompletedProcess(cmd, 0, stdout=existing)
            if cmd == ["crontab", "-"]:
                written.append(kwargs.get("input", ""))
                return sp.CompletedProcess(cmd, 0, stdout="")
            return sp.CompletedProcess(cmd, 0, stdout="")

        monkeypatch.setattr(sa.subprocess, "run", fake_run)
        monkeypatch.setattr(sa, "LOG_DIR", tmp_path / "logs")

        sa._cron_install(FAKE_ROOT, use_ocr=False, hour=5, minute=0)

        new_crontab = written[0]
        # 古い時刻が消え、新しい時刻になっている
        assert "0 8 * * *" not in new_crontab
        assert "0 5 * * *" in new_crontab
        # 他のジョブは保持
        assert "# other job" in new_crontab
        assert "# another job" in new_crontab

    def test_cron_uninstall_removes_entry(self, monkeypatch):
        """_cron_uninstall がエントリを削除する。"""
        import subprocess as sp
        existing = (
            "# keep this\n"
            f"{sa.CRON_COMMENT}\n"
            "0 5 * * * /usr/bin/python organizer.py\n"
            "# keep this too\n"
        )
        written: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd == ["crontab", "-l"]:
                return sp.CompletedProcess(cmd, 0, stdout=existing)
            if cmd == ["crontab", "-"]:
                written.append(kwargs.get("input", ""))
                return sp.CompletedProcess(cmd, 0, stdout="")
            return sp.CompletedProcess(cmd, 0, stdout="")

        monkeypatch.setattr(sa.subprocess, "run", fake_run)

        sa._cron_uninstall()

        assert written, "crontab - が呼ばれていない"
        new_crontab = written[0]
        assert sa.CRON_COMMENT not in new_crontab
        assert "0 5 * * *" not in new_crontab
        assert "# keep this" in new_crontab

    def test_cron_uninstall_no_entry_is_noop(self, monkeypatch):
        """エントリがない場合は crontab を変更しない。"""
        import subprocess as sp
        existing = "# only other jobs\n0 * * * * echo hi\n"
        written: list[str] = []

        def fake_run(cmd, **kwargs):
            if cmd == ["crontab", "-l"]:
                return sp.CompletedProcess(cmd, 0, stdout=existing)
            if cmd == ["crontab", "-"]:
                written.append(kwargs.get("input", ""))
                return sp.CompletedProcess(cmd, 0, stdout="")
            return sp.CompletedProcess(cmd, 0, stdout="")

        monkeypatch.setattr(sa.subprocess, "run", fake_run)

        sa._cron_uninstall()

        assert not written, "エントリなしなのに crontab が書き換えられた"


# ================================================================== #
#  macOS: launchd 定時実行 plist 生成
# ================================================================== #

class TestLaunchdPlistSchedule:

    def test_plist_schedule_is_valid_xml(self):
        plist = sa._launchd_plist_schedule(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert "<?xml" in plist
        assert "<plist" in plist
        assert "</plist>" in plist

    def test_plist_schedule_uses_schedule_label(self):
        plist = sa._launchd_plist_schedule(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert sa.MACOS_LABEL_SCHEDULE in plist

    def test_plist_schedule_has_start_calendar_interval(self):
        plist = sa._launchd_plist_schedule(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert "StartCalendarInterval" in plist
        assert "<integer>5</integer>" in plist
        assert "<integer>0</integer>" in plist

    def test_plist_schedule_no_keep_alive(self):
        plist = sa._launchd_plist_schedule(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert "KeepAlive" not in plist

    def test_plist_schedule_no_watch_flag(self):
        """定時実行 plist は --watch フラグを含まない（一回実行のため）。"""
        plist = sa._launchd_plist_schedule(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert "--watch" not in plist

    def test_plist_schedule_contains_root(self):
        plist = sa._launchd_plist_schedule(FAKE_ROOT, use_ocr=False, hour=5, minute=0)
        assert str(FAKE_ROOT) in plist

    def test_plist_schedule_ocr_enabled(self):
        plist = sa._launchd_plist_schedule(FAKE_ROOT, use_ocr=True, hour=5, minute=0)
        assert "--ocr" in plist

    def test_plist_schedule_hour_minute_varied(self):
        plist = sa._launchd_plist_schedule(FAKE_ROOT, use_ocr=False, hour=22, minute=45)
        assert "<integer>22</integer>" in plist
        assert "<integer>45</integer>" in plist

    def test_plist_schedule_path_uses_schedule_label(self):
        p = sa._launchd_plist_schedule_path()
        assert sa.MACOS_LABEL_SCHEDULE in p.name
        assert p.suffix == ".plist"

    def test_launchd_schedule_install_writes_plist(self, tmp_path, monkeypatch):
        """_launchd_schedule_install が plist を書き込む。"""
        plist_path = tmp_path / f"{sa.MACOS_LABEL_SCHEDULE}.plist"
        monkeypatch.setattr(sa, "_launchd_plist_schedule_path", lambda: plist_path)
        monkeypatch.setattr(sa, "_run", lambda *a, **kw: None)
        monkeypatch.setattr(sa, "LOG_DIR", tmp_path / "logs")

        sa._launchd_schedule_install(FAKE_ROOT, use_ocr=False, hour=5, minute=0)

        assert plist_path.exists()
        content = plist_path.read_text()
        assert "StartCalendarInterval" in content
        assert "<integer>5</integer>" in content


# ================================================================== #
#  CLI: --watch / --schedule オプション
# ================================================================== #

class TestArgParser:

    def test_install_watch_only(self):
        parser = sa.build_arg_parser()
        args = parser.parse_args(["install", "--root", "/tmp/drive", "--watch"])
        assert args.watch is True
        assert args.schedule is None

    def test_install_schedule_only(self):
        parser = sa.build_arg_parser()
        args = parser.parse_args(["install", "--root", "/tmp/drive", "--schedule", "05:00"])
        assert args.watch is False
        assert args.schedule == "05:00"

    def test_install_watch_and_schedule(self):
        parser = sa.build_arg_parser()
        args = parser.parse_args(["install", "--root", "/tmp/drive", "--watch", "--schedule", "22:30"])
        assert args.watch is True
        assert args.schedule == "22:30"

    def test_install_ocr_flag(self):
        parser = sa.build_arg_parser()
        args = parser.parse_args(["install", "--root", "/tmp/drive", "--watch", "--ocr"])
        assert args.ocr is True
