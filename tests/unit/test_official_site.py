import httpx
from datetime import date

from app.services.official_site import OfficialSiteRetriever, OfficialSource, html_to_text, weekly_museum_excerpt


def test_live_search_uses_latest_weekly_page_and_named_museum():
    pages = {
        "https://kazan-kremlin.ru/news/": (
            '<a href="/news/meropriyatiya-kazanskogo-kremlya-21-27-sentyabrya">Свежая афиша</a>'
        ),
        "https://kazan-kremlin.ru/news/meropriyatiya-kazanskogo-kremlya-21-27-sentyabrya": (
            "<h1>Мероприятия Казанского Кремля: 21 – 27 сентября</h1>"
            "<h3>Выставки в музеях</h3><p>Музей Пушечного двора</p>"
            "<h3>Программы в музеях</h3><p>Музей естественной истории Татарстана</p>"
            "<li>Путешествие в затерянные миры — 26, 27 сентября в 15:00</li>"
        ),
        "https://kazan-kremlin.ru/museums/muzej-estestvennoj-istorii-respubliki-tatarstan": (
            "<h1>Музей естественной истории Республики Татарстан</h1>"
            "<p>Официальная страница музея и постоянной экспозиции.</p>"
        ),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=pages[str(request.url)], request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    retriever = OfficialSiteRetriever(client)
    sources = retriever.search("Какая выставка будет в музее естественной истории в эти выходные?")

    assert len(sources) == 2
    assert sources[0].url.endswith("meropriyatiya-kazanskogo-kremlya-21-27-sentyabrya")
    assert "Путешествие в затерянные миры" in sources[0].text
    assert sources[1].url.endswith("muzej-estestvennoj-istorii-respubliki-tatarstan")
    client.close()


def test_should_use_live_for_named_museum_and_changing_facts():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)))
    retriever = OfficialSiteRetriever(client)

    assert retriever.should_use("Сколько стоит билет в Музей естественной истории?")
    assert retriever.should_use("Какие выставки идут сейчас в музеях?")
    assert not retriever.should_use("Как добраться до Казанского Кремля?")
    client.close()


def test_html_to_text_ignores_scripts_and_keeps_lists():
    text = html_to_text(
        "<script>секретный шум</script><h1>Музей естественной истории</h1>"
        "<ul><li>Экскурсия 26 сентября</li></ul>"
    )
    assert "секретный шум" not in text
    assert "Музей естественной истории" in text
    assert "• Экскурсия 26 сентября" in text


def test_weekend_excerpt_excludes_other_dates_and_preserves_both_weekend_days():
    text = "\n".join(
        [
            "Мероприятия Казанского Кремля: 21 – 27 сентября",
            "Выставки в музеях",
            "Музей Пушечного двора",
            "• Потайное оружие",
            "Программы в музеях",
            "Музей естественной истории Татарстана",
            "• Путешествие в затерянные миры – 26, 27 сентября в 15:00",
            "• Палеонтология для всех – 23 сентября в 15:00",
            "• Раскопки – 27 сентября в 12:00",
            "На все программы необходима предварительная запись: +7 843 000-00-00",
            "Музей Пушечного двора",
            "Экскурсии",
        ]
    )
    excerpt = weekly_museum_excerpt(
        text,
        "Что будет в музее естественной истории в эти выходные?",
        ("естественн", "истори"),
        "Музей естественной истории Татарстана",
        today=date(2026, 9, 22),
    )
    assert "26, 27 сентября" in excerpt
    assert "23 сентября" not in excerpt
    assert "отдельная временная выставка" in excerpt


def test_exact_schedule_answer_copies_dates_without_llm():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request)))
    retriever = OfficialSiteRetriever(client)
    source = OfficialSource(
        title="Свежая афиша",
        url="https://kazan-kremlin.ru/news/current",
        text="\n".join(
            [
                "Мероприятия Казанского Кремля",
                "Проверка раздела «Выставки в музеях»: Музей естественной истории Татарстана в списке отсутствует; отдельная временная выставка на эту неделю официальной афишей не указана.",
                "• Путешествие в затерянные миры – 26, 27 сентября в 15:00",
                "• Раскопки – 27 сентября в 12:00",
                "На все программы необходима предварительная запись: +7 843 000-00-00",
            ]
        ),
    )
    answer = retriever.exact_schedule_answer(
        "Какая выставка будет в музее естественной истории в эти выходные?", [source]
    )
    assert answer is not None
    assert "26, 27 сентября в 15:00" in answer
    assert "Раскопки – 27 сентября" in answer
    client.close()
