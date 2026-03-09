"""
classifier.py
ファイル名を解析して、移動先フォルダパスを決定するモジュール。

命名規則: YYYYMMDD_【TAG】_Category_Detail_Type_Version.extension
"""

import re
from dataclasses import dataclass
from typing import Optional


# ------------------------------------------------------------------ #
#  データ構造
# ------------------------------------------------------------------ #

@dataclass
class ParsedFile:
    original_name: str
    date: Optional[str]
    tag: Optional[str]
    category: Optional[str]
    rest: str  # Category以降の残り部分


@dataclass
class ClassificationResult:
    target_path: list[str]   # ルートからのフォルダ名リスト (ルート自体は除く)
    reason: str
    is_classified: bool


# ------------------------------------------------------------------ #
#  タグ → トップレベルフォルダ
# ------------------------------------------------------------------ #

TAG_TO_ROOT: dict[str, str] = {
    "LCT": "01_University_Lecture",
    "RES": "02_Self_Study",
    "STY": "02_Self_Study",
    "PRJ": "03_Admin_Life",
    "ADM": "03_Admin_Life",
    "MUS": "04_Music_Score",
    "PSN": "05_Personal_Health",
}

# ------------------------------------------------------------------ #
#  カテゴリ略称 → サブフォルダ
# ------------------------------------------------------------------ #

# 02_Self_Study サブフォルダ
SELF_STUDY_MAP: dict[str, str] = {
    # CS / プログラミング
    "cs":      "01_CS_Programming",
    "algo":    "01_CS_Programming",
    "ml":      "01_CS_Programming",
    "dl":      "01_CS_Programming",
    "python":  "01_CS_Programming",
    "cpp":     "01_CS_Programming",
    "atcoder": "01_CS_Programming",
    "kaggle":  "01_CS_Programming",
    # 数学・クオンツ
    "math":    "02_Math_Quant",
    "linalg":  "02_Math_Quant",
    "calc":    "02_Math_Quant",
    "probstat":"02_Math_Quant",
    "diffeq":  "02_Math_Quant",
    "quants":  "02_Math_Quant",
    "fineng":  "02_Math_Quant",
    "econ":    "02_Math_Quant",
    "metrics": "02_Math_Quant",
    "stat":    "02_Math_Quant",
    # 英語
    "english": "03_English",
    "toefl":   "03_English",
    "eng":     "03_English",
}

# 03_Admin_Life サブフォルダ
ADMIN_MAP: dict[str, str] = {
    "univ":    "01_University_Admin",
    "career":  "02_Career_Intern",
    "intern":  "02_Career_Intern",
    "gov":     "03_Government_Public",
    "house":   "04_Housing_Utilities",
    "fin":     "05_Finance_Bank",
    "bank":    "05_Finance_Bank",
    "med":     "05_Finance_Bank",  # 医療は個人健康フォルダへリマップ
}

# 04_Music_Score サブフォルダ (楽曲の種類で分類)
MUSIC_KEYWORDS: dict[str, str] = {
    # ソロ系キーワード
    "sonat":   "01_Solo",
    "conc":    "01_Solo",
    "suite":   "01_Solo",
    "partita": "01_Solo",
    "vcconc":  "01_Solo",
    "solo":    "01_Solo",
    # オーケストラ系
    "sym":     "02_Orchestra",
    "orch":    "02_Orchestra",
    "overture":"02_Orchestra",
    "tone":    "02_Orchestra",
    # 室内楽
    "quartet": "03_Chamber",
    "trio":    "03_Chamber",
    "quintet": "03_Chamber",
    "chamber": "03_Chamber",
    "duo":     "03_Chamber",
    "sonata":  "03_Chamber",  # ピアノソナタ等は室内楽扱い(上のsonat優先)
}

# 05_Personal_Health サブフォルダ
PERSONAL_MAP: dict[str, str] = {
    "gym":      "01_Gym_Workout",
    "workout":  "01_Gym_Workout",
    "training": "01_Gym_Workout",
    "diet":     "02_Diet_Nutrition",
    "nutrition":"02_Diet_Nutrition",
    "inbody":   "02_Diet_Nutrition",
    "food":     "02_Diet_Nutrition",
    "med":      "03_Medical",
    "medical":  "03_Medical",
    "hospital": "03_Medical",
    "health":   "03_Medical",
}


# ------------------------------------------------------------------ #
#  ファイル名パーサ
# ------------------------------------------------------------------ #

# タグパターン: 【LCT】【RES】etc.
TAG_PATTERN = re.compile(r"【([A-Z]{2,4})】", re.IGNORECASE)
# 日付パターン: 先頭の YYYYMMDD または 00000000
DATE_PATTERN = re.compile(r"^(\d{8})_")


def parse_filename(name: str) -> ParsedFile:
    """ファイル名を解析して ParsedFile を返す。"""
    stem = name.rsplit(".", 1)[0]  # 拡張子を除いたステム

    # 日付
    date_match = DATE_PATTERN.match(stem)
    date = date_match.group(1) if date_match else None

    # タグ
    tag_match = TAG_PATTERN.search(stem)
    tag = tag_match.group(1).upper() if tag_match else None

    # タグ以降を parts に分解
    parts: list[str] = []
    if tag_match:
        after_tag = stem[tag_match.end():].lstrip("_")
        parts = [p for p in after_tag.split("_") if p]
    elif date_match:
        after_date = stem[date_match.end():].lstrip("_")
        parts = [p for p in after_date.split("_") if p]
    else:
        parts = [p for p in stem.split("_") if p]

    category = parts[0] if parts else None
    rest = "_".join(parts[1:]) if len(parts) > 1 else ""

    return ParsedFile(
        original_name=name,
        date=date,
        tag=tag,
        category=category,
        rest=rest,
    )


# ------------------------------------------------------------------ #
#  サブフォルダ解決ヘルパー
# ------------------------------------------------------------------ #

def _match_map(keyword: str, mapping: dict[str, str]) -> Optional[str]:
    """keyword (小文字) を mapping のキーと前方一致で照合する。"""
    key = keyword.lower()
    # 完全一致優先
    if key in mapping:
        return mapping[key]
    # 前方一致
    for k, v in mapping.items():
        if key.startswith(k) or k.startswith(key):
            return v
    return None


def _classify_lecture(pf: ParsedFile) -> ClassificationResult:
    """【LCT】ファイルの分類。"""
    root = "01_University_Lecture"
    name_lower = pf.original_name.lower()

    # 過去問キーワード
    if any(kw in name_lower for kw in ["pastexam", "exam", "kakomon", "past_exam"]):
        return ClassificationResult(
            target_path=[root, "00_Past_Exams_Archive"],
            reason="過去問キーワード検出",
            is_classified=True,
        )

    # 学期フォルダ (日付の年から推定 or ファイル名に semester キーワード)
    semester = _detect_semester(pf, name_lower)
    subject  = _detect_lecture_subject(pf, name_lower)

    path = [root, semester]
    if subject:
        path.append(subject)
    # Lecture Notes / Handouts / Assignments の振り分け
    subtype = _detect_lecture_subtype(name_lower)
    if subject and subtype:
        path.append(subtype)

    return ClassificationResult(
        target_path=path,
        reason=f"講義: {semester}/{subject or '不明'}",
        is_classified=True,
    )


def _detect_semester(pf: ParsedFile, name_lower: str) -> str:
    """学期フォルダ名を推定する。"""
    year = None
    if pf.date and pf.date != "00000000":
        year = pf.date[:4]

    season = None
    if any(kw in name_lower for kw in ["spring", "spr", "s1", "前期", "1q", "2q"]):
        season = "Spring"
    elif any(kw in name_lower for kw in ["autumn", "fall", "aut", "s2", "後期", "3q", "4q"]):
        season = "Autumn"

    # 月で推定 (日付がある場合)
    if season is None and pf.date and pf.date != "00000000":
        month = int(pf.date[4:6])
        season = "Spring" if 1 <= month <= 7 else "Autumn"

    if year and season:
        return f"{year}_{season}"
    if year:
        return f"{year}_Spring"
    return "2026_Spring"  # デフォルト


def _detect_lecture_subject(pf: ParsedFile, name_lower: str) -> Optional[str]:
    """科目フォルダ名を推定する。"""
    subject_map = {
        "linalg":   "01_LinAlg1",
        "linalg1":  "01_LinAlg1",
        "linalg2":  "02_LinAlg2",
        "calc":     "02_Calc",
        "probstat": "03_ProbStat",
        "diffeq":   "04_DiffEq",
        "phys":     "05_Physics",
        "mech":     "05_Physics",
        "cs":       "06_CS",
        "algo":     "07_Algorithm",
        "prog":     "08_Programming",
        "econ":     "09_Econ",
        "fineng":   "10_FinEng",
    }
    # Category から照合
    if pf.category:
        result = _match_map(pf.category, subject_map)
        if result:
            return result
    # ファイル名全体から照合
    for key, val in subject_map.items():
        if key in name_lower:
            return val
    return None


def _detect_lecture_subtype(name_lower: str) -> Optional[str]:
    """講義内サブフォルダ (Notes / Handouts / Assignments)。"""
    if any(kw in name_lower for kw in ["note", "summary", "memo"]):
        return "01_Lecture_Notes"
    if any(kw in name_lower for kw in ["slide", "handout", "print", "material"]):
        return "02_Handouts"
    if any(kw in name_lower for kw in ["assign", "report", "hw", "homework", "kadai"]):
        return "03_Assignments"
    return None


def _classify_music(pf: ParsedFile) -> ClassificationResult:
    """【MUS】ファイルの分類。"""
    root = "04_Music_Score"
    name_lower = pf.original_name.lower()

    # ファイル名全体でキーワード照合
    for keyword, subfolder in MUSIC_KEYWORDS.items():
        if keyword in name_lower:
            return ClassificationResult(
                target_path=[root, subfolder],
                reason=f"音楽キーワード '{keyword}' 検出",
                is_classified=True,
            )

    # 判定不能 → Unsorted
    return ClassificationResult(
        target_path=[root, "99_Unsorted"],
        reason="音楽サブフォルダ未判定 → Unsorted",
        is_classified=True,
    )


def _classify_self_study(pf: ParsedFile) -> ClassificationResult:
    """【STY】【RES】ファイルの分類。"""
    root = "02_Self_Study"
    name_lower = pf.original_name.lower()

    # Category から照合
    if pf.category:
        sub = _match_map(pf.category, SELF_STUDY_MAP)
        if sub:
            return ClassificationResult(
                target_path=[root, sub],
                reason=f"自習カテゴリ '{pf.category}' → {sub}",
                is_classified=True,
            )

    # ファイル名全体から照合
    for key, val in SELF_STUDY_MAP.items():
        if key in name_lower:
            return ClassificationResult(
                target_path=[root, val],
                reason=f"自習キーワード '{key}' 検出",
                is_classified=True,
            )

    return ClassificationResult(
        target_path=[root],
        reason="自習サブフォルダ未判定 → ルート",
        is_classified=True,
    )


def _classify_admin(pf: ParsedFile) -> ClassificationResult:
    """【ADM】【PRJ】ファイルの分類。"""
    root = "03_Admin_Life"
    name_lower = pf.original_name.lower()

    # 医療は個人健康フォルダ優先
    if any(kw in name_lower for kw in ["med", "medical", "hospital", "clinic", "薬"]):
        return ClassificationResult(
            target_path=["05_Personal_Health", "03_Medical"],
            reason="医療キーワード → 05_Personal_Health/03_Medical",
            is_classified=True,
        )

    if pf.category:
        sub = _match_map(pf.category, ADMIN_MAP)
        if sub:
            return ClassificationResult(
                target_path=[root, sub],
                reason=f"事務カテゴリ '{pf.category}' → {sub}",
                is_classified=True,
            )

    for key, val in ADMIN_MAP.items():
        if key in name_lower:
            return ClassificationResult(
                target_path=[root, val],
                reason=f"事務キーワード '{key}' 検出",
                is_classified=True,
            )

    return ClassificationResult(
        target_path=[root],
        reason="事務サブフォルダ未判定 → ルート",
        is_classified=True,
    )


def _classify_personal(pf: ParsedFile) -> ClassificationResult:
    """【PSN】ファイルの分類。"""
    root = "05_Personal_Health"
    name_lower = pf.original_name.lower()

    if pf.category:
        sub = _match_map(pf.category, PERSONAL_MAP)
        if sub:
            return ClassificationResult(
                target_path=[root, sub],
                reason=f"個人カテゴリ '{pf.category}' → {sub}",
                is_classified=True,
            )

    for key, val in PERSONAL_MAP.items():
        if key in name_lower:
            return ClassificationResult(
                target_path=[root, val],
                reason=f"個人キーワード '{key}' 検出",
                is_classified=True,
            )

    return ClassificationResult(
        target_path=[root],
        reason="個人サブフォルダ未判定 → ルート",
        is_classified=True,
    )


# ------------------------------------------------------------------ #
#  メイン分類関数
# ------------------------------------------------------------------ #

def classify(filename: str) -> ClassificationResult:
    """
    ファイル名から移動先フォルダパス (リスト) を返す。

    戻り値の target_path は Google Drive ルートからのフォルダ名リスト。
    例: ["01_University_Lecture", "2026_Spring", "01_LinAlg1", "01_Lecture_Notes"]
    """
    pf = parse_filename(filename)

    if pf.tag is None:
        # タグなし → ファイル名全体からヒューリスティック判定
        name_lower = filename.lower()
        if any(k in name_lower for k in MUSIC_KEYWORDS):
            return _classify_music(pf)
        return ClassificationResult(
            target_path=[],
            reason="タグなし・判定不能 → Inbox に留置",
            is_classified=False,
        )

    tag = pf.tag
    if tag == "LCT":
        return _classify_lecture(pf)
    if tag in ("STY", "RES"):
        return _classify_self_study(pf)
    if tag in ("ADM", "PRJ"):
        return _classify_admin(pf)
    if tag == "MUS":
        return _classify_music(pf)
    if tag == "PSN":
        return _classify_personal(pf)

    return ClassificationResult(
        target_path=[TAG_TO_ROOT.get(tag, "00_Inbox")],
        reason=f"タグ {tag} → ルートフォルダのみ",
        is_classified=True,
    )
