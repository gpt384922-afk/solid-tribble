from bot.structured_input import parse_manual_input, parse_server_input


def test_parse_server_input_ok() -> None:
    text = """Название: DE-01
Роль: bridge
Провайдер: Hetzner
IPv4: 1.2.3.4
IPv6: -
Домен: de.example.com
SSH порт: 22
SSH пользователь: root
Тип секрета (password/private_key/none): password
Секрет: superpass
Теги (через запятую): EU, 10Gbps
Заметки: test
Дата оплаты (YYYY-MM-DD): 2026-02-01
Дата истечения (YYYY-MM-DD): 2026-03-01
Сумма: 10
Валюта: EUR
Период: 1m"""

    parsed = parse_server_input(text, user_id=1)
    assert parsed.server.name == "DE-01"
    assert parsed.server.ip4 == "1.2.3.4"
    assert parsed.billing.currency == "EUR"


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
