"""
test_classifier.py
classifier.py の単体テスト。Google Drive への接続は不要。

命名規則:
  General : YYYYMMDD_【TAG】_Category_Detail_Type_vXX.ext
  Admin   : YYYYMMDD_【ADM】_Category_Detail_Type.ext
  Music   : YYYYMMDD_【MUS】_Composer_Work_[arr_X]_[Key]_Instrument_[Publisher]_Type_[State].ext
"""

import pytest
from classifier import classify, _parse_music_fields, _extract_tag_and_fields


# ================================================================== #
#  内部パーサのテスト
# ================================================================== #

class TestExtractTagAndFields:
    def test_full_format(self):
        tag, fields = _extract_tag_and_fields(
            "20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf"
        )
        assert tag == "LCT"
        assert fields == ["LinAlg", "Lec01", "Note", "v01"]

    def test_no_date(self):
        tag, fields = _extract_tag_and_fields("【MUS】_Bach_Suite01_Vc_Part_Clean.pdf")
        assert tag == "MUS"
        assert fields[0] == "Bach"

    def test_no_tag(self):
        tag, fields = _extract_tag_and_fields("random_file.pdf")
        assert tag is None

    def test_adm_format(self):
        tag, fields = _extract_tag_and_fields(
            "20260401_【ADM】_Univ_Scholarship_App.pdf"
        )
        assert tag == "ADM"
        assert fields == ["Univ", "Scholarship", "App"]


class TestParseMusicFields:
    def test_full_fields_with_key(self):
        # Composer_Work_Key_Instrument_Publisher_Type_State
        _, fields = _extract_tag_and_fields(
            "17870101_【MUS】_Mozart_VnConc5_A_dur_Vn_Baerenreiter_Part_Clean.pdf"
        )
        mf = _parse_music_fields(fields)
        assert mf.composer == "Mozart"
        assert "VnConc5" in mf.work
        assert mf.key == "A_dur"
        assert mf.instrument == "Vn"
        assert mf.publisher == "Baerenreiter"
        assert mf.mus_type == "Part"
        assert mf.state == "Clean"

    def test_arranger(self):
        _, fields = _extract_tag_and_fields(
            "19360101_【MUS】_Dvorak_VcConc_Op104_arr_Casals_Vc_Peters_Part_Bowing.pdf"
        )
        mf = _parse_music_fields(fields)
        assert mf.composer == "Dvorak"
        assert mf.arranger == "arr_Casals"
        assert mf.instrument == "Vc"
        assert mf.publisher == "Peters"
        assert mf.state == "Bowing"

    def test_no_optional_fields(self):
        _, fields = _extract_tag_and_fields(
            "00000000_【MUS】_Bach_CelloSuite1_BWV1007_Vc_Part.pdf"
        )
        mf = _parse_music_fields(fields)
        assert mf.composer == "Bach"
        assert mf.instrument == "Vc"
        assert mf.mus_type == "Part"
        assert mf.key is None
        assert mf.publisher is None
        assert mf.state is None


# ================================================================== #
#  【LCT】 講義ファイルの分類
# ================================================================== #

class TestLectureClassification:

    def test_note_to_lecture_notes_subfolder(self):
        r = classify("20260401_【LCT】_LinAlg_Lec01_Note_v01.pdf")
        assert r.is_classified
        assert r.target_path[0] == "01_University_Lecture"
        assert "2026_Spring" in r.target_path
        assert "01_LinAlg" in r.target_path
        assert "01_Lecture_Notes" in r.target_path

    def test_slide_to_handouts(self):
        r = classify("20260415_【LCT】_LinAlg_Lec03_Slide_v01.pdf")
        assert "02_Handouts" in r.target_path

    def test_ref_to_lecture_notes(self):
        r = classify("20260422_【LCT】_ProbStat_Week02_Ref_v01.pdf")
        assert "01_Lecture_Notes" in r.target_path
        assert "03_ProbStat" in r.target_path

    def test_report_to_assignments(self):
        r = classify("20260510_【LCT】_LinAlg_Report01_Rep_v01.pdf")
        assert "03_Assignments" in r.target_path

    def test_exam_to_past_exams_archive(self):
        r = classify("20250120_【LCT】_Calc_MidtermExam_Exam.pdf")
        assert "00_Past_Exams_Archive" in r.target_path

    def test_ans_to_past_exams_archive(self):
        r = classify("20250120_【LCT】_Calc_MidtermExam_Ans.pdf")
        assert "00_Past_Exams_Archive" in r.target_path

    def test_autumn_semester_by_month(self):
        r = classify("20261001_【LCT】_DiffEq_Lec01_Note_v01.pdf")
        assert "2026_Autumn" in r.target_path
        assert "04_DiffEq" in r.target_path

    def test_cs_subject(self):
        r = classify("20260601_【LCT】_CS_Lecture05_Note_v01.pdf")
        assert "06_CS" in r.target_path

    def test_ml_subject(self):
        r = classify("20260601_【LCT】_ML_NeuralNet_Slide_v01.pdf")
        assert "09_ML_DL" in r.target_path

    def test_fineng_subject(self):
        r = classify("20260601_【LCT】_FinEng_BlackScholes_Note_v01.pdf")
        assert "11_FinEng" in r.target_path


# ================================================================== #
#  【STY】【RES】 自習ファイルの分類
# ================================================================== #

class TestSelfStudyClassification:

    def test_cs_programming(self):
        r = classify("20260501_【STY】_CS_AtCoder_ABC300_Note_v01.pdf")
        assert r.target_path[0] == "02_Self_Study"
        assert "01_CS_Programming" in r.target_path

    def test_cp_competitive_programming(self):
        r = classify("20260501_【STY】_CP_DijkstraMemo_Note_v01.pdf")
        assert "01_CS_Programming" in r.target_path

    def test_quants_math(self):
        r = classify("20260501_【STY】_Quants_ItoFormula_Note_v01.pdf")
        assert "02_Math_Quant" in r.target_path

    def test_fineng(self):
        r = classify("20260501_【STY】_FinEng_BSModel_Ref_v01.pdf")
        assert "02_Math_Quant" in r.target_path

    def test_toefl_english(self):
        r = classify("20260501_【STY】_TOEFL_PracticeSet01_Log_v01.pdf")
        assert "03_English" in r.target_path

    def test_res_tag(self):
        r = classify("20260601_【RES】_ML_TransformerPaper_Ref_v01.pdf")
        assert r.target_path[0] == "02_Self_Study"
        assert "01_CS_Programming" in r.target_path


# ================================================================== #
#  【PRJ】 プロジェクトの分類
# ================================================================== #

class TestProjectClassification:

    def test_prj_goes_to_career(self):
        r = classify("20260601_【PRJ】_InternXYZ_DevReport_Rep_v01.pdf")
        assert r.target_path == ["03_Admin_Life", "02_Career_Intern"]


# ================================================================== #
#  【ADM】 事務ファイルの分類 (Category 完全一致)
# ================================================================== #

class TestAdminClassification:

    def test_univ_scholarship(self):
        r = classify("20260401_【ADM】_Univ_Scholarship_App.pdf")
        assert r.target_path == ["03_Admin_Life", "01_University_Admin"]

    def test_univ_tuition_bill(self):
        r = classify("20260401_【ADM】_Univ_Tuition_Bill.pdf")
        assert r.target_path == ["03_Admin_Life", "01_University_Admin"]

    def test_career_intern_contract(self):
        r = classify("20260601_【ADM】_Career_InternABC_Contract.pdf")
        assert r.target_path == ["03_Admin_Life", "02_Career_Intern"]

    def test_gov_juminhyo(self):
        r = classify("20260401_【ADM】_Gov_JuminHyo_Cert.pdf")
        assert r.target_path == ["03_Admin_Life", "03_Government_Public"]

    def test_house_rent(self):
        r = classify("20260401_【ADM】_House_Rent_Bill.pdf")
        assert r.target_path == ["03_Admin_Life", "04_Housing_Utilities"]

    def test_house_electricity(self):
        r = classify("20260501_【ADM】_House_Electricity_Bill.pdf")
        assert r.target_path == ["03_Admin_Life", "04_Housing_Utilities"]

    def test_fin_bank(self):
        r = classify("20260401_【ADM】_Fin_BankStatement_Apr_Notice.pdf")
        assert r.target_path == ["03_Admin_Life", "05_Finance_Bank"]

    def test_med_redirects_to_personal_health(self):
        """Med カテゴリは 05_Personal_Health/03_Medical へリダイレクト。"""
        r = classify("20260401_【ADM】_Med_HospitalReceipt_Rcpt.pdf")
        assert r.target_path == ["05_Personal_Health", "03_Medical"]


# ================================================================== #
#  【MUS】 音楽ファイルの分類 (命名規則フィールドで精密判定)
# ================================================================== #

class TestMusicClassification:

    # --- 01_Solo ---
    def test_cello_concerto_solo(self):
        r = classify(
            "18950101_【MUS】_Dvorak_VcConc_Op104_b_moll_Vc_Baerenreiter_Part_Clean.pdf"
        )
        assert r.target_path == ["04_Music_Score", "01_Solo"]

    def test_bach_suite_solo(self):
        r = classify(
            "00000000_【MUS】_Bach_CelloSuite1_BWV1007_c_moll_Vc_Baerenreiter_Part_Clean.pdf"
        )
        assert r.target_path == ["04_Music_Score", "01_Solo"]

    def test_violin_sonata_solo(self):
        r = classify(
            "18050101_【MUS】_Beethoven_VnSonat5_Op24_F_dur_Vn_Peters_Part_Bowing.pdf"
        )
        assert r.target_path == ["04_Music_Score", "01_Solo"]

    def test_instrument_fallback_to_solo(self):
        """Work パターンに一致しなくても Vc なら Solo。"""
        r = classify(
            "00000000_【MUS】_Popper_Etude_Op73_Vc_Peters_Part.pdf"
        )
        assert r.target_path == ["04_Music_Score", "01_Solo"]

    # --- 02_Orchestra ---
    def test_symphony_orchestra(self):
        r = classify(
            "18080101_【MUS】_Beethoven_Sym05_Op67_c_moll_Orch_Baerenreiter_Score.pdf"
        )
        assert r.target_path == ["04_Music_Score", "02_Orchestra"]

    def test_orchestra_instrument(self):
        """Instrument=Orch でも Orchestra へ。"""
        r = classify(
            "00000000_【MUS】_Brahms_Sym4_Op98_e_moll_Orch_Breitkopf_Score.pdf"
        )
        assert r.target_path == ["04_Music_Score", "02_Orchestra"]

    # --- 03_Chamber ---
    def test_string_quartet_chamber(self):
        r = classify(
            "18270101_【MUS】_Schubert_StringQuartet_D810_d_moll_Vc_Henle_Part_Clean.pdf"
        )
        assert r.target_path == ["04_Music_Score", "03_Chamber"]

    def test_piano_trio_chamber(self):
        r = classify(
            "19080101_【MUS】_Ravel_PianoTrio_a_moll_Vc_Durand_Part_Lesson.pdf"
        )
        assert r.target_path == ["04_Music_Score", "03_Chamber"]

    # --- 99_Unsorted ---
    def test_unsorted_when_no_clues(self):
        """楽器フィールドも Work パターンも持たない場合は 99_Unsorted。"""
        r = classify("00000000_【MUS】_Unknown_PieceXYZ_Score.pdf")
        # "PieceXYZ" は Work パターン "piece" に一致 → Solo に振られる
        # → 完全に判定不能なケースで確認
        r2 = classify("00000000_【MUS】_UnknownComposer_WerkeNr99_Score.pdf")
        assert r2.target_path == ["04_Music_Score", "99_Unsorted"]


# ================================================================== #
#  【PSN】 個人・健康ファイルの分類
# ================================================================== #

class TestPersonalClassification:

    def test_gym_workout(self):
        r = classify("20260401_【PSN】_Gym_ChestDay_Log_v01.pdf")
        assert r.target_path == ["05_Personal_Health", "01_Gym_Workout"]

    def test_health_to_gym(self):
        r = classify("20260401_【PSN】_Health_InBody_Log_v01.pdf")
        assert r.target_path == ["05_Personal_Health", "01_Gym_Workout"]

    def test_diet(self):
        r = classify("20260401_【PSN】_Diet_MealPlan_Note_v01.pdf")
        assert r.target_path == ["05_Personal_Health", "02_Diet_Nutrition"]

    def test_med(self):
        r = classify("20260401_【PSN】_Med_HospitalVisit_Rcpt.pdf")
        assert r.target_path == ["05_Personal_Health", "03_Medical"]


# ================================================================== #
#  タグなし・不明ファイル
# ================================================================== #

class TestUntaggedFiles:

    def test_no_tag_returns_not_classified(self):
        r = classify("random_document.pdf")
        assert not r.is_classified
        assert r.target_path == []

    def test_unknown_tag_not_classified(self):
        r = classify("20260401_【XYZ】_Foo_Bar.pdf")
        assert not r.is_classified
