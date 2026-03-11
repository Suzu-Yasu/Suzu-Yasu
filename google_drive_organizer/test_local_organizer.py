"""
test_local_organizer.py
local_organizer.py の単体テスト。
実際のファイルシステム操作を tmp_path で行う (Google API 不要)。
"""

import shutil
import pytest
from pathlib import Path

from local_organizer import organize_inbox, _resolve_conflict, OrganizerStats


# ================================================================== #
#  フィクスチャ: 仮想 Drive フォルダ構成
# ================================================================== #

@pytest.fixture
def drive_root(tmp_path: Path) -> Path:
    """
    tmp_path 直下に Google Drive ルートを模した構成を作る。
    00_Inbox だけ作成し、中にテスト用ファイルを置く。
    """
    root = tmp_path / "MyDrive"
    inbox = root / "00_Inbox"
    inbox.mkdir(parents=True)
    return root


def _put(inbox: Path, filename: str) -> Path:
    """inbox にダミーファイルを作成して Path を返す。"""
    p = inbox / filename
    p.write_text("dummy content")
    return p


# ================================================================== #
#  正常系: ファイル名で分類できるケース
# ================================================================== #

class TestOrganizeByFilename:

    def test_lecture_note_moved(self, drive_root):
        inbox = drive_root / "00_Inbox"
        _put(inbox, "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf")

        stats = organize_inbox(drive_root)

        assert len(stats.moved) == 1
        assert len(stats.errors) == 0
        dest = drive_root / "01_University_Lecture" / "2026_Spring" / "01_LinAlg" / "01_Lecture_Notes"
        assert (dest / "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf").exists()
        assert not (inbox / "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf").exists()

    def test_music_solo_moved(self, drive_root):
        inbox = drive_root / "00_Inbox"
        _put(inbox, "18950101_【MUS】_Dvorak_VcConc_Op104_b_moll_Vc_Baerenreiter_Part_Clean.pdf")

        stats = organize_inbox(drive_root)

        assert len(stats.moved) == 1
        dest = drive_root / "04_Music_Score" / "01_Solo"
        assert dest.exists()

    def test_admin_univ_moved(self, drive_root):
        inbox = drive_root / "00_Inbox"
        _put(inbox, "20260401_【ADM】_Univ_Scholarship_App.pdf")

        stats = organize_inbox(drive_root)

        dest = drive_root / "03_Admin_Life" / "01_University_Admin"
        assert (dest / "20260401_【ADM】_Univ_Scholarship_App.pdf").exists()

    def test_self_study_cs_moved(self, drive_root):
        inbox = drive_root / "00_Inbox"
        _put(inbox, "20260501_【STY】_CP_DijkstraMemo_Note_v01.pdf")

        stats = organize_inbox(drive_root)

        dest = drive_root / "02_Self_Study" / "01_CS_Programming"
        assert dest.exists()

    def test_multiple_files(self, drive_root):
        inbox = drive_root / "00_Inbox"
        names = [
            "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf",
            "20260401_【ADM】_House_Rent_Bill.pdf",
            "20260401_【PSN】_Gym_ChestDay_Log_v01.pdf",
        ]
        for n in names:
            _put(inbox, n)

        stats = organize_inbox(drive_root)

        assert len(stats.moved) == 3
        assert len(stats.skipped) == 0

    def test_subfolders_created_automatically(self, drive_root):
        """移動先フォルダが存在しなくても自動作成される。"""
        inbox = drive_root / "00_Inbox"
        _put(inbox, "20261001_【LCT】_DiffEq_Lec01_Note_v01.pdf")

        organize_inbox(drive_root)

        assert (drive_root / "01_University_Lecture" / "2026_Autumn" / "04_DiffEq").exists()


# ================================================================== #
#  スキップ: タグなしファイル
# ================================================================== #

class TestSkipUntaggedFiles:

    def test_no_tag_file_skipped(self, drive_root):
        inbox = drive_root / "00_Inbox"
        _put(inbox, "random_document.pdf")

        stats = organize_inbox(drive_root)

        assert len(stats.skipped) == 1
        assert len(stats.moved) == 0
        # ファイルは Inbox に残っている
        assert (inbox / "random_document.pdf").exists()

    def test_mixed_tagged_and_untagged(self, drive_root):
        inbox = drive_root / "00_Inbox"
        _put(inbox, "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf")
        _put(inbox, "random_scan.pdf")

        stats = organize_inbox(drive_root)

        assert len(stats.moved) == 1
        assert len(stats.skipped) == 1


# ================================================================== #
#  ドライラン
# ================================================================== #

class TestDryRun:

    def test_dry_run_does_not_move(self, drive_root):
        inbox = drive_root / "00_Inbox"
        filename = "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf"
        _put(inbox, filename)

        stats = organize_inbox(drive_root, dry_run=True)

        # ドライランなのでファイルは Inbox に残っている
        assert (inbox / filename).exists()
        # でも moved にはカウントされている
        assert len(stats.moved) == 1

    def test_dry_run_does_not_create_folders(self, drive_root):
        inbox = drive_root / "00_Inbox"
        _put(inbox, "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf")

        organize_inbox(drive_root, dry_run=True)

        # フォルダは作成されていない
        assert not (drive_root / "01_University_Lecture").exists()


# ================================================================== #
#  同名ファイルの競合解決
# ================================================================== #

class TestConflictResolution:

    def test_conflict_renamed(self, drive_root):
        inbox = drive_root / "00_Inbox"
        filename = "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf"

        # 先に同名ファイルを移動先に置く
        dest_dir = drive_root / "01_University_Lecture" / "2026_Spring" / "01_LinAlg" / "01_Lecture_Notes"
        dest_dir.mkdir(parents=True)
        (dest_dir / filename).write_text("original")

        # 同名ファイルを Inbox に追加
        _put(inbox, filename)
        organize_inbox(drive_root)

        # _1 が付いた名前で保存されている
        assert (dest_dir / "20260401_【LCT】_LinAlg_Lec01_Note_v01_1.pdf").exists()
        # 元ファイルは上書きされていない
        assert (dest_dir / filename).read_text() == "original"

    def test_resolve_conflict_no_existing(self, tmp_path):
        p = tmp_path / "file.pdf"
        assert _resolve_conflict(p) == p

    def test_resolve_conflict_with_existing(self, tmp_path):
        p = tmp_path / "file.pdf"
        p.write_text("x")
        result = _resolve_conflict(p)
        assert result == tmp_path / "file_1.pdf"

    def test_resolve_conflict_multiple(self, tmp_path):
        p = tmp_path / "file.pdf"
        p.write_text("x")
        (tmp_path / "file_1.pdf").write_text("x")
        result = _resolve_conflict(p)
        assert result == tmp_path / "file_2.pdf"


# ================================================================== #
#  Inbox フォルダが存在しない場合
# ================================================================== #

class TestMissingInbox:

    def test_missing_inbox_exits(self, tmp_path):
        root = tmp_path / "NoInbox"
        root.mkdir()

        with pytest.raises(SystemExit):
            organize_inbox(root)


# ================================================================== #
#  空の Inbox
# ================================================================== #

class TestEmptyInbox:

    def test_empty_inbox_returns_zero_stats(self, drive_root):
        stats = organize_inbox(drive_root)
        assert stats.moved == []
        assert stats.skipped == []
        assert stats.errors == []


# ================================================================== #
#  サマリー出力
# ================================================================== #

class TestSummary:

    def test_summary_contains_counts(self, drive_root):
        inbox = drive_root / "00_Inbox"
        _put(inbox, "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf")
        _put(inbox, "random.pdf")

        stats = organize_inbox(drive_root)
        summary = stats.summary()

        assert "1" in summary   # 移動済み 1
        assert "スキップ" in summary
