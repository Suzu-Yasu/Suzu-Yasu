"""
ocr.py
Google Drive の組み込み OCR を使ってテキストを抽出し、
ファイル名だけでは分類できなかったファイルの移動先を推定するモジュール。

仕組み:
  1. Drive API で PDF/画像をGoogle Docとして一時コピー (→Drive側がOCR実行)
  2. Google Doc をプレーンテキストにエクスポート
  3. 一時コピーを削除
  4. 抽出テキストをキーワード解析して ClassificationResult を返す

対応フォーマット:
  PDF (.pdf), JPEG (.jpg / .jpeg), PNG (.png), TIFF (.tiff / .tif),
  BMP (.bmp), GIF (.gif), WebP (.webp)
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from classifier import ClassificationResult

# googleapiclient は実行時にのみ必要 (テスト時は不要)
# 関数内で遅延インポートする

logger = logging.getLogger(__name__)

# OCR 対応拡張子
OCR_SUPPORTED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png",
    ".tiff", ".tif", ".bmp", ".gif", ".webp",
}

# Google Doc の MIME タイプ
_GDOC_MIME = "application/vnd.google-apps.document"


# ================================================================== #
#  テキスト抽出
# ================================================================== #

def extract_text_via_drive_ocr(service, file_id: str, file_name: str) -> Optional[str]:
    """
    Drive API の組み込み OCR でファイルからテキストを抽出する。

    Parameters
    ----------
    service   : Google Drive API サービスオブジェクト
    file_id   : Drive 上のファイル ID
    file_name : ファイル名 (拡張子チェック用)

    Returns
    -------
    抽出されたテキスト文字列。OCR非対応ファイルやエラー時は None。
    """
    from googleapiclient.errors import HttpError  # 遅延インポート

    ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext not in OCR_SUPPORTED_EXTENSIONS:
        logger.debug("OCR非対応フォーマット: %s", file_name)
        return None

    temp_doc_id: Optional[str] = None
    try:
        # 1. Google Doc としてコピー (Drive がOCRを実行)
        logger.debug("OCR開始: '%s' (id=%s)", file_name, file_id)
        copied = (
            service.files()
            .copy(
                fileId=file_id,
                body={
                    "name": f"__ocr_temp_{file_name}",
                    "mimeType": _GDOC_MIME,
                },
                fields="id",
            )
            .execute()
        )
        temp_doc_id = copied["id"]

        # 2. プレーンテキストとしてエクスポート
        text_bytes: bytes = (
            service.files()
            .export(fileId=temp_doc_id, mimeType="text/plain")
            .execute()
        )
        text = text_bytes.decode("utf-8", errors="replace").strip()
        logger.debug("OCR完了: %d 文字抽出", len(text))
        return text if text else None

    except HttpError as e:
        logger.warning("Drive OCR エラー '%s': %s", file_name, e)
        return None

    finally:
        # 3. 一時 Google Doc を削除
        if temp_doc_id:
            try:
                service.files().delete(fileId=temp_doc_id).execute()
                logger.debug("一時Docを削除: id=%s", temp_doc_id)
            except HttpError:
                logger.warning("一時Doc削除失敗: id=%s (手動削除してください)", temp_doc_id)


# ================================================================== #
#  OCR テキストから分類を推定
# ================================================================== #

# --- キーワードセット定義 ---

# タグ推定用: (タグ, 移動先パス, キーワードリスト) の優先度付きリスト
# 上から順に評価し、最初に閾値を超えたものを採用
_OCR_RULES: list[tuple[str, list[str], list[str]]] = [
    # ---- 音楽 ----
    ("MUS", ["04_Music_Score", "99_Unsorted"], [
        "allegro", "andante", "adagio", "presto", "moderato",
        "forte", "piano", "cresc", "dim", "pp", "ff", "mf",
        "tempo", "ritardando", "accel", "fermata",
        "treble clef", "bass clef", "time signature",
        "measure", "bar", "quarter note", "eighth note",
        "楽譜", "音符", "拍子", "小節", "調号", "臨時記号",
        "ソナタ", "協奏曲", "交響曲", "弦楽四重奏",
    ]),

    # ---- 事務: 大学 ----
    ("ADM_UNIV", ["03_Admin_Life", "01_University_Admin"], [
        "在学証明", "成績証明", "履修登録", "学費", "授業料",
        "奨学金", "学生証", "単位", "シラバス", "科目",
        "university", "enrollment", "academic", "tuition",
        "scholarship", "transcript", "syllabus",
    ]),

    # ---- 事務: キャリア ----
    ("ADM_CAREER", ["03_Admin_Life", "02_Career_Intern"], [
        "履歴書", "職務経歴書", "インターン", "採用", "給与",
        "雇用契約", "アルバイト", "勤務", "時給",
        "resume", "internship", "employment", "salary",
        "contract", "part-time",
    ]),

    # ---- 事務: 役所 ----
    ("ADM_GOV", ["03_Admin_Life", "03_Government_Public"], [
        "住民票", "マイナンバー", "年金", "国民健康保険",
        "確定申告", "住民税", "個人番号",
        "residence", "my number", "pension", "tax return",
        "municipal", "ward office", "city hall",
    ]),

    # ---- 事務: 住居 ----
    ("ADM_HOUSE", ["03_Admin_Life", "04_Housing_Utilities"], [
        "賃貸", "家賃", "管理費", "敷金", "礼金", "契約書",
        "電気", "ガス", "水道", "インターネット", "光熱費",
        "rent", "lease", "utility", "electricity", "gas",
        "water supply", "broadband",
    ]),

    # ---- 事務: 金融 ----
    ("ADM_FIN", ["03_Admin_Life", "05_Finance_Bank"], [
        "口座", "残高", "振込", "引き落とし", "クレジットカード",
        "証券", "株式", "投資信託", "保険",
        "account", "balance", "transfer", "credit card",
        "securities", "investment", "insurance",
    ]),

    # ---- 医療 ----
    ("MED", ["05_Personal_Health", "03_Medical"], [
        "診察", "処方箋", "領収書", "病院", "クリニック",
        "診断", "薬", "投薬", "検査", "血圧", "体温",
        "prescription", "hospital", "clinic", "diagnosis",
        "medication", "blood pressure", "medical",
    ]),

    # ---- 健康・ジム ----
    ("PSN_GYM", ["05_Personal_Health", "01_Gym_Workout"], [
        "ベンチプレス", "スクワット", "デッドリフト", "筋トレ",
        "rep", "set", "rm", "kcal", "体重", "体脂肪",
        "bench press", "squat", "deadlift", "workout",
        "gym", "training", "muscle",
    ]),

    # ---- 講義: 数学系 ----
    ("LCT_MATH", ["01_University_Lecture", "2026_Spring", "01_LinAlg"], [
        "行列", "固有値", "ベクトル", "線形変換", "微分", "積分",
        "確率", "統計", "微分方程式",
        "matrix", "eigenvalue", "vector", "linear",
        "differential", "integral", "probability", "statistics",
    ]),

    # ---- 講義: CS系 ----
    ("LCT_CS", ["01_University_Lecture", "2026_Spring", "06_CS"], [
        "algorithm", "complexity", "O(n)", "recursion",
        "data structure", "graph", "dynamic programming",
        "アルゴリズム", "計算量", "再帰", "データ構造",
    ]),
]

# 最低一致キーワード数 (この数以上で採用)
_MIN_KEYWORD_HITS = 2


def classify_from_text(text: str, filename: str) -> ClassificationResult:
    """
    OCR で抽出したテキストからファイルの分類先を推定する。

    Parameters
    ----------
    text     : OCR テキスト
    filename : 元のファイル名 (ログ用)

    Returns
    -------
    ClassificationResult (is_classified=False なら推定不能)
    """
    text_lower = text.lower()
    best: Optional[tuple[int, str, list[str]]] = None  # (hits, label, path)

    for label, path, keywords in _OCR_RULES:
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        if hits >= _MIN_KEYWORD_HITS:
            if best is None or hits > best[0]:
                best = (hits, label, path)

    if best is None:
        logger.info("OCR分類不能: '%s' (キーワード不足)", filename)
        return ClassificationResult(
            target_path=[],
            reason="OCR: テキスト抽出済みだが分類キーワード不足",
            is_classified=False,
        )

    hits, label, path = best
    reason = f"OCR推定: {label} ({hits}キーワード一致) → {' / '.join(path)}"
    logger.info("%s", reason)
    return ClassificationResult(
        target_path=path,
        reason=reason,
        is_classified=True,
    )


# ================================================================== #
#  公開 API: ワンショット関数
# ================================================================== #

def ocr_classify(
    service,
    file_id: str,
    file_name: str,
) -> ClassificationResult:
    """
    Drive OCR でテキスト抽出 → 分類先を返す。

    organizer.py からのメインエントリーポイント。
    """
    text = extract_text_via_drive_ocr(service, file_id, file_name)
    if text is None:
        return ClassificationResult(
            target_path=[],
            reason="OCR: テキスト抽出失敗または非対応フォーマット",
            is_classified=False,
        )
    return classify_from_text(text, file_name)
