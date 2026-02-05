import pytest


def test_tokenize_basic():
    from app.services.tokenizer import Tokenizer
    tokenizer = Tokenizer()
    result = tokenizer.tokenize("赵州桥是石拱桥")
    assert "赵州桥" in result
    assert "石拱桥" in result


def test_tokenize_with_custom_dict():
    from app.services.tokenizer import Tokenizer, default_user_dict_path

    tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
    result = tokenizer.tokenize("敞肩式石拱桥结构")
    assert "敞肩式" in result
    assert "石拱桥" in result


def test_to_tsquery():
    from app.services.tokenizer import Tokenizer
    tokenizer = Tokenizer()
    result = tokenizer.to_tsquery("赵州桥的结构特点")
    assert " & " in result
    assert "赵州桥" in result


def test_to_tsvector_text():
    from app.services.tokenizer import Tokenizer
    tokenizer = Tokenizer()
    result = tokenizer.to_tsvector_text("赵州桥是石拱桥")
    assert " " in result
    assert "赵州桥" in result
    assert "是" not in result  # single chars filtered
