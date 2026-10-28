import re
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]


def brl(cents):
    s = f"{abs(cents) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if cents < 0 else ''}R$ {s}"


def dec(cents):
    """Centavos -> texto para campos de formulário ('' quando zero)."""
    return f"{cents / 100:.2f}".replace(".", ",") if cents else ""


def month_bounds(ym):
    """'YYYY-MM' (ou None) -> (início do mês, início do próximo, início do anterior)."""
    try:
        year, month = (int(p) for p in ym.split("-"))
        start = date(year, month, 1)
    except (AttributeError, ValueError):
        today = date.today()
        start = date(today.year, today.month, 1)
    nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    prev = date(start.year - (start.month == 1), (start.month - 2) % 12 + 1, 1)
    return start, nxt, prev


def parse_amount(raw, allow_zero=False):
    """'1.234,56', '1.234' (= 1234), '49.90' -> centavos. Levanta InvalidOperation se inválido."""
    raw = raw.strip().replace("R$", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        raw = raw.replace(".", "")
    value = Decimal(raw)
    if (not value.is_finite() or value < 0 or (value == 0 and not allow_zero)
            or value > Decimal("999999999")):
        raise InvalidOperation
    return int((value * 100).to_integral_value())
