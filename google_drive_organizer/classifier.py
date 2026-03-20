"""
classifier.py
ファイル名を解析して、移動先フォルダパスを決定するモジュール。

3つの命名規則に対応:
  General : YYYYMMDD_【TAG】_Category_Detail_Type_vXX.ext
  Admin   : YYYYMMDD_【ADM】_Category_Detail_Type.ext
  Music   : YYYYMMDD_【MUS】_Composer_Work_[arr_X]_[Key]_Instrument_[Publisher]_Type_[State].ext
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ================================================================== #
#  共通データ構造
# ================================================================== #

@dataclass
class ClassificationResult:
    """classify() の戻り値。"""
    target_path: list[str]   # Google Drive ルートからのフォルダ名リスト
    reason: str
    is_classified: bool


# ================================================================== #
#  パターン定数
# ================================================================== #

_TAG_RE    = re.compile(r"【([A-Z]{2,4})】", re.IGNORECASE)
_DATE_RE   = re.compile(r"^(\d{8})")
# 音楽: Key フィールド検出  例: C_dur, Es_dur, c_moll, fis_moll
_KEY_RE    = re.compile(r"^([A-Ga-g](?:is|es|s|b)?)_(dur|moll)$", re.IGNORECASE)
# 音楽: Arranger フィールド検出
_ARR_RE    = re.compile(r"^arr_", re.IGNORECASE)

# 楽器略称 (Instrument フィールド)
_INSTRUMENTS = {
    "vc", "vn", "va", "cb",           # 弦
    "pf", "org", "cemb",              # 鍵盤
    "fl", "ob", "cl", "fg", "sax",   # 木管
    "tp", "hn", "tb", "tba",         # 金管
    "perc", "timp",                   # 打楽器
    "orch", "str", "choir",           # アンサンブル
    "gt", "hp",                       # その他
}

# 出版社名 (Publisher フィールド)
_PUBLISHERS = {
    "baerenreiter", "breitkopf", "peters", "henle",
    "boosey", "schirmer", "durand", "ricordi",
    "imslp", "urtext",
}

# Type フィールド (音楽)
_MUS_TYPES = {"score", "part", "pfscore", "score_parts", "pf_part"}

# State フィールド (音楽)
_MUS_STATES = {"clean", "bowing", "lesson"}

# Type フィールド (一般/講義)
_GEN_TYPES = {"note", "slide", "ref", "rep", "exam", "ans", "log", "menu"}

# Type フィールド (事務)
_ADM_TYPES = {
    "guide", "notice", "form", "app",
    "cert", "bill", "rcpt", "contract", "card", "map",
}


# ================================================================== #
#  ユーティリティ
# ================================================================== #

def _stem(filename: str) -> str:
    """拡張子を除いたファイル名ステムを返す。"""
    return filename.rsplit(".", 1)[0]


def _extract_tag_and_fields(filename: str) -> tuple[Optional[str], list[str]]:
    """
    ファイル名からタグと、タグ以降のフィールドリストを返す。
    タグがなければ日付以降をフィールドとして扱う。
    """
    s = _stem(filename)

    tag_m = _TAG_RE.search(s)
    tag = tag_m.group(1).upper() if tag_m else None

    if tag_m:
        after = s[tag_m.end():].lstrip("_")
    else:
        date_m = _DATE_RE.match(s)
        after = s[date_m.end():].lstrip("_") if date_m else s

    fields = [f for f in after.split("_") if f]
    return tag, fields


def _extract_date(filename: str) -> Optional[str]:
    m = _DATE_RE.match(_stem(filename))
    return m.group(1) if m else None


# ================================================================== #
#  音楽ファイル専用パーサ
# ================================================================== #

@dataclass
class MusicFields:
    """【MUS】命名規則から抽出したフィールド群。"""
    composer: Optional[str]  = None
    work: Optional[str]      = None
    arranger: Optional[str]  = None
    key: Optional[str]       = None
    instrument: Optional[str]= None
    publisher: Optional[str] = None
    mus_type: Optional[str]  = None
    state: Optional[str]     = None
    raw_parts: list[str]     = field(default_factory=list)


def _parse_music_fields(parts: list[str]) -> MusicFields:
    """
    【MUS】タグ以降のフィールドリストを解析して MusicFields を返す。

    フォーマット:
      Composer_Work_[arr_X]_[Key]_Instrument_[Publisher]_Type_[State]

    Arranger / Key / Publisher / State はオプション。
    Instrument と Type は既知セットによる識別で位置を検出する。
    """
    mf = MusicFields(raw_parts=parts)
    if not parts:
        return mf

    # Composer は先頭
    mf.composer = parts[0]

    # 残りパーツを一つずつ分類
    remaining = parts[1:]
    work_parts: list[str] = []

    i = 0
    while i < len(remaining):
        p = remaining[i]
        p_lower = p.lower()

        # Arranger: 命名規則では "arr_Name" だが split("_") で
        #   ["arr", "Casals"] のように2トークンに分かれる。
        #   "arr" 単体トークン + 次トークンを結合して処理する。
        if p.lower() == "arr" and i + 1 < len(remaining):
            mf.arranger = "arr_" + remaining[i + 1]
            i += 2
            continue
        # "arr_Name" が1トークンとして来た場合 (スペースなし環境等)
        if _ARR_RE.match(p) and "_" in p:
            mf.arranger = p
            i += 1
            continue

        # Key: C_dur, c_moll 等 → split で分割されているので "C" + "dur" の2トークン
        if i + 1 < len(remaining):
            combined = p + "_" + remaining[i + 1]
            if _KEY_RE.match(combined):
                mf.key = combined
                i += 2
                continue

        # Instrument
        if p_lower in _INSTRUMENTS:
            mf.instrument = p
            i += 1
            continue

        # Publisher
        if p_lower in _PUBLISHERS:
            mf.publisher = p
            i += 1
            continue

        # Type (音楽)
        if p_lower in _MUS_TYPES:
            mf.mus_type = p
            i += 1
            continue

        # State
        if p_lower in _MUS_STATES:
            mf.state = p
            i += 1
            continue

        # それ以外 → Work の一部
        work_parts.append(p)
        i += 1

    if work_parts:
        mf.work = "_".join(work_parts)

    return mf


# ================================================================== #
#  音楽 サブフォルダ決定
# ================================================================== #

# Work 略称プレフィックス → サブフォルダ (優先度順に検索)
_WORK_SUBFOLDER: list[tuple[re.Pattern, str]] = [
    # オーケストラ系 (Sym は Solo の Conc より先にチェック)
    (re.compile(r"^sym\d*", re.I),          "02_Orchestra"),
    (re.compile(r"^overture",   re.I),       "02_Orchestra"),
    (re.compile(r"^tone",       re.I),       "02_Orchestra"),
    (re.compile(r"^sinfonia",   re.I),       "02_Orchestra"),
    # 室内楽
    (re.compile(r"quartet",     re.I),       "03_Chamber"),
    (re.compile(r"trio",        re.I),       "03_Chamber"),
    (re.compile(r"quintet",     re.I),       "03_Chamber"),
    (re.compile(r"sextet",      re.I),       "03_Chamber"),
    (re.compile(r"octet",       re.I),       "03_Chamber"),
    (re.compile(r"duo$",        re.I),       "03_Chamber"),
    # ソロ系 (コンチェルトはオーケストラ伴奏付きだがソロ譜として管理)
    (re.compile(r"conc",        re.I),       "01_Solo"),
    (re.compile(r"sonat",       re.I),       "01_Solo"),
    (re.compile(r"suite\d*",    re.I),       "01_Solo"),
    (re.compile(r"partita",     re.I),       "01_Solo"),
    (re.compile(r"chaconne",    re.I),       "01_Solo"),
    (re.compile(r"capricc",     re.I),       "01_Solo"),
    (re.compile(r"fantasia",    re.I),       "01_Solo"),
    (re.compile(r"elegy",       re.I),       "01_Solo"),
    (re.compile(r"piece",       re.I),       "01_Solo"),
    (re.compile(r"romanze",     re.I),       "01_Solo"),
]

# Instrument → サブフォルダ (Work で決定できなかった場合のフォールバック)
_INSTRUMENT_SUBFOLDER: dict[str, str] = {
    "orch": "02_Orchestra",
    "str":  "02_Orchestra",
    "choir":"02_Orchestra",
    # 独奏楽器 → Solo
    "vc": "01_Solo", "vn": "01_Solo", "va": "01_Solo",
    "pf": "01_Solo", "org": "01_Solo", "cemb": "01_Solo",
    "fl": "01_Solo", "ob": "01_Solo", "cl": "01_Solo",
    "gt": "01_Solo", "hp": "01_Solo",
}


def _music_subfolder(mf: MusicFields) -> str:
    """MusicFields から 04_Music_Score のサブフォルダを決定する。"""
    # 1) Work フィールドのプレフィックスパターンで判定
    if mf.work:
        work_first = mf.work.split("_")[0]  # 例: "VcConc" "Sym05" "Quartet"
        for pattern, subfolder in _WORK_SUBFOLDER:
            if pattern.search(work_first):
                return subfolder

    # 2) Instrument で判定
    if mf.instrument:
        sub = _INSTRUMENT_SUBFOLDER.get(mf.instrument.lower())
        if sub:
            return sub

    # 3) raw_parts 全体をフォールバック検索
    combined = " ".join(mf.raw_parts).lower()
    for pattern, subfolder in _WORK_SUBFOLDER:
        if pattern.search(combined):
            return subfolder

    return "99_Unsorted"


# ================================================================== #
#  事務 (ADM) カテゴリ → サブフォルダ
# ================================================================== #

# 命名規則で定義されたカテゴリ略称と完全一致させる
_ADM_CATEGORY_MAP: dict[str, str] = {
    "univ":   "01_University_Admin",
    "career": "02_Career_Intern",
    "gov":    "03_Government_Public",
    "house":  "04_Housing_Utilities",
    "fin":    "05_Finance_Bank",
    "med":    None,  # → 05_Personal_Health/03_Medical へリダイレクト
}


# ================================================================== #
#  一般/講義 カテゴリ → サブフォルダ
# ================================================================== #

# 【LCT】科目 Category → 科目フォルダ名
_SUBJECT_MAP: dict[str, str] = {
    "linalg":   "01_LinAlg",
    "calc":     "02_Calc",
    "probstat": "03_ProbStat",
    "diffeq":   "04_DiffEq",
    "phys":     "05_Physics",
    "mech":     "05_Physics",
    "qm":       "05_Physics",
    "elec":     "05_Physics",
    "cs":       "06_CS",
    "algo":     "07_Algorithm",
    "prog":     "08_Programming",
    "ml":       "09_ML_DL",
    "dl":       "09_ML_DL",
    "econ":     "10_Econ",
    "fineng":   "11_FinEng",
    "quants":   "11_FinEng",
    "metrics":  "12_Metrics",
    "chem":     "13_Chemistry",
}

# 【LCT】Type → 科目内サブフォルダ
_LCT_TYPE_SUBFOLDER: dict[str, str] = {
    "note":  "01_Lecture_Notes",
    "ref":   "01_Lecture_Notes",   # レジュメ・配布資料
    "slide": "02_Handouts",
    "rep":   "03_Assignments",
    "exam":  "03_Assignments",
    "ans":   "03_Assignments",
}

# 【STY】【RES】Category → サブフォルダ
_STUDY_MAP: dict[str, str] = {
    # CS
    "cs":      "01_CS_Programming",
    "algo":    "01_CS_Programming",
    "cp":      "01_CS_Programming",   # 競技プログラミング
    "ml":      "01_CS_Programming",
    "dl":      "01_CS_Programming",
    # 数学・クオンツ
    "linalg":  "02_Math_Quant",
    "calc":    "02_Math_Quant",
    "probstat":"02_Math_Quant",
    "diffeq":  "02_Math_Quant",
    "quants":  "02_Math_Quant",
    "fineng":  "02_Math_Quant",
    "econ":    "02_Math_Quant",
    "metrics": "02_Math_Quant",
    "phys":    "02_Math_Quant",
    # 英語
    "english": "03_English",
    "toefl":   "03_English",
    "eng":     "03_English",
}

# 【PSN】Category → サブフォルダ
_PERSONAL_MAP: dict[str, str] = {
    "gym":    "01_Gym_Workout",
    "health": "01_Gym_Workout",   # 命名規則では Health も Gym 扱い
    "diet":   "02_Diet_Nutrition",
    "med":    "03_Medical",
}


# ================================================================== #
#  タグ別分類関数
# ================================================================== #

def _classify_music(tag: str, fields: list[str], filename: str) -> ClassificationResult:
    """【MUS】命名規則に基づく詳細分類。"""
    root = "04_Music_Score"
    mf = _parse_music_fields(fields)
    subfolder = _music_subfolder(mf)

    reason_parts = []
    if mf.work:
        reason_parts.append(f"Work={mf.work}")
    if mf.instrument:
        reason_parts.append(f"Instrument={mf.instrument}")
    reason = "音楽: " + (", ".join(reason_parts) or "フィールド不明") + f" → {subfolder}"

    return ClassificationResult(
        target_path=[root, subfolder],
        reason=reason,
        is_classified=True,
    )


def _classify_admin(tag: str, fields: list[str], filename: str) -> ClassificationResult:
    """【ADM】命名規則に基づく詳細分類。
    フォーマット: Category_Detail_Type
    """
    root = "03_Admin_Life"

    # Category は fields[0] で完全一致
    category = fields[0].lower() if fields else ""

    if category in _ADM_CATEGORY_MAP:
        subfolder = _ADM_CATEGORY_MAP[category]

        # Med は Personal_Health へリダイレクト
        if subfolder is None:
            return ClassificationResult(
                target_path=["05_Personal_Health", "03_Medical"],
                reason=f"ADM Category=Med → 05_Personal_Health/03_Medical",
                is_classified=True,
            )

        # Type フィールドを取得してログに付記 (フォルダには影響しない)
        type_field = _find_adm_type(fields[1:])
        reason = f"ADM Category={fields[0]}"
        if type_field:
            reason += f", Type={type_field}"
        reason += f" → {subfolder}"

        return ClassificationResult(
            target_path=[root, subfolder],
            reason=reason,
            is_classified=True,
        )

    # Category が定義外 → ファイル名全体から緩くフォールバック
    name_lower = filename.lower()
    for key, sub in _ADM_CATEGORY_MAP.items():
        if key in name_lower and sub is not None:
            return ClassificationResult(
                target_path=[root, sub],
                reason=f"ADM フォールバック: '{key}' を検出 → {sub}",
                is_classified=True,
            )

    return ClassificationResult(
        target_path=[root],
        reason=f"ADM Category='{category}' 未定義 → ルート",
        is_classified=True,
    )


def _find_adm_type(parts: list[str]) -> Optional[str]:
    """fields の中から ADM Type を探して返す。"""
    for p in parts:
        if p.lower() in _ADM_TYPES:
            return p
    return None


def _classify_lecture(tag: str, fields: list[str], filename: str) -> ClassificationResult:
    """【LCT】命名規則に基づく詳細分類。
    フォーマット: Category_Detail_Type_[vXX]
    """
    root = "01_University_Lecture"

    # --- Type フィールドを先に抽出 ---
    gen_type = _find_gen_type(fields)

    # --- Exam/Ans は過去問アーカイブ ---
    if gen_type in ("exam", "ans"):
        return ClassificationResult(
            target_path=[root, "00_Past_Exams_Archive"],
            reason=f"LCT Type={gen_type} → 過去問アーカイブ",
            is_classified=True,
        )

    # --- 学期フォルダ (日付から推定) ---
    date = _extract_date(filename)
    semester = _detect_semester(date, filename.lower())

    # --- 科目フォルダ (Category から完全一致 → フォールバック部分一致) ---
    category = fields[0].lower() if fields else ""
    subject = _SUBJECT_MAP.get(category)
    if subject is None:
        # 部分一致フォールバック
        for key, val in _SUBJECT_MAP.items():
            if key in category or category in key:
                subject = val
                break

    # --- 科目内サブフォルダ (Type フィールドから決定) ---
    subtype = _LCT_TYPE_SUBFOLDER.get(gen_type) if gen_type else None

    path = [root, semester]
    if subject:
        path.append(subject)
    if subject and subtype:
        path.append(subtype)

    reason = f"LCT: {semester}"
    if subject:
        reason += f"/{subject}"
    if gen_type:
        reason += f", Type={gen_type}"

    return ClassificationResult(
        target_path=path,
        reason=reason,
        is_classified=True,
    )


def _classify_study(tag: str, fields: list[str], filename: str) -> ClassificationResult:
    """【STY】【RES】命名規則に基づく分類。
    フォーマット: Category_Detail_Type_[vXX]
    """
    root = "02_Self_Study"

    category = fields[0].lower() if fields else ""
    subfolder = _STUDY_MAP.get(category)

    if subfolder is None:
        # 部分一致フォールバック
        name_lower = filename.lower()
        for key, val in _STUDY_MAP.items():
            if key in name_lower:
                subfolder = val
                break

    if subfolder:
        return ClassificationResult(
            target_path=[root, subfolder],
            reason=f"STY/RES Category='{fields[0] if fields else ''}' → {subfolder}",
            is_classified=True,
        )

    return ClassificationResult(
        target_path=[root],
        reason=f"STY/RES: Category 未判定 → ルート",
        is_classified=True,
    )


def _classify_project(tag: str, fields: list[str], filename: str) -> ClassificationResult:
    """【PRJ】命名規則に基づく分類。
    インターン・開発成果物は Career フォルダへ。
    """
    return ClassificationResult(
        target_path=["03_Admin_Life", "02_Career_Intern"],
        reason="PRJ → 03_Admin_Life/02_Career_Intern",
        is_classified=True,
    )


def _classify_personal(tag: str, fields: list[str], filename: str) -> ClassificationResult:
    """【PSN】命名規則に基づく分類。
    フォーマット: Category_Detail_Type_[vXX]
    """
    root = "05_Personal_Health"

    category = fields[0].lower() if fields else ""
    subfolder = _PERSONAL_MAP.get(category)

    if subfolder is None:
        name_lower = filename.lower()
        for key, val in _PERSONAL_MAP.items():
            if key in name_lower:
                subfolder = val
                break

    if subfolder:
        return ClassificationResult(
            target_path=[root, subfolder],
            reason=f"PSN Category='{fields[0] if fields else ''}' → {subfolder}",
            is_classified=True,
        )

    return ClassificationResult(
        target_path=[root],
        reason="PSN: Category 未判定 → ルート",
        is_classified=True,
    )


# ================================================================== #
#  共通ヘルパー
# ================================================================== #

def _find_gen_type(parts: list[str]) -> Optional[str]:
    """fields の中から General/Lecture 用 Type フィールドを探す。"""
    for p in parts:
        if p.lower() in _GEN_TYPES:
            return p.lower()
    return None


def _detect_semester(date: Optional[str], name_lower: str) -> str:
    """日付またはキーワードから学期フォルダ名 (例: 2026_Spring) を返す。"""
    year: Optional[str] = None
    if date and date != "00000000":
        year = date[:4]

    # キーワード優先
    if any(kw in name_lower for kw in ("spring", "spr", "前期", "1q", "2q")):
        season = "Spring"
    elif any(kw in name_lower for kw in ("autumn", "fall", "aut", "後期", "3q", "4q")):
        season = "Autumn"
    elif date and date != "00000000":
        month = int(date[4:6])
        season = "Spring" if 1 <= month <= 7 else "Autumn"
    else:
        season = "Spring"

    return f"{year}_{season}" if year else "2026_Spring"


# ================================================================== #
#  メイン分類関数 (公開 API)
# ================================================================== #

_TAG_DISPATCH = {
    "LCT": _classify_lecture,
    "STY": _classify_study,
    "RES": _classify_study,
    "PRJ": _classify_project,
    "ADM": _classify_admin,
    "MUS": _classify_music,
    "PSN": _classify_personal,
}


def classify(filename: str) -> ClassificationResult:
    """
    命名規則に従ったファイル名を解析し、移動先フォルダパスを返す。

    Parameters
    ----------
    filename : str
        ファイル名 (拡張子あり)。パスは含まない。

    Returns
    -------
    ClassificationResult
        - target_path: Google Drive ルートからのフォルダ名リスト
          例: ["01_University_Lecture", "2026_Spring", "01_LinAlg", "01_Lecture_Notes"]
        - is_classified: False の場合は Inbox に留置
    """
    tag, fields = _extract_tag_and_fields(filename)

    if tag is None:
        # タグなし → 音楽ファイルのヒューリスティック判定のみ試みる
        name_lower = filename.lower()
        for pattern, _ in _WORK_SUBFOLDER:
            if pattern.search(name_lower):
                # タグなし音楽ファイルとして処理
                return _classify_music("MUS", fields, filename)
        return ClassificationResult(
            target_path=[],
            reason="タグ【】なし・判定不能 → Inbox に留置",
            is_classified=False,
        )

    handler = _TAG_DISPATCH.get(tag)
    if handler is None:
        return ClassificationResult(
            target_path=[],
            reason=f"未知のタグ 【{tag}】 → Inbox に留置",
            is_classified=False,
        )

    return handler(tag, fields, filename)
