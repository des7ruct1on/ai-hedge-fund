import re
import time
import logging
from typing import List, Dict, Callable, Optional
from urllib.parse import urlparse
from datetime import datetime
import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as dateparse
from dateutil.tz import UTC
import json

# Настройка логирования
logger = logging.getLogger("per_source_financial_parsers")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%Y-%m-%d %H:%M:%S"))
logger.addHandler(ch)

class NewsParser:
    """Класс для парсинга новостей из RSS-лент и HTML-страниц."""
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    FINANCE_KEYWORDS = [
        "эконом", "экономика", "финанс", "финансы", "рынок", "курс", "акция", "акции", "валют", "банк", "инвест",
        "инвестици", "рынок капит", "денег", "бирж", "фондов", "обмен", "ставк", "доход", "прибыл", "убыт", "дивиден",
        "облигац", "кредит", "займ", "ипотек", "страхован", "капитал", "бюджет", "сбережен", "налог", "долг",
        "депозит", "актив", "пассив", "ликвидн", "портфель", "доходн", "оценк", "риск", "баланс", "отчет", "банковск",
        "транзакц", "платеж", "валютн", "курсов", "монетарн", "бухгалтер", "аудит", "финансовый анализ", "денежный поток",
        "эмисс", "рынок облигац", "макроэконом", "микроэконом"
    ]

    
    PARSERS_BY_FEED = {
            "https://rssexport.rbc.ru/rbcnews/news/30/full.rss": "rbc_full",
            "https://www.finam.ru/analysis/conews/rsspoint/": "finam",
            "http://www.cbr.ru/rss/RssNews": "cbrf",
            "https://www.vedomosti.ru/rss/rubric/finance": "vedomosti_finance",
            "https://www.vedomosti.ru/rss/rubric/economics": "vedomosti_economics",
            "https://www.vedomosti.ru/rss/rubric/economics/macro": "vedomosti_economics_macro",
            "https://www.vedomosti.ru/rss/rubric/economics/global": "vedomosti_economics_global",
            "https://www.vedomosti.ru/rss/rubric/economics/taxes": "vedomosti_economics_taxes",
            "https://tass.ru/rss/v2.xml": "tass_v2",
            "http://www.kommersant.ru/RSS/money.xml": "kommersant_money",
            "https://www.kommersant.ru/finance": "kommersant_finance",
        }


    def __init__(self):
        self.company_names = None

    @staticmethod
    def parse_date_safe(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = dateparse.parse(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except Exception:
            return None

    @staticmethod
    def contains_finance_keyword(text: Optional[str]) -> bool:
        if not text:
            return False
        t = text.lower()
        for kw in NewsParser.FINANCE_KEYWORDS:
            if kw in t:
                return True
        return False

    @staticmethod
    def fetch_html(url: str, timeout: int = 12) -> Optional[BeautifulSoup]:
        try:
            r = requests.get(url, headers=NewsParser.HEADERS, timeout=timeout)
            r.raise_for_status()
            return BeautifulSoup(r.content, "html.parser")
        except Exception as e:
            logger.debug("fetch_html failed %s: %s", url, e)
            return None

    @staticmethod
    def entry_is_financial_by_meta(soup: BeautifulSoup) -> bool:
        if not soup:
            return False
        meta_section = soup.find('meta', attrs={"property": "article:section"}) or soup.find('meta', attrs={"name": "section"})
        if meta_section and meta_section.get('content') and NewsParser.contains_finance_keyword(meta_section.get('content')):
            return True
        meta_keywords = soup.find('meta', attrs={"name": "keywords"})
        if meta_keywords and meta_keywords.get('content') and NewsParser.contains_finance_keyword(meta_keywords.get('content')):
            return True
        crumbs = soup.select(".breadcrumb, .breadcrumbs, .b-breadcrumbs, .section, .topic, .rubric")
        for c in crumbs:
            txt = c.get_text(" ", strip=True)
            if NewsParser.contains_finance_keyword(txt):
                return True
        return False

    def generic_feed_parser(self) -> Callable[[feedparser.FeedParserDict, dict], List[dict]]:
        def _parser(d: feedparser.FeedParserDict, params: dict = None) -> List[dict]:
            out = []
            for entry in d.entries:
                title = (entry.get('title') or "").strip()
                summary = (entry.get('summary') or entry.get('description') or "").strip()
                link = entry.get('link') or entry.get('guid')
                pub_raw = entry.get('published') or entry.get('updated') or entry.get('pubDate')
                pub = self.parse_date_safe(pub_raw)

                if self.contains_finance_keyword(title) or self.contains_finance_keyword(summary):
                    out.append({"title": title, "link": link, "published": pub, "summary": summary})
                    continue
                if link and re.search(r'/econom|/finance|/money|/business|/markets|/market|/invest', link, re.IGNORECASE):
                    out.append({"title": title, "link": link, "published": pub, "summary": summary})
                    continue
                if link:
                    soup = self.fetch_html(link)
                    if self.entry_is_financial_by_meta(soup):
                        out.append({"title": title, "link": link, "published": pub, "summary": summary})
            return out
        return _parser

    def parse_tass_v2(self, feed: feedparser.FeedParserDict, params: dict = None) -> List[dict]:
        out = []
        for entry in feed.entries:
            title = (entry.get('title') or "").strip()
            summary = (entry.get('summary') or entry.get('description') or "").strip()
            link = entry.get('link')
            pub = self.parse_date_safe(entry.get('published') or entry.get('updated'))
            cat = entry.get('category') or entry.get('tags')
            if isinstance(cat, list):
                cat_txt = " ".join(str(c) for c in cat)
            else:
                cat_txt = str(cat or "")
            if self.contains_finance_keyword(title) or self.contains_finance_keyword(summary) or self.contains_finance_keyword(cat_txt):
                out.append({"title": title, "link": link, "published": pub, "summary": summary})
                continue
            if link:
                soup = self.fetch_html(link)
                if self.entry_is_financial_by_meta(soup):
                    out.append({"title": title, "link": link, "published": pub, "summary": summary})
        return out

    def get_parser(self, feed_url: str) -> Callable[[feedparser.FeedParserDict, dict], List[dict]]:
        parser_name = self.PARSERS_BY_FEED.get(feed_url, "generic")
        if parser_name == "tass_v2":
            return self.parse_tass_v2
        return self.generic_feed_parser()

    def scrape_feed(self, feed_url: str, company_names: Dict[str, List[str]] = None, start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None) -> List[dict]:
        """Скачивает RSS/HTML и возвращает финансовые записи, отфильтрованные по компаниям и датам."""
        self.company_names = company_names
        parser = self.get_parser(feed_url)
        
        try:
            r = requests.get(feed_url, headers=self.HEADERS, timeout=15)
            r.raise_for_status()
            fp = feedparser.parse(r.content)
        except Exception as e:
            logger.debug("Failed to fetch/parse feed %s: %s", feed_url, e)
            soup = self.fetch_html(feed_url)
            entries = []
            if soup:
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if href.startswith('/'):
                        href = requests.compat.urljoin(feed_url, href)
                    if re.search(r'/20\d{2}/|/news|/article|/econom|/finance|/money', href, re.IGNORECASE):
                        title = a.get_text(strip=True)
                        entries.append({"title": title, "link": href, "published": None, "summary": None})
                return entries
            return []

        parsed = parser(fp, params={"company_names": company_names} if company_names else None)

        if start_dt or end_dt:
            parsed = [e for e in parsed if (not e.get('published') or
                                           (not start_dt or e.get('published') >= start_dt) and
                                           (not end_dt or e.get('published') <= end_dt))]

        if company_names:
            name_to_ticker = {name.upper(): ticker for ticker, names in company_names.items() for name in names}
            final = []
            for e in parsed:
                header = (e.get('title') or "") + " " + (e.get('summary') or "")
                header_up = header.upper()
                matched = False
                for name in name_to_ticker:
                    if re.search(r'\b' + re.escape(name) + r'\b', header_up, re.IGNORECASE):
                        matched = True
                        break
                if not matched and e.get('link'):
                    soup = self.fetch_html(e['link'])
                    if soup and self.contains_finance_keyword(soup.get_text(' ', strip=True)):
                        matched = True
                if matched:
                    final.append(e)
            parsed = final

        return parsed

class NewsTransformer:
    """Класс для преобразования распарсенных новостей в JSON-формат."""
    
    @staticmethod
    def transform_results_to_json(records_by_feed: Dict[str, List[dict]], company_names: Dict[str, List[str]], filter_by_ticker: bool = True, selected_tickers: Optional[List[str]] = None) -> List[dict]:
        transformed = []
        name_to_ticker = {name.upper(): ticker for ticker, names in company_names.items() for name in names}
        
        for feed, items in records_by_feed.items():
            source = urlparse(feed).netloc
            for it in items:
                title = it.get("title") or ""
                summary = it.get("summary") or ""
                text_all = (title + " " + summary).upper()
                
                found_tickers = set()
                for name, ticker in name_to_ticker.items():
                    if re.search(r'\b' + re.escape(name) + r'\b', text_all, re.IGNORECASE):
                        found_tickers.add(ticker)

                ticket = ",".join(sorted(found_tickers)) if found_tickers else ""
                # Пропускаем запись, если фильтрация по тикерам включена и нет совпадений с selected_tickers
                if filter_by_ticker and selected_tickers:
                    if not ticket or not any(t in ticket.split(",") for t in selected_tickers):
                        continue
                elif filter_by_ticker and not ticket:
                    continue

                record = {
                    "ticket": ticket,
                    "news": title,
                    "text": summary,
                    "link": it.get("link") or "",
                    "source": source,
                    "published": it.get("published").isoformat() if it.get("published") else ""
                }
                transformed.append(record)
                if ticket:
                    logger.debug("Found tickers %s in news: %s", ticket, title[:50])
                else:
                    logger.debug("No tickers found in news: %s", title[:50])
        
        return transformed

class NewsSaver:
    """Класс для сохранения новостей в JSON-файл."""
    
    @staticmethod
    def save_news_to_file(data: List[dict], filename: str = "news_by_ticker.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Сохранено {len(data)} записей в {filename}")

class FinancialNewsScraper:
    """Основной класс для координации парсинга, обработки и сохранения финансовых новостей."""
    
    COMPANY_NAMES = {
        "SBER": ["Сбербанк", "Сбербанк России", "Сбер", "Sberbank", "Sber"],
        "GAZP": ["Газпром", "Газпром ПАО", "Gazprom"],
        "ROSN": ["Роснефть", "ПАО НК Роснефть", "Rosneft", "ROSN"],
        "NVTK": ["Новатэк", "ПАО Новатэк", "NOVATEK", "Novatek"],
        "GMKN": ["Норильский никель", "ГМК Норильский никель", "Norilsk Nickel", "Nornickel"],
        "LKOH": ["Лукойл", "PJSC LUKOIL", "LUKOIL"],
        "SIBN": ["Газпром нефть", "Газпром-нефть", "Gazprom Neft", "SIBN"],
        "PLZL": ["Полюс", "Полюс Золото", "Polyus", "PLZL"],
        "PHOR": ["ФосАгро", "PhosAgro", "Фосагро"],
        "SNGS": ["Сургутнефтегаз", "Сургут", "Surgutneftegaz", "SNGS"],
        "TATN": ["Татнефть", "Татнефть ПАО", "Tatneft", "TATN"],
        "NLMK": ["НЛМК", "Новолипецкий металлургический комбинат", "NLMK"],
        "CHMF": ["Северсталь", "Severstal", "CHMF"],
        "AKRN": ["Акрон", "Acron", "АКРОН"],
        "RUAL": ["РУСАЛ", "United Company RUSAL", "RUSAL"],
        "VSMO": ["ВСМПО-Ависма", "VSMPO-AVISMA", "VSMPO"],
        "PIKK": ["PIK", "PIKK"],
        "ALRS": ["Алроса", "ALROSA", "АЛРОСА"],
        "MTSS": ["МТС", "Mobile TeleSystems", "MTS", "MTSS"],
        "MGNT": ["Магнит", "Magnit", "MGNT"],
        "TCSG": ["Тинькофф (TCS Group)", "TCS Group", "TCSG"],
        "MAGN": ["ММК", "Магнитогорский металлургический комбинат", "MMK", "MAGN"],
        "HYDR": ["РусГидро", "RusHydro", "HYDR"],
        "IRKT": ["Иркут", "Irkut Corporation", "IRKT"],
        "UNAC": ["ОАК / United Aircraft Corporation", "UAC", "UNAC"],
        "IRAO": ["Интер РАО", "Inter RAO", "IRAO"],
        "VTBR": ["ВТБ", "Банк ВТБ", "VTB Bank", "VTBR"],
        "RTKM": ["Ростелеком", "Rostelecom", "RTKM"],
        "RASP": ["Распадская", "Raspadskaya", "RASP"],
        "MOEX": ["Московская биржа", "MOEX", "Moscow Exchange"],
        "BANE": ["Башнефть / Башнефтегаз (Bashneft)", "Bashneft", "BANE"],
        "SMLT": ["Самолет Группа", "Samolёt Group", "SMLT", "Самолет"],
        "CBOM": ["Кредит Банк Москвы", "Credit Bank of Moscow", "CBOM"],
        "NKNC": ["Нижнекамскнефтехим", "Nizhnekamskneftekhim", "NKNC"],
        "AFKS": ["АФК Система", "AFK Sistema", "Sistema", "AFKS"],
        "SGZH": ["Сегежа", "Segezha Group", "SGZH"],
        "KZOS": ["Казаньоргсинтез", "Kazanorgsintez", "KZOS"],
        "MGTS": ["МГТС", "MGTS (Moscow City Telephone Network)", "MGTS"],
        "FEES": ["ФСК ЕЭС (Federal Grid Company)", "Federal Grid Company", "FEES"],
        "GCHE": ["Черкизово", "Cherkizovo Group", "GCHE"],
        "NMTP": ["Новороссийский морской торговый порт", "Novorossiysk Commercial Sea Port", "NMTP"],
        "APTK": ["Аптечная сеть 36.6 / Pharmacy Chain 36.6", "APTK"],
        "UPRO": ["ЮПРО / Unipro", "Unipro", "UPRO"],
        "FLOT": ["Совкомфлот", "Sovcomflot", "FLOT"],
        "YAKG": ["Якутсктрансгаз / Yakutsk Fuel & Energy Co", "YAKG"],
        "MSNG": ["Мосэнерго", "Mosenergo", "MSNG"],
        "LENT": ["Лента", "Lenta", "LENT"],
        "AFLT": ["Аэрофлот", "Aeroflot", "AFLT"],
        "OGKB": ["ОГК-2 / Second Generating Company", "OGKB"],
        "KMAZ": ["КамАЗ", "KAMAZ", "KMAZ"],
        "TRMK": ["ТМК", "TMK", "TRMK"],
        "RGSS": ["Росгосстрах", "Rosgosstrakh", "RGSS"],
        "LSRG": ["Группа ЛСР", "LSR Group", "LSRG"],
        "MVID": ["M.Video", "M.video", "MVID"],
        "BSPB": ["Банк Санкт-Петербург", "Bank Saint-Petersburg", "BSPB"],
        "RNFT": ["РуссНефть / RussNeft", "RNFT"],
    }

    def __init__(self, feed_urls: List[str]):
        self.feed_urls = feed_urls
        self.parser = NewsParser()
        self.transformer = NewsTransformer()
        self.saver = NewsSaver()

    def scrape(self, start_dt: Optional[datetime] = None, end_dt: Optional[datetime] = None, filter_by_ticker: bool = True, output_file: str = "news_by_ticker.json", selected_tickers: Optional[List[str]] = None) -> List[dict]:
        """Основной метод для парсинга, обработки и сохранения новостей."""
        results = {}
        for url in self.feed_urls:
            try:
                results[url] = self.parser.scrape_feed(url, self.COMPANY_NAMES, start_dt, end_dt)
                time.sleep(0.15)
            except Exception as e:
                logger.exception("Failed scraping %s: %s", url, e)
                results[url] = []

        news_json = self.transformer.transform_results_to_json(results, self.COMPANY_NAMES, filter_by_ticker, selected_tickers)
        self.saver.save_news_to_file(news_json, output_file)
        return news_json

if __name__ == "__main__":
    from datetime import datetime, timedelta
    from dateutil.tz import UTC

    start = datetime.now(tz=UTC) - timedelta(days=7)
    end = datetime.now(tz=UTC)
    feed_urls = list(NewsParser.PARSERS_BY_FEED.keys())
    
    scraper = FinancialNewsScraper(feed_urls)
    news_json = scraper.scrape(
        start_dt=start,
        end_dt=end,
        filter_by_ticker=True,
        selected_tickers=["SBER", "GAZP", "LKOH", "NVTK", "YNDX", "SMLT"]  
    )