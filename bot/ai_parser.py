"""
Voice transcription + smart expense parsing.
Handles Russian/Uzbek number words, multipliers, currencies.
"""
import os
import re
import subprocess
import tempfile
from datetime import date


# ─── ffmpeg helper ────────────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _ogg_to_wav(ogg_path: str, wav_path: str) -> None:
    ffmpeg = _get_ffmpeg()
    result = subprocess.run(
        [ffmpeg, '-y', '-i', ogg_path, '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-300:])


# ─── Transcription ────────────────────────────────────────────────────────────

async def transcribe_voice(ogg_bytes: bytes) -> str:
    """OGG → WAV → Google Speech (ru-RU, then uz-UZ)."""
    import speech_recognition as sr

    with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp:
        tmp.write(ogg_bytes)
        ogg_path = tmp.name
    wav_path = ogg_path.replace('.ogg', '.wav')

    try:
        _ogg_to_wav(ogg_path, wav_path)
        rec = sr.Recognizer()
        rec.energy_threshold = 300
        rec.dynamic_energy_threshold = True

        with sr.AudioFile(wav_path) as src:
            audio = rec.record(src)

        for lang in ('ru-RU', 'uz-UZ', 'ru-RU'):
            try:
                return rec.recognize_google(audio, language=lang).strip()
            except sr.UnknownValueError:
                continue
        raise ValueError('Не удалось распознать речь')
    finally:
        for p in (ogg_path, wav_path):
            try: os.unlink(p)
            except OSError: pass


# ─── Number-word → digit ──────────────────────────────────────────────────────

# Russian number words
_ONES = {
    'ноль': 0, 'нуль': 0,
    'один': 1, 'одна': 1, 'одно': 1,
    'два': 2, 'две': 2,
    'три': 3, 'четыре': 4, 'пять': 5, 'шесть': 6,
    'семь': 7, 'восемь': 8, 'девять': 9, 'десять': 10,
    'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13,
    'четырнадцать': 14, 'пятнадцать': 15, 'шестнадцать': 16,
    'семнадцать': 17, 'восемнадцать': 18, 'девятнадцать': 19,
    'двадцать': 20, 'тридцать': 30, 'сорок': 40,
    'пятьдесят': 50, 'шестьдесят': 60, 'семьдесят': 70,
    'восемьдесят': 80, 'девяносто': 90,
    'сто': 100, 'двести': 200, 'триста': 300, 'четыреста': 400,
    'пятьсот': 500, 'шестьсот': 600, 'семьсот': 700,
    'восемьсот': 800, 'девятьсот': 900,
}

_MULTIPLIERS = {
    'тысяч': 1_000, 'тысячи': 1_000, 'тысяча': 1_000, 'тыс': 1_000,
    'миллион': 1_000_000, 'миллиона': 1_000_000, 'миллионов': 1_000_000, 'млн': 1_000_000,
    'k': 1_000, 'к': 1_000,  # "50к сум"
}

# Uzbek/Latin number words
_UZ_ONES = {
    'bir': 1, 'ikki': 2, 'uch': 3, "to'rt": 4, 'besh': 5,
    'olti': 6, 'yetti': 7, 'sakkiz': 8, 'to\'qqiz': 9, 'o\'n': 10,
    'yigirma': 20, 'o\'ttiz': 30, 'qirq': 40, 'ellik': 50,
    'oltmish': 60, 'yetmish': 70, 'sakson': 80, 'to\'qson': 90,
    'yuz': 100, 'ming': 1_000,
}


def words_to_number(text: str) -> float | None:
    """
    Try to parse a number from word tokens in the text.
    Returns the number as float or None if not found.
    """
    words = re.split(r'[\s\-]+', text.lower())
    total = 0.0
    current = 0.0
    found_any = False

    for w in words:
        w = w.strip('.,!?;:')
        if not w:
            continue
        if w in _ONES:
            current += _ONES[w]
            found_any = True
        elif w in _UZ_ONES:
            current += _UZ_ONES[w]
            found_any = True
        elif w in _MULTIPLIERS:
            if current == 0:
                current = 1  # "тысяч" alone = 1000
            current *= _MULTIPLIERS[w]
            total += current
            current = 0.0
            found_any = True

    if found_any:
        return total + current
    return None


def extract_amount(text: str) -> float:
    """
    Extract numeric amount from text.
    Priority: digit numbers > number words.
    Handles: "50 000", "50,000", "50.5", "50к", "пятьдесят тысяч".
    """
    clean = text.replace(' ', ' ')  # non-breaking space

    # "50к" or "50k" shorthand
    m = re.search(r'(\d+[\.,]?\d*)\s*[кk]\b', clean, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(',', '.')) * 1000

    # Digit + multiplier word: "50 тысяч", "1.5 миллиона"
    mult_pattern = '|'.join(re.escape(k) for k in _MULTIPLIERS)
    m = re.search(rf'(\d[\d\s]*[\.,]?\d*)\s*({mult_pattern})', clean, re.IGNORECASE)
    if m:
        num_str = re.sub(r'\s+', '', m.group(1)).replace(',', '.')
        try:
            return float(num_str) * _MULTIPLIERS[m.group(2).lower()]
        except ValueError:
            pass

    # "50 000" or "50,000" with space/comma thousands separator
    m = re.search(r'(\d{1,3}(?:[\s,]\d{3})+)', clean)
    if m:
        return float(re.sub(r'[\s,]', '', m.group(1)))

    # Plain decimal / integer
    m = re.search(r'(\d+[.,]\d+)', clean)
    if m:
        return float(m.group(1).replace(',', '.'))
    m = re.search(r'(\d+)', clean)
    if m:
        return float(m.group(1))

    # Fallback: number words
    val = words_to_number(clean)
    return val if val else 0.0


# ─── Category detection ───────────────────────────────────────────────────────

CATEGORY_KEYWORDS = {
    'food': [
        'еда', 'ел', 'поел', 'пообедал', 'поужинал', 'позавтракал', 'кушал',
        'кафе', 'ресторан', 'столовая', 'пицца', 'суши', 'бургер', 'шаурма',
        'плов', 'лагман', 'самса', 'нарын', 'манты', 'шашлык', 'лепёшка',
        'продукты', 'супермаркет', 'korzinka', 'корзинка', 'makro', 'макро',
        'магазин', 'рынок', 'bozor', 'базар',
        'завтрак', 'обед', 'ужин', 'перекус', 'snack',
        'кофе', 'чай', 'напиток', 'сок', 'вода', 'cola',
        'фрукты', 'овощи', 'мясо', 'хлеб', 'молоко', 'яйца', 'масло',
        'non', 'go\'sht', 'sabzavot',
    ],
    'transport': [
        'такси', 'taxi', 'яндекс', 'yandex', 'uber', 'убер',
        'метро', 'автобус', 'маршрутка', 'трамвай', 'троллейбус',
        'поезд', 'самолёт', 'авиа', 'билет',
        'бензин', 'топливо', 'заправка', 'паркинг', 'парковка',
        'доехал', 'поехал', 'добрался', 'отвезли',
    ],
    'entertainment': [
        'кино', 'фильм', 'театр', 'концерт', 'клуб', 'боулинг',
        'игра', 'netflix', 'spotify', 'youtube', 'подписка',
        'парк', 'аттракцион', 'экскурсия', 'билет на',
        'развлечение', 'отдых', 'вечеринка',
    ],
    'health': [
        'аптека', 'лекарство', 'таблетки', 'витамины', 'врач', 'доктор',
        'клиника', 'больница', 'анализ', 'процедура', 'укол',
        'массаж', 'спорт', 'фитнес', 'тренажёр', 'зал', 'gym',
    ],
    'shopping': [
        'одежда', 'обувь', 'кроссовки', 'куртка', 'рубашка', 'штаны',
        'платье', 'джинсы', 'футболка', 'носки',
        'купил', 'купила', 'покупка',
        'зарядка', 'наушники', 'гаджет', 'техника', 'электроника',
        'телефон', 'планшет', 'ноутбук', 'компьютер',
        'книга', 'канцелярия', 'сумка', 'рюкзак',
    ],
    'utilities': [
        'интернет', 'свет', 'электричество', 'газ', 'вода',
        'коммунальные', 'квартплата', 'аренда', 'квартира',
        'связь', 'симка', 'баланс', 'пополнил',
        'uztelecom', 'ucell', 'beeline', 'mobiuz', 'humans',
    ],
}


def detect_category(text: str) -> str:
    t = text.lower()
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                scores[cat] += 1
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else 'other'


# ─── Currency detection ───────────────────────────────────────────────────────

CURRENCY_MAP = {
    'UZS': ['сум', 'сума', 'сумов', 'сумм', 'uzs', "so'm", 'сўм', 'тысяч сум',
            'ming so\'m', 'ming sum'],
    'RUB': ['рубл', 'руб', 'rub', '₽', 'рублей', 'рубля'],
    'USD': ['долл', 'доллар', 'usd', '$', 'бакс', 'green', 'бакса', 'долларов'],
}


def detect_currency(text: str) -> str:
    t = text.lower()
    # Check UZS first since "сум" is common in Uzbekistan
    for currency in ('UZS', 'USD', 'RUB'):
        for kw in CURRENCY_MAP[currency]:
            if kw in t:
                return currency
    # Default to UZS (Uzbekistan)
    return 'UZS'


# ─── Description builder ──────────────────────────────────────────────────────

_NOISE_WORDS = {
    'я', 'мне', 'мой', 'моя', 'моё', 'это',
    'потратил', 'потратила', 'потратили',
    'купил', 'купила', 'купили',
    'заплатил', 'заплатила', 'заплатили',
    'оплатил', 'оплатила',
    'потрачено', 'стоило', 'стоит',
    'взял', 'взяла', 'взяли',
    'на', 'за', 'в', 'у', 'по', 'к', 'с', 'и', 'или', 'что',
    'сегодня', 'вчера', 'утром', 'днём', 'вечером',
    'примерно', 'около', 'где-то', 'приблизительно',
    'рублей', 'рубля', 'руб',
    'долларов', 'доллара', 'доллар',
    'сум', 'сумов', 'сума',
    'тысяч', 'тысячи', 'тысяча', 'тыс',
    'миллион', 'миллиона', 'миллионов', 'млн',
}

_NUMBER_RE = re.compile(r'^\d[\d\s.,]*$')


def build_description(text: str, category: str) -> str:
    words = text.split()
    meaningful = []
    for w in words:
        clean = w.lower().strip('.,!?;:-')
        if clean in _NOISE_WORDS:
            continue
        if _NUMBER_RE.match(clean):
            continue
        # skip single letters
        if len(clean) <= 1:
            continue
        meaningful.append(w.strip('.,!?'))

    desc = ' '.join(meaningful[:6]).strip()

    if not desc:
        fallback = {
            'food': 'Еда', 'transport': 'Транспорт',
            'entertainment': 'Развлечения', 'health': 'Здоровье',
            'shopping': 'Покупки', 'utilities': 'Коммунальные', 'other': 'Расход',
        }
        desc = fallback.get(category, 'Расход')

    # Capitalise first letter
    return desc[0].upper() + desc[1:] if desc else desc


# ─── Main parser ──────────────────────────────────────────────────────────────

async def parse_expense(text: str) -> dict:
    amount      = extract_amount(text)
    currency    = detect_currency(text)
    category    = detect_category(text)
    description = build_description(text, category)

    return {
        'amount':       amount,
        'currency':     currency,
        'category':     category,
        'description':  description,
        'expense_date': date.today().isoformat(),
    }
