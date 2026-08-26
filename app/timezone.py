from datetime import datetime
from zoneinfo import ZoneInfo

TIMEZONE_NAME = "America/Sao_Paulo"
TZ = ZoneInfo(TIMEZONE_NAME)


def now_local():
    """Retorna data/hora oficial do portal (Brasília) sem tzinfo para compatibilidade com o banco atual."""
    return datetime.now(TZ).replace(tzinfo=None)


def today_local():
    return now_local().date()


def utc_naive_to_local(value):
    """Converte um datetime antigo salvo como UTC sem tzinfo para horário local sem tzinfo."""
    if value is None:
        return None
    from datetime import timezone
    return value.replace(tzinfo=timezone.utc).astimezone(TZ).replace(tzinfo=None)
