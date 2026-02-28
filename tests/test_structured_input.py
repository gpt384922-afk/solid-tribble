import pytest

from bot.structured_input import StructuredInputError, parse_manual_input


def test_parse_manual_input_multiline_ok() -> None:
    text = """Название: RemnaNode
Категория: install
Теги: remna, node
Текст (markdown):
# Заголовок
\n```bash
apt update
```
"""

    parsed = parse_manual_input(text, user_id=1)
    assert parsed.manual.title == "RemnaNode"
    assert "apt update" in parsed.manual.body_markdown


def test_parse_manual_input_invalid_category() -> None:
    text = """Название: RemnaNode
Категория: unknown
Теги: remna
Текст (markdown):
text
"""
    with pytest.raises(StructuredInputError):
        parse_manual_input(text, user_id=1)
