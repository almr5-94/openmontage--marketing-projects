import pytest

from lib.arabic_captions import (
    assert_caption_safe,
    chunks_from_words,
    normalize_ar,
    to_latin_digits,
    wer,
)


def test_to_latin_digits_maps_both_digit_sets():
    assert to_latin_digits("المادة ١٢ و ۳٤") == "المادة 12 و 34"


def test_normalize_folds_alef_ta_marbuta_and_tashkeel():
    assert normalize_ar("إنَّ المادّة") == normalize_ar("ان الماده")


def test_wer_zero_for_identical_and_one_for_all_wrong():
    ref = normalize_ar("هذا نص عربي")
    assert wer(ref, ref) == 0.0
    assert wer(ref, normalize_ar("كلمات مختلفة تماما")) == 1.0


def test_caption_guard_rejects_arabic_indic_digits():
    # the digit rule: a single Arabic-Indic digit must fail the gate
    with pytest.raises(ValueError, match="non-Latin digit"):
        assert_caption_safe("المادة ٣")
    assert_caption_safe("المادة 3")  # Latin digit passes


def test_caption_guard_rejects_long_chunks():
    with pytest.raises(ValueError, match="words"):
        assert_caption_safe("كلمة كلمة كلمة كلمة كلمة")
    with pytest.raises(ValueError, match="chars"):
        assert_caption_safe("كلمةطويلةجداجداجداجداجداجداجدا")


def test_chunks_follow_word_timestamps_and_flag_headlines():
    words = [("مربع", 0.0, 0.3), ("اسود", 0.3, 0.6), ("فوق", 0.7, 0.9), ("الاسم", 0.9, 1.4)]
    chunks = chunks_from_words(["*مربع أسود", "فوق الاسم"], words, offset=10.0)
    assert chunks == [["مربع أسود", 10.0, 10.6, True], ["فوق الاسم", 10.7, 11.4, False]]
