"""
local_organizer.py
Google API を一切使用しない、ローカルフォルダベースの整理スクリプト。

前提:
  Google Drive for Desktop (公式) または rclone で
  Google Drive をローカルフォルダとしてマウント・同期済みであること。

  Google Drive for Desktop のデフォルトパス:
    macOS : ~/Library/CloudStorage/GoogleDrive-xxx@gmail.com/My Drive/
    Windows: G:\\My Drive\\   (ドライブレターは環境による)
    Linux  : ~/GoogleDrive/   (rclone mount 等の場合)

使い方:
    # 一回実行 (ドライラン)
    python local_organizer.py --root ~/GoogleDrive --dry-run

    # 一回実行 (実際に移動)
    python local_organizer.py --root ~/GoogleDrive

    # 常駐監視モード (00_Inbox に追加されたら即整理)
    python local_organizer.py --root ~/GoogleDrive --watch

    # OCR フォールバック付き
    python local_organizer.py --root ~/GoogleDrive --ocr

    # OCR + 監視モード
    python local_organizer.py --root ~/GoogleDrive --watch --ocr

    # AI 分類モード (OCR + LLM で柔軟に分類)
    python local_organizer.py --root ~/GoogleDrive --ai

    # AI + 監視モード
    python local_organizer.py --root ~/GoogleDrive --watch --ai
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from classifier import classify

logger = logging.getLogger(__name__)

INBOX_DIR_NAMES = ("00_Inbox", "00_inbox", "00_INBOX")


# ================================================================== #
#  結果集計
# ================================================================== #

@dataclass
class OrganizerStats:
    moved:   list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors:  list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "  整理結果サマリー",
            "=" * 50,
            f"  移動済み : {len(self.moved)} ファイル",
            f"  スキップ : {len(self.skipped)} ファイル",
            f"  エラー   : {len(self.errors)} ファイル",
        ]
        if self.moved:
            lines.append("\n[移動済み]")
            lines.extend(f"  ✓ {n}" for n in self.moved)
        if self.skipped:
            lines.append("\n[スキップ (タグなし/判定不能)]")
            lines.extend(f"  - {n}" for n in self.skipped)
        if self.errors:
            lines.append("\n[エラー]")
            lines.extend(f"  ✗ {n}" for n in self.errors)
        lines.append("=" * 50)
        return "\n".join(lines)


# ================================================================== #
#  Inbox フォルダ検出 (大文字小文字を柔軟に扱う)
# ================================================================== #

def _find_inbox(root: Path) -> Optional[Path]:
    """root 直下から Inbox フォルダを検索する (大文字小文字不問)。"""
    for name in INBOX_DIR_NAMES:
        candidate = root / name
        if candidate.exists() and candidate.is_dir():
            return candidate
    # さらに大文字小文字を完全無視して探す
    for child in root.iterdir():
        if child.is_dir() and child.name.lower() == "00_inbox":
            return child
    return None


# ================================================================== #
#  コアロジック
# ================================================================== #

def organize_inbox(
    root: Path,
    dry_run: bool = False,
    use_ocr: bool = False,
    use_ai: bool = False,
) -> OrganizerStats:
    """
    <root>/00_Inbox 内のファイルを分類して各フォルダに移動する。

    Parameters
    ----------
    root    : Google Drive のローカル同期フォルダのルートパス
    dry_run : True の場合は移動せず確認のみ
    use_ocr : True の場合、分類できなかったファイルにローカルOCRを試みる
    use_ai  : True の場合、全ファイルに OCR → AI 分類を実行する
    """
    stats = OrganizerStats()
    inbox = _find_inbox(root)

    if inbox is None:
        logger.error("Inbox フォルダが見つかりません: %s/00_Inbox", root)
        sys.exit(1)

    files = [p for p in inbox.iterdir() if p.is_file()]
    if not files:
        logger.info("Inbox にファイルがありません。")
        return stats

    logger.info("Inbox 内ファイル数: %d", len(files))

    for filepath in files:
        file_name = filepath.name

        if use_ai:
            # AI モード: 全ファイルに OCR → AI 分類を実行
            result = _ai_classify_local(filepath, file_name)
            # AI で分類できなかった場合、ファイル名ベースにフォールバック
            if not result.is_classified:
                logger.info("AI分類失敗 → ファイル名ベースにフォールバック: '%s'", file_name)
                result = classify(file_name)
        else:
            # 従来モード: ファイル名ベースの分類
            result = classify(file_name)
            logger.debug("'%s' → %s (%s)", file_name, result.target_path, result.reason)

            # ファイル名で分類できなかった場合 → OCR フォールバック
            if not result.is_classified or not result.target_path:
                if use_ocr:
                    logger.info("OCRフォールバック: '%s'", file_name)
                    result = _ocr_classify_local(filepath, file_name)

        if not result.is_classified or not result.target_path:
            logger.info("SKIP '%s': %s", file_name, result.reason)
            stats.skipped.append(file_name)
            continue

        # 移動先フォルダパスを解決 (なければ作成)
        dest_dir = root
        for part in result.target_path:
            dest_dir = dest_dir / part

        dest_path_str = str(dest_dir.relative_to(root))

        if dry_run:
            logger.info("[DRY-RUN] '%s'  →  %s", file_name, dest_path_str)
            stats.moved.append(f"{file_name}  →  {dest_path_str}")
            continue

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / file_name

            # 同名ファイルが存在する場合はリネーム (_1, _2, ...)
            dest_file = _resolve_conflict(dest_file)

            shutil.move(str(filepath), str(dest_file))
            logger.info("MOVED '%s'  →  %s", file_name, dest_path_str)
            stats.moved.append(f"{file_name}  →  {dest_path_str}")
        except Exception as e:
            logger.error("移動エラー '%s': %s", file_name, e)
            stats.errors.append(file_name)

    return stats


def _resolve_conflict(dest: Path) -> Path:
    """移動先に同名ファイルがある場合、_1 / _2 ... を付けて返す。"""
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _ocr_classify_local(filepath: Path, file_name: str):
    """
    ローカルOCR による分類フォールバック。
    ocr.py の extract_text_local_from_path() + classify_from_text() を使用。
    """
    try:
        from ocr import extract_text_local_from_path, classify_from_text
        text = extract_text_local_from_path(filepath)
        if text:
            return classify_from_text(text, file_name)
    except ImportError:
        logger.warning(
            "OCRライブラリ未インストール。"
            "'pip install pdfplumber pytesseract pdf2image pillow' を実行してください。"
        )
    except Exception as e:
        logger.warning("OCRエラー '%s': %s", file_name, e)

    from classifier import ClassificationResult
    return ClassificationResult(
        target_path=[],
        reason="ローカルOCR失敗",
        is_classified=False,
    )


def _extract_text_local(filepath: Path) -> Optional[str]:
    """OCR テキスト抽出のみ行う (分類は呼び出し側で行う)。"""
    try:
        from ocr import extract_text_local_from_path
        return extract_text_local_from_path(filepath)
    except ImportError:
        logger.warning(
            "OCRライブラリ未インストール。"
            "'pip install pdfplumber pytesseract pdf2image pillow' を実行してください。"
        )
    except Exception as e:
        logger.warning("OCRエラー '%s': %s", filepath.name, e)
    return None


def _ai_classify_local(filepath: Path, file_name: str):
    """
    OCR テキスト抽出 → AI (LLM) による柔軟な分類。
    ai_classifier.py の classify_with_ai() を使用。
    """
    from classifier import ClassificationResult

    # 1. OCR でテキスト抽出
    ocr_text = _extract_text_local(filepath)
    if not ocr_text:
        logger.info("AI分類: OCRテキスト抽出失敗 '%s'", file_name)
        return ClassificationResult(
            target_path=[],
            reason="AI分類: OCRテキスト抽出失敗",
            is_classified=False,
        )

    # 2. AI で分類
    try:
        from ai_classifier import classify_with_ai
        return classify_with_ai(file_name, ocr_text)
    except ImportError as e:
        logger.warning("AI分類ライブラリエラー: %s", e)
        return ClassificationResult(
            target_path=[],
            reason=f"AI分類: ライブラリエラー — {e}",
            is_classified=False,
        )
    except Exception as e:
        logger.warning("AI分類エラー '%s': %s", file_name, e)
        return ClassificationResult(
            target_path=[],
            reason=f"AI分類: エラー — {e}",
            is_classified=False,
        )


# ================================================================== #
#  監視モード (watchdog)
# ================================================================== #

def watch_inbox(root: Path, use_ocr: bool = False, use_ai: bool = False) -> None:
    """
    00_Inbox フォルダを監視し、新しいファイルが追加されたら即整理する。
    watchdog ライブラリが必要: pip install watchdog
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        logger.error(
            "watchdog がインストールされていません。"
            "'pip install watchdog' を実行してください。"
        )
        sys.exit(1)

    inbox = _find_inbox(root)
    if inbox is None:
        logger.error("Inbox フォルダが見つかりません: %s/00_Inbox", root)
        sys.exit(1)

    class InboxHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            filepath = Path(event.src_path)
            # ファイルが書き込み中の場合があるため少し待つ
            time.sleep(0.5)
            if not filepath.exists():
                return
            logger.info("新規ファイル検出: '%s'", filepath.name)
            # 単一ファイルを整理
            _process_single_file(filepath, root, use_ocr=use_ocr, use_ai=use_ai)

    observer = Observer()
    observer.schedule(InboxHandler(), str(inbox), recursive=False)
    observer.start()
    logger.info("監視開始: %s  (Ctrl+C で停止)", inbox)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("監視を停止します...")
        observer.stop()
    observer.join()


def _process_single_file(
    filepath: Path,
    root: Path,
    dry_run: bool = False,
    use_ocr: bool = False,
    use_ai: bool = False,
) -> None:
    """watchdog から呼ばれる単一ファイル処理。"""
    file_name = filepath.name

    if use_ai:
        result = _ai_classify_local(filepath, file_name)
        if not result.is_classified:
            result = classify(file_name)
    else:
        result = classify(file_name)
        if not result.is_classified or not result.target_path:
            if use_ocr:
                result = _ocr_classify_local(filepath, file_name)

    if not result.is_classified or not result.target_path:
        logger.info("SKIP '%s'", file_name)
        return

    dest_dir = root
    for part in result.target_path:
        dest_dir = dest_dir / part

    if dry_run:
        logger.info("[DRY-RUN] '%s' → %s", file_name, dest_dir.relative_to(root))
        return

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = _resolve_conflict(dest_dir / file_name)
        shutil.move(str(filepath), str(dest_file))
        logger.info("MOVED '%s' → %s", file_name, dest_dir.relative_to(root))
    except Exception as e:
        logger.error("移動エラー '%s': %s", file_name, e)


# ================================================================== #
#  エントリーポイント
# ================================================================== #

def _detect_drive_root() -> Optional[Path]:
    """Google Drive for Desktop のデフォルトパスを自動検出する。"""
    home = Path.home()
    candidates = [
        # macOS: Google Drive for Desktop (新形式)
        *sorted(home.glob(
            "Library/CloudStorage/GoogleDrive-*/My Drive"
        )),
        # macOS: 旧 Backup and Sync
        home / "Google Drive" / "My Drive",
        home / "Google Drive",
        # Linux: rclone mount 等
        home / "GoogleDrive",
        home / "gdrive",
        # Windows (WSL 経由)
        Path("/mnt/g/My Drive"),
        Path("/mnt/g"),
        # Windows: Desktop ショートカット
        home / "Desktop" / "Google Drive Local",
    ]
    for p in candidates:
        if p.exists() and _find_inbox(p) is not None:
            return p
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Google API 不要のローカル版 Drive 整理スクリプト。\n"
            "Google Drive for Desktop または rclone でローカル同期済みの\n"
            "フォルダを直接操作します。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        default=None,
        metavar="DIR",
        help=(
            "Google Drive のローカル同期フォルダのルートパス。\n"
            "省略すると自動検出を試みます。"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には移動せず、移動先の確認のみ行う",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細なデバッグログを表示する",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help=(
            "ファイル名で分類できなかったファイルにローカルOCRを試みる。\n"
            "事前に 'pip install pdfplumber pytesseract pdf2image pillow' と\n"
            "Tesseract バイナリのインストールが必要。"
        ),
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help=(
            "00_Inbox フォルダを常駐監視し、ファイル追加を検出したら即整理する。\n"
            "事前に 'pip install watchdog' が必要。"
        ),
    )
    parser.add_argument(
        "--ai",
        action="store_true",
        help=(
            "AI分類モード: 全ファイルに対して OCR → Gemini API で\n"
            "ファイル内容を分析し、柔軟にフォルダ分類する。\n"
            "ファイル名の命名規則に従っていなくても分類可能。\n"
            "事前に 'pip install google-genai pdfplumber pytesseract pdf2image pillow' と\n"
            "環境変数 GEMINI_API_KEY の設定が必要。"
        ),
    )
    parser.add_argument(
        "--ai-model",
        default="gemini-2.0-flash",
        metavar="MODEL",
        help=(
            "AI分類に使用する Gemini モデル (デフォルト: gemini-2.0-flash)。\n"
            "精度を上げたい場合は gemini-2.5-pro を指定。"
        ),
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ルートパス解決
    if args.root:
        root = Path(args.root).expanduser().resolve()
    else:
        root = _detect_drive_root()
        if root is None:
            logger.error(
                "Google Drive のローカルフォルダが自動検出できませんでした。\n"
                "--root オプションでパスを明示してください。\n"
                "例: python local_organizer.py --root ~/GoogleDrive"
            )
            sys.exit(1)
        logger.info("Drive ルートを自動検出: %s", root)

    if not root.exists():
        logger.error("指定パスが存在しません: %s", root)
        sys.exit(1)

    if args.dry_run:
        logger.info("=== ドライランモード: ファイルは移動されません ===")
    if args.ai:
        logger.info("=== AI分類モード: OCR + LLM (%s) を使用します ===", args.ai_model)
    elif args.ocr:
        logger.info("=== OCRモード: ローカル Tesseract OCR を使用します ===")

    inbox = _find_inbox(root)
    inbox_name = inbox.name if inbox else "00_Inbox"

    if args.watch:
        logger.info("=== 監視モードで起動: %s/%s ===", root, inbox_name)
        watch_inbox(root, use_ocr=args.ocr, use_ai=args.ai)
    else:
        stats = organize_inbox(root, dry_run=args.dry_run, use_ocr=args.ocr, use_ai=args.ai)
        print(stats.summary())


if __name__ == "__main__":
    main()
