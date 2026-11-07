import calendar
import re
from datetime import date
from decimal import Decimal, InvalidOperation

WALLET_KINDS = {"conta": "Conta bancária", "corretora": "Corretora / investimentos",
                "beneficio": "Benefício (VR/VA)", "dinheiro": "Dinheiro", "outro": "Outro"}

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


def clamp_day(year, month, day):
    """Data com o dia pedido, limitado ao último dia do mês (dia 31 em fevereiro -> 28/29)."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def add_month(d, day):
    """Próxima ocorrência mensal depois de `d`, sempre no dia `day` (sem 'derivar' de 31 para 28)."""
    return clamp_day(d.year + (d.month == 12), d.month % 12 + 1, day)


def pending_dues(next_due, day, today, end_date=None):
    """Vencimentos já ocorridos (<= hoje), o próximo vencimento e se a série terminou (passou de end_date)."""
    dues = []
    while next_due <= today and not (end_date and next_due > end_date):
        dues.append(next_due)
        next_due = add_month(next_due, day)
    return dues, next_due, bool(end_date and next_due > end_date)


def months_until(deadline, today):
    return max((deadline.year - today.year) * 12 + deadline.month - today.month, 1)


def monthly_needed(remaining, deadline, today):
    """Quanto guardar por mês (arredondado para cima) para atingir a meta até o prazo."""
    return -(-remaining // months_until(deadline, today)) if remaining > 0 else 0
