"""
ai_classifier.py
OCR テキストとファイル名を LLM (Google Gemini API) に送り、
フォルダ構造に基づいて柔軟にファイルを分類するモジュール。

必要:
  pip install google-generativeai
  環境変数 GEMINI_API_KEY を設定

使い方 (local_organizer.py から):
  python local_organizer.py --root <path> --ai
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from classifier import ClassificationResult

logger = logging.getLogger(__name__)

# ================================================================== #
#  フォルダ構造定義 (プロンプトに埋め込む)
# ================================================================== #

FOLDER_STRUCTURE = """\
01_University_Lecture/
  00_Past_Exams_Archive/          # 過去問・模範解答
  {YYYY}_{Spring|Autumn}/         # 学期フォルダ (例: 2026_Spring)
    01_LinAlg/                    # 線形代数
      01_Lecture_Notes/
      02_Handouts/
      03_Assignments/
    02_Calc/                      # 微分積分
    03_ProbStat/                  # 確率統計
    04_DiffEq/                    # 微分方程式
    05_Physics/                   # 物理
    06_CS/                        # 計算機科学
    07_Algorithm/                 # アルゴリズム
    08_Programming/               # プログラミング
    09_ML_DL/                     # 機械学習・深層学習
    10_Econ/                      # 経済学
    11_FinEng/                    # 金融工学・クオンツ
    12_Metrics/                   # 計量経済学
    13_Chemistry/                 # 化学

02_Self_Study/
  01_CS_Programming/              # CS・プログラミング独学
  02_Math_Quant/                  # 数学・クオンツ独学
  03_English/                     # 英語・TOEFL

03_Admin_Life/
  01_University_Admin/            # 大学事務 (在学証明, 奨学金, 成績等)
  02_Career_Intern/               # 就活・インターン
  03_Government_Public/           # 役所 (住民票, マイナンバー, 年金等)
  04_Housing_Utilities/           # 住居・光熱費 (賃貸, 電気, ガス, 水道等)
  05_Finance_Bank/                # 金融・銀行 (口座, クレジットカード, 保険等)

04_Music_Score/
  01_Solo/                        # ソロ曲 (ソナタ, 協奏曲, 組曲等)
  02_Orchestra/                   # オーケストラ (交響曲, 序曲等)
  03_Chamber/                     # 室内楽 (四重奏, 三重奏, 五重奏等)
  99_Unsorted/                    # 分類不明の楽譜

05_Personal_Health/
  01_Gym_Workout/                 # ジム・筋トレ
  02_Diet_Nutrition/              # 食事・栄養
  03_Medical/                     # 医療 (診察, 処方箋, 検査等)
"""

SYSTEM_PROMPT = """\
あなたはファイル分類アシスタントです。
ユーザーが提供するファイル名とファイル内容（OCRテキスト）を分析し、
以下のフォルダ構造の中で最も適切な移動先を1つ決定してください。

## フォルダ構造
{folder_structure}

## ルール
1. ファイル内容を最優先で判断材料にしてください。ファイル名も参考にします。
2. 大学講義資料の場合、内容から科目・学期を推定してください。
   - 学期: 1〜7月 → Spring, 8〜12月 → Autumn
   - 年度は内容中の日付や文脈から推定。不明なら 2026_Spring とする。
3. 過去問・試験問題は 00_Past_Exams_Archive に分類してください。
4. 楽譜・音楽関連は曲の編成から Solo/Orchestra/Chamber を判断してください。
5. どのカテゴリにも該当しない場合は null を返してください（Inbox に留置）。

## 出力形式
必ず以下の JSON 形式のみを出力してください。他のテキストは不要です。
{{
  "target_path": ["フォルダ1", "フォルダ2", ...] or null,
  "reason": "分類理由（日本語で簡潔に）"
}}

例:
{{
  "target_path": ["01_University_Lecture", "2026_Spring", "01_LinAlg", "01_Lecture_Notes"],
  "reason": "線形代数の講義ノート。行列の固有値分解について記載。"
}}
""".format(folder_structure=FOLDER_STRUCTURE)


# ================================================================== #
#  LLM 呼び出し (Google Gemini API)
# ================================================================== #

def _call_gemini(filename: str, ocr_text: str, model: str = "gemini-2.0-flash") -> Optional[dict]:
    """Google Gemini API を呼び出してファイル分類結果の辞書を返す。"""
    try:
        from google import genai
    except ImportError:
        raise ImportError(
            "google-genai が未インストールです: pip install google-genai\n"
            "環境変数 GEMINI_API_KEY も設定してください。"
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "環境変数 GEMINI_API_KEY が設定されていません。\n"
            "Windows : set GEMINI_API_KEY=AIza...\n"
            "macOS/Linux: export GEMINI_API_KEY='AIza...'\n"
            "Google AI Studio (https://aistudio.google.com/apikey) で無料取得できます。"
        )

    client = genai.Client(api_key=api_key)

    # OCR テキストが長すぎる場合は先頭を切り詰め
    max_chars = 3000
    text_truncated = ocr_text[:max_chars]
    if len(ocr_text) > max_chars:
        text_truncated += "\n...(以下省略)"

    user_message = (
        f"## ファイル名\n{filename}\n\n"
        f"## ファイル内容 (OCR テキスト)\n{text_truncated}"
    )

    logger.debug("AI分類リクエスト送信: model=%s, filename='%s'", model, filename)

    response = client.models.generate_content(
        model=model,
        contents=[
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\n" + user_message}]},
        ],
        config={
            "temperature": 0.0,
            "max_output_tokens": 300,
        },
    )

    raw = response.text.strip()
    logger.debug("AI応答: %s", raw)

    # JSON パース (```json ... ``` で囲まれている場合も対処)
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    return json.loads(raw)


# ================================================================== #
#  公開 API
# ================================================================== #

def classify_with_ai(
    filename: str,
    ocr_text: str,
    model: str = "gemini-2.0-flash",
) -> ClassificationResult:
    """
    OCR テキストとファイル名を Gemini に送り、分類結果を返す。

    Parameters
    ----------
    filename  : ファイル名
    ocr_text  : OCR で抽出したテキスト
    model     : 使用する Gemini モデル (デフォルト: gemini-2.0-flash)

    Returns
    -------
    ClassificationResult
    """
    if not ocr_text or not ocr_text.strip():
        return ClassificationResult(
            target_path=[],
            reason="AI分類: OCRテキストが空のため分類不能",
            is_classified=False,
        )

    try:
        result = _call_gemini(filename, ocr_text, model=model)
    except ImportError as e:
        logger.error("%s", e)
        return ClassificationResult(
            target_path=[],
            reason=f"AI分類: ライブラリエラー — {e}",
            is_classified=False,
        )
    except RuntimeError as e:
        logger.error("%s", e)
        return ClassificationResult(
            target_path=[],
            reason=f"AI分類: 設定エラー — {e}",
            is_classified=False,
        )
    except json.JSONDecodeError as e:
        logger.warning("AI応答のJSONパース失敗: %s", e)
        return ClassificationResult(
            target_path=[],
            reason="AI分類: 応答の解析に失敗",
            is_classified=False,
        )
    except Exception as e:
        logger.warning("AI分類エラー: %s", e)
        return ClassificationResult(
            target_path=[],
            reason=f"AI分類: API呼び出し失敗 — {e}",
            is_classified=False,
        )

    target_path = result.get("target_path")
    reason = result.get("reason", "AI分類")

    if target_path is None or not isinstance(target_path, list):
        return ClassificationResult(
            target_path=[],
            reason=f"AI分類: 該当カテゴリなし — {reason}",
            is_classified=False,
        )

    # パス要素のバリデーション (空文字やスラッシュを除去)
    clean_path = [p.strip() for p in target_path if isinstance(p, str) and p.strip()]
    if not clean_path:
        return ClassificationResult(
            target_path=[],
            reason=f"AI分類: パスが空 — {reason}",
            is_classified=False,
        )

    logger.info("AI分類: '%s' → %s (%s)", filename, " / ".join(clean_path), reason)
    return ClassificationResult(
        target_path=clean_path,
        reason=f"AI分類: {reason}",
        is_classified=True,
    )
