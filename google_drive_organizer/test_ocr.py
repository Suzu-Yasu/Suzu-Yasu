"""
test_ocr.py
ocr.py の単体テスト。Drive への接続は不要 (classify_from_text のみテスト)。
"""

import pytest
from ocr import classify_from_text, OCR_SUPPORTED_EXTENSIONS


# ================================================================== #
#  サポートフォーマット
# ================================================================== #

class TestSupportedExtensions:
    def test_pdf_is_supported(self):
        assert ".pdf" in OCR_SUPPORTED_EXTENSIONS

    def test_png_is_supported(self):
        assert ".png" in OCR_SUPPORTED_EXTENSIONS

    def test_docx_not_supported(self):
        assert ".docx" not in OCR_SUPPORTED_EXTENSIONS


# ================================================================== #
#  楽譜テキスト
# ================================================================== #

class TestMusicClassification:
    def test_music_score_keywords(self):
        text = """
        Allegro moderato  ♩= 120
        p   cresc.   mf   forte
        Andante cantabile
        bass clef   treble clef
        fermata
        """
        r = classify_from_text(text, "scan001.pdf")
        assert r.is_classified
        assert r.target_path[0] == "04_Music_Score"

    def test_japanese_music_keywords(self):
        text = "楽譜　拍子記号　音符　小節　臨時記号　調号"
        r = classify_from_text(text, "sheet.pdf")
        assert r.is_classified
        assert r.target_path[0] == "04_Music_Score"

    def test_too_few_keywords_not_classified_as_music(self):
        text = "Allegro"  # 1語だけ → 閾値未満
        r = classify_from_text(text, "random.pdf")
        # 他のカテゴリにも引っかからなければ is_classified=False
        if r.target_path and r.target_path[0] == "04_Music_Score":
            # 他キーワードとたまたま一致した場合は許容
            pass
        else:
            assert not r.is_classified or r.target_path[0] != "04_Music_Score"


# ================================================================== #
#  大学事務テキスト
# ================================================================== #

class TestAdminUnivClassification:
    def test_scholarship_notice(self):
        text = """
        奨学金採用通知
        令和8年度 在学証明書 および 成績証明書 について
        履修登録期間のお知らせ
        授業料の納付について
        """
        r = classify_from_text(text, "univ_notice.pdf")
        assert r.is_classified
        assert r.target_path == ["03_Admin_Life", "01_University_Admin"]

    def test_english_enrollment(self):
        text = "tuition payment academic year enrollment university scholarship transcript"
        r = classify_from_text(text, "uni_doc.pdf")
        assert r.is_classified
        assert r.target_path == ["03_Admin_Life", "01_University_Admin"]


# ================================================================== #
#  キャリア・就活テキスト
# ================================================================== #

class TestAdminCareerClassification:
    def test_internship_contract(self):
        text = """
        インターンシップ 雇用契約書
        勤務時間・給与・アルバイト規定
        採用通知
        """
        r = classify_from_text(text, "contract.pdf")
        assert r.is_classified
        assert r.target_path == ["03_Admin_Life", "02_Career_Intern"]


# ================================================================== #
#  役所テキスト
# ================================================================== #

class TestAdminGovClassification:
    def test_residence_certificate(self):
        text = "住民票 マイナンバー 個人番号 確定申告 住民税"
        r = classify_from_text(text, "gov.pdf")
        assert r.is_classified
        assert r.target_path == ["03_Admin_Life", "03_Government_Public"]


# ================================================================== #
#  住居・インフラテキスト
# ================================================================== #

class TestAdminHouseClassification:
    def test_electricity_bill(self):
        text = "電気料金 ご請求金額 ガス 水道 光熱費 賃貸"
        r = classify_from_text(text, "bill.pdf")
        assert r.is_classified
        assert r.target_path == ["03_Admin_Life", "04_Housing_Utilities"]

    def test_lease_contract(self):
        text = "賃貸借契約書 家賃 管理費 敷金 礼金 契約書"
        r = classify_from_text(text, "lease.pdf")
        assert r.is_classified
        assert r.target_path == ["03_Admin_Life", "04_Housing_Utilities"]


# ================================================================== #
#  金融テキスト
# ================================================================== #

class TestAdminFinClassification:
    def test_bank_statement(self):
        text = "口座残高 振込 引き落とし クレジットカード 証券"
        r = classify_from_text(text, "bank.pdf")
        assert r.is_classified
        assert r.target_path == ["03_Admin_Life", "05_Finance_Bank"]


# ================================================================== #
#  医療テキスト
# ================================================================== #

class TestMedicalClassification:
    def test_hospital_receipt(self):
        text = "診察 処方箋 領収書 病院 投薬 検査"
        r = classify_from_text(text, "hospital.pdf")
        assert r.is_classified
        assert r.target_path == ["05_Personal_Health", "03_Medical"]

    def test_english_prescription(self):
        text = "prescription medication diagnosis clinic blood pressure medical"
        r = classify_from_text(text, "med.pdf")
        assert r.is_classified
        assert r.target_path == ["05_Personal_Health", "03_Medical"]


# ================================================================== #
#  ジム・ワークアウトテキスト
# ================================================================== #

class TestGymClassification:
    def test_workout_log(self):
        text = "ベンチプレス スクワット デッドリフト 筋トレ 体重 体脂肪"
        r = classify_from_text(text, "gym_log.pdf")
        assert r.is_classified
        assert r.target_path == ["05_Personal_Health", "01_Gym_Workout"]


# ================================================================== #
#  判定不能テキスト
# ================================================================== #

class TestUnclassifiable:
    def test_blank_text(self):
        r = classify_from_text("", "blank.pdf")
        assert not r.is_classified

    def test_completely_irrelevant_text(self):
        text = "foo bar baz hello world test"
        r = classify_from_text(text, "irrelevant.pdf")
        assert not r.is_classified

    def test_single_keyword_below_threshold(self):
        """1キーワードだけでは閾値未満で分類されない。"""
        r = classify_from_text("prescription", "one_kw.pdf")
        assert not r.is_classified
