"""
test_classifier.py
classifier.py の単体テスト。Google Drive への接続は不要。
"""

import pytest
from classifier import classify, parse_filename


# ------------------------------------------------------------------ #
#  parse_filename
# ------------------------------------------------------------------ #

def test_parse_basic():
    pf = parse_filename("20260401_【LCT】_LinAlg_Lec01_Note.pdf")
    assert pf.tag == "LCT"
    assert pf.date == "20260401"
    assert pf.category == "LinAlg"


def test_parse_no_date():
    pf = parse_filename("【MUS】_Bach_Suite01_Solo_Clean.pdf")
    assert pf.tag == "MUS"
    assert pf.date is None
    assert pf.category == "Bach"


def test_parse_no_tag():
    pf = parse_filename("random_file.pdf")
    assert pf.tag is None


# ------------------------------------------------------------------ #
#  classify - 講義 (LCT)
# ------------------------------------------------------------------ #

class TestLectureClassification:
    def test_note(self):
        r = classify("20260401_【LCT】_LinAlg_Lec01_Note.pdf")
        assert r.is_classified
        assert r.target_path[0] == "01_University_Lecture"
        assert "2026_Spring" in r.target_path
        assert "01_LinAlg1" in r.target_path
        assert "01_Lecture_Notes" in r.target_path

    def test_assignment(self):
        r = classify("20260510_【LCT】_LinAlg_Report01_Assign.pdf")
        assert r.is_classified
        assert "03_Assignments" in r.target_path

    def test_past_exam(self):
        r = classify("20250101_【LCT】_LinAlg_PastExam_2024.pdf")
        assert r.is_classified
        assert "00_Past_Exams_Archive" in r.target_path

    def test_autumn_semester(self):
        r = classify("20261001_【LCT】_Calc_Lec01_Note.pdf")
        assert "2026_Autumn" in r.target_path


# ------------------------------------------------------------------ #
#  classify - 音楽 (MUS)
# ------------------------------------------------------------------ #

class TestMusicClassification:
    def test_solo_concerto(self):
        r = classify("20260301_【MUS】_Dvorak_VcConc_Op104_Baerenreiter_Clean.pdf")
        assert r.is_classified
        assert r.target_path[0] == "04_Music_Score"
        assert "01_Solo" in r.target_path

    def test_symphony(self):
        r = classify("20260301_【MUS】_Beethoven_Sym05_Op67_Peters_Clean.pdf")
        assert r.is_classified
        assert "02_Orchestra" in r.target_path

    def test_quartet(self):
        r = classify("20260301_【MUS】_Schubert_Quartet_D810_Henle_Clean.pdf")
        assert r.is_classified
        assert "03_Chamber" in r.target_path

    def test_unsorted(self):
        r = classify("20260301_【MUS】_Unknown_Piece.pdf")
        assert r.is_classified
        assert "99_Unsorted" in r.target_path


# ------------------------------------------------------------------ #
#  classify - 自習 (STY)
# ------------------------------------------------------------------ #

class TestSelfStudyClassification:
    def test_cs(self):
        r = classify("20260501_【STY】_CS_AtCoder_ABC300.pdf")
        assert r.target_path[0] == "02_Self_Study"
        assert "01_CS_Programming" in r.target_path

    def test_math(self):
        r = classify("20260501_【STY】_Quants_Ito_Calculus_Note.pdf")
        assert "02_Math_Quant" in r.target_path

    def test_english(self):
        r = classify("20260501_【STY】_TOEFL_Practice_Set01.pdf")
        assert "03_English" in r.target_path


# ------------------------------------------------------------------ #
#  classify - 事務 (ADM)
# ------------------------------------------------------------------ #

class TestAdminClassification:
    def test_university_admin(self):
        r = classify("20260401_【ADM】_Univ_Scholarship_App.pdf")
        assert r.target_path[0] == "03_Admin_Life"
        assert "01_University_Admin" in r.target_path

    def test_finance(self):
        r = classify("20260401_【ADM】_Fin_BankStatement_Apr.pdf")
        assert "05_Finance_Bank" in r.target_path

    def test_medical_redirects_to_personal(self):
        r = classify("20260401_【ADM】_Med_HospitalReceipt.pdf")
        assert r.target_path[0] == "05_Personal_Health"
        assert "03_Medical" in r.target_path


# ------------------------------------------------------------------ #
#  classify - 個人 (PSN)
# ------------------------------------------------------------------ #

class TestPersonalClassification:
    def test_gym(self):
        r = classify("20260401_【PSN】_Gym_Workout_Log.pdf")
        assert r.target_path[0] == "05_Personal_Health"
        assert "01_Gym_Workout" in r.target_path

    def test_diet(self):
        r = classify("20260401_【PSN】_InBody_Result.pdf")
        assert "02_Diet_Nutrition" in r.target_path


# ------------------------------------------------------------------ #
#  classify - タグなし
# ------------------------------------------------------------------ #

def test_no_tag_not_classified():
    r = classify("random_document.pdf")
    assert not r.is_classified
    assert r.target_path == []


def test_no_tag_music_keyword():
    r = classify("Beethoven_Sym05_Peters.pdf")
    assert r.is_classified
    assert "02_Orchestra" in r.target_path
