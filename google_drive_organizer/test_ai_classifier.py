"""
test_ai_classifier.py
ai_classifier.py のユニットテスト。
OpenAI API を呼ばずにモックでテストする。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ai_classifier import classify_with_ai, SYSTEM_PROMPT, FOLDER_STRUCTURE


# ================================================================== #
#  classify_with_ai
# ================================================================== #

class TestClassifyWithAi:
    """classify_with_ai の基本テスト。"""

    def test_empty_text_returns_unclassified(self):
        result = classify_with_ai("test.pdf", "")
        assert not result.is_classified
        assert result.target_path == []

    def test_none_text_returns_unclassified(self):
        result = classify_with_ai("test.pdf", None)
        assert not result.is_classified

    def test_whitespace_only_text_returns_unclassified(self):
        result = classify_with_ai("test.pdf", "   \n  ")
        assert not result.is_classified

    @patch("ai_classifier._call_openai")
    def test_successful_classification(self, mock_call):
        mock_call.return_value = {
            "target_path": ["01_University_Lecture", "2026_Spring", "01_LinAlg"],
            "reason": "線形代数の講義ノート",
        }
        result = classify_with_ai("lecture.pdf", "行列の固有値分解について...")
        assert result.is_classified
        assert result.target_path == ["01_University_Lecture", "2026_Spring", "01_LinAlg"]
        assert "線形代数" in result.reason

    @patch("ai_classifier._call_openai")
    def test_null_target_path(self, mock_call):
        mock_call.return_value = {
            "target_path": None,
            "reason": "分類不能",
        }
        result = classify_with_ai("random.pdf", "何かのテキスト")
        assert not result.is_classified

    @patch("ai_classifier._call_openai")
    def test_api_error_returns_unclassified(self, mock_call):
        mock_call.side_effect = Exception("API Error")
        result = classify_with_ai("test.pdf", "テキスト内容")
        assert not result.is_classified
        assert "API呼び出し失敗" in result.reason

    @patch("ai_classifier._call_openai")
    def test_json_parse_error(self, mock_call):
        mock_call.side_effect = json.JSONDecodeError("err", "doc", 0)
        result = classify_with_ai("test.pdf", "テキスト内容")
        assert not result.is_classified

    @patch("ai_classifier._call_openai")
    def test_import_error(self, mock_call):
        mock_call.side_effect = ImportError("openai not installed")
        result = classify_with_ai("test.pdf", "テキスト内容")
        assert not result.is_classified

    @patch("ai_classifier._call_openai")
    def test_path_with_empty_strings_cleaned(self, mock_call):
        mock_call.return_value = {
            "target_path": ["04_Music_Score", "", "01_Solo", "  "],
            "reason": "楽譜",
        }
        result = classify_with_ai("score.pdf", "ソナタ テキスト")
        assert result.is_classified
        assert result.target_path == ["04_Music_Score", "01_Solo"]


# ================================================================== #
#  プロンプト内容の検証
# ================================================================== #

class TestPromptContents:
    """プロンプトにフォルダ構造が正しく含まれているか検証。"""

    def test_folder_structure_contains_key_folders(self):
        assert "01_University_Lecture" in FOLDER_STRUCTURE
        assert "02_Self_Study" in FOLDER_STRUCTURE
        assert "03_Admin_Life" in FOLDER_STRUCTURE
        assert "04_Music_Score" in FOLDER_STRUCTURE
        assert "05_Personal_Health" in FOLDER_STRUCTURE

    def test_system_prompt_contains_json_format(self):
        assert "target_path" in SYSTEM_PROMPT
        assert "reason" in SYSTEM_PROMPT
