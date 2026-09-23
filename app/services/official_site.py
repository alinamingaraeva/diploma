"""Живой поиск только по официальному сайту Казанского Кремля."""

from __future__ import annotations

import html
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx


OFFICIAL_HOSTS = {"kazan-kremlin.ru", "www.kazan-kremlin.ru"}

MUSEUM_PAGES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("эрмитаж",), "/museums/czentr-ermitazh-kazan", "Центр «Эрмитаж-Казань»"),
    (("естественн", "истори"), "/museums/muzej-estestvennoj-istorii-respubliki-tatarstan", "Музей естественной истории Татарстана"),
    (("пушечн", "двор"), "/museums/muzej-pushechnogo-dvora", "Музей Пушечного двора"),
    (("исламск", "культур"), "/museums/muzej-islamskoj-kultury", "Музей исламской культуры"),
    (("благовещен", "собор"), "/museums/muzej-istorii-blagoveshhenskogo-sobora", "Музей истории Благовещенского собора"),
    (("государственност",), "/museums/muzej-istorii-gosudarstvennosti-tatarskogo-naroda-i-respubliki-tatarstan", "Музей истории государственности татарского народа и Республики Татарстан"),
    (("спасск", "башн"), "/museums/muzej-spasskoj-bashni", "Музей Спасской башни"),
    (("манеж",), "/museums/vystavochnyj-zal-manezh", "Выставочный зал «Манеж»"),
    (("присутственн",), "/museums/vystavochnye-zaly-prisutstvennyh-mest", "Выставочные залы Присутственных мест"),
    (("кул-шариф",), "/architectural-objects/mechet-kul-sharif", "Мечеть Кул-Шариф"),
    (("кул шариф",), "/architectural-objects/mechet-kul-sharif", "Мечеть Кул-Шариф"),
)

FRESHNESS_MARKERS = (
    "сегодня",
    "завтра",
    "выходн",
    "сейчас",
    "ближайш",
    "афиш",
    "выставк",
    "мероприят",
    "событи",
    "открыт",
    "закрыт",
    "работает ли",
    "расписан",
    "программ",
)

WEEKLY_LINK_MARKERS = (
    "meropriyatiya-kazanskogo-kremlya",
    "vyhodnye-v-kazanskom-kremle",
)


@dataclass(frozen=True)
class OfficialSource:
    title: str
    url: str
    text: str


class _TextExtractor(HTMLParser):
    _ignored = {"script", "style", "svg", "noscript", "template"}
    _blocks = {"h1", "h2", "h3", "h4", "h5", "p", "li", "br", "tr", "div"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._ignored:
            self._ignore_depth += 1
        elif not self._ignore_depth and tag in self._blocks:
            self.parts.append("\n")
            if tag == "li":
                self.parts.append("• ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored and self._ignore_depth:
            self._ignore_depth -= 1
        elif not self._ignore_depth and tag in self._blocks:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignore_depth:
            self.parts.append(data)


def html_to_text(raw_html: str, max_chars: int = 24_000) -> str:
    parser = _TextExtractor()
    parser.feed(raw_html)
    lines = []
    for raw in "".join(parser.parts).splitlines():
        line = re.sub(r"\s+", " ", html.unescape(raw)).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    text = "\n".join(lines)
    # На страницах Next.js полезное содержимое начинается с заголовка после хлебных крошек.
    weekly_pos = text.find("Мероприятия Казанского Кремля:")
    if weekly_pos >= 0:
        text = text[weekly_pos:]
    else:
        breadcrumb_pos = text.find("Главная/Музеи и выставочные залы кремля")
        if breadcrumb_pos >= 0:
            text = text[breadcrumb_pos:]
    return text[:max_chars]


def _contains_terms(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower().replace("ё", "е")
    return all(term.replace("ё", "е") in lowered for term in terms)


def _section(lines: list[str], start_heading: str, end_headings: tuple[str, ...]) -> list[str]:
    try:
        start = lines.index(start_heading) + 1
    except ValueError:
        return []
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index] in end_headings:
            end = index
            break
    return lines[start:end]


def weekly_museum_excerpt(
    text: str,
    question: str,
    terms: tuple[str, ...],
    museum_name: str,
    today: date | None = None,
) -> str:
    """Оставляет только проверку выставки и программы нужного музея/дат."""
    lines = text.splitlines()
    exhibitions = _section(lines, "Выставки в музеях", ("Выставки на территории Казанского Кремля", "Программы в музеях"))
    exhibition_lines: list[str] = []
    for index, line in enumerate(exhibitions):
        if _contains_terms(line, terms):
            exhibition_lines = exhibitions[index : index + 4]
            break

    programs = _section(lines, "Программы в музеях", ("Экскурсии",))
    program_lines: list[str] = []
    for index, line in enumerate(programs):
        if not _contains_terms(line, terms):
            continue
        for candidate in programs[index + 1 :]:
            if candidate.startswith(("Музей ", "Центр ", "Выставочн")):
                break
            if candidate.startswith("• ") or candidate.startswith("На все программы необходима"):
                program_lines.append(candidate)
                if candidate.startswith("На все программы необходима"):
                    break
        break

    lowered = question.lower().replace("ё", "е")
    if "выходн" in lowered and program_lines:
        today = today or datetime.now(ZoneInfo("Europe/Moscow")).date()
        days_to_saturday = (5 - today.weekday()) % 7
        saturday = today + timedelta(days=days_to_saturday)
        sunday = saturday + timedelta(days=1)
        wanted_days = {str(saturday.day), str(sunday.day)}
        filtered = []
        for line in program_lines:
            if line.startswith("На все программы необходима"):
                filtered.append(line)
                continue
            if any(re.search(rf"(?<!\d){re.escape(day)}(?!\d)", line) for day in wanted_days):
                filtered.append(line)
        program_lines = filtered

    result = [lines[0] if lines else "Свежая недельная афиша"]
    if exhibition_lines:
        result.extend([f"Выставка для {museum_name} указана в разделе «Выставки в музеях»:", *exhibition_lines])
    else:
        result.append(
            f"Проверка раздела «Выставки в музеях»: {museum_name} в списке отсутствует; "
            "отдельная временная выставка на эту неделю официальной афишей не указана."
        )
    if program_lines:
        result.extend([f"Программы для {museum_name} на запрошенные даты:", *program_lines])
    return "\n".join(result)


class OfficialSiteRetriever:
    def __init__(
        self,
        client: httpx.Client,
        base_url: str = "https://kazan-kremlin.ru",
        cache_ttl_seconds: int = 600,
        timeout_seconds: float = 12.0,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self._cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def should_use(self, question: str) -> bool:
        lowered = question.lower().replace("ё", "е")
        named_museum = any(_contains_terms(lowered, terms) for terms, _, _ in MUSEUM_PAGES)
        changing_fact = any(marker in lowered for marker in FRESHNESS_MARKERS)
        return named_museum or ("музе" in lowered and changing_fact)

    def search(self, question: str) -> list[OfficialSource]:
        urls: list[str] = []
        lowered = question.lower().replace("ё", "е")
        changing_fact = any(marker in lowered for marker in FRESHNESS_MARKERS)
        matched_museum = next(
            ((terms, path, name) for terms, path, name in MUSEUM_PAGES if _contains_terms(lowered, terms)),
            None,
        )

        if changing_fact:
            latest = self._latest_weekly_url()
            if latest:
                urls.append(latest)

        if matched_museum:
            urls.append(urljoin(self.base_url + "/", matched_museum[1].lstrip("/")))

        if not urls:
            urls.append(urljoin(self.base_url + "/", "museums"))

        sources: list[OfficialSource] = []
        for url in dict.fromkeys(urls):
            raw = self._get(url)
            text = html_to_text(raw)
            if matched_museum and any(marker in urlparse(url).path for marker in WEEKLY_LINK_MARKERS):
                text = weekly_museum_excerpt(text, question, matched_museum[0], matched_museum[2])
            elif matched_museum and changing_fact:
                # Карточки старых новостей на странице музея не доказывают, что выставка ещё действует.
                text = text.split("\nПубликации\n", 1)[0]
            if len(text) < 40:
                continue
            title = text.splitlines()[0][:160] if text else url
            sources.append(OfficialSource(title=title, url=url, text=text))
        return sources

    def exact_schedule_answer(self, question: str, sources: list[OfficialSource]) -> str | None:
        """Без LLM переносит расписание из свежей афиши, не искажая даты и часы."""
        lowered = question.lower().replace("ё", "е")
        if "выходн" not in lowered or "выставк" not in lowered or not sources:
            return None
        lines = sources[0].text.splitlines()
        check = next((line for line in lines if line.startswith("Проверка раздела «Выставки в музеях»")), None)
        if not check:
            return None
        match = re.search(r": (.+?) в списке отсутствует", check)
        museum_name = match.group(1) if match else "указанного музея"
        programs = [line for line in lines if line.startswith("• ")]
        booking = next((line for line in lines if line.startswith("На все программы необходима")), None)
        answer = (
            f"В свежей официальной афише отдельная временная выставка для площадки «{museum_name}» "
            "на эту неделю не указана [1]."
        )
        if programs:
            answer += "\n\nНа выходные запланированы программы:\n" + "\n".join(programs)
        if booking:
            answer += "\n\n" + booking + " [1]."
        return answer

    def _latest_weekly_url(self) -> str | None:
        raw = self._get(urljoin(self.base_url + "/", "news/"))
        for link in re.findall(r"href=[\"']([^\"']+)", raw, flags=re.IGNORECASE):
            absolute = urljoin(self.base_url + "/", html.unescape(link))
            parsed = urlparse(absolute)
            if parsed.hostname not in OFFICIAL_HOSTS:
                continue
            if any(marker in parsed.path for marker in WEEKLY_LINK_MARKERS):
                return absolute
        return None

    def _get(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
            raise ValueError("Разрешены только HTTPS-страницы официального сайта Казанского Кремля")

        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(url)
            if cached and cached[0] > now:
                return cached[1]

        response = self.client.get(url, follow_redirects=True, timeout=self.timeout_seconds)
        response.raise_for_status()
        final = urlparse(str(response.url))
        if final.scheme != "https" or final.hostname not in OFFICIAL_HOSTS:
            raise ValueError("Официальная страница перенаправила на сторонний сайт")
        text = response.text
        with self._lock:
            self._cache[url] = (now + self.cache_ttl_seconds, text)
        return text
