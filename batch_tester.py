#!/usr/bin/env python3
"""
Load Tester for Citation Checker
- Загружает данные из test_data.py
- Проверяет через OpenAlex API
- Считает статистику: время, % попаданий, скорость
- Сохраняет отчёт в results.json
"""

import time
import json
import requests
from datetime import datetime

# Импорт ваших данных
from test_data import citations

# --- Конфигурация ---
API_URL_CROSS_REF = "https://api.crossref.org/works"
API_URL_OPENALEX = "https://api.openalex.org/works"

HEADERS = {"User-Agent": "CitationTester/1.0"}
DELAY_SEC = 1.0  # Пауза между запросами (вежливость к API)

def restore_abstract(inverted_index):
    """Восстановление абстракта из инвертированного индекса"""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    try:
        sorted_words = sorted(inverted_index.items(), key=lambda x: min(x[1]) if isinstance(x[1], list) else x[1])
        return ' '.join([word for word, _ in sorted_words])
    except:
        return ""

def build_query(citation: dict, mode: str = "full") -> str:
    """
    Формирует поисковый запрос.
    
    :param mode: 
        - "full" (по умолчанию) — использует полное название (макс. точность)
        - "keywords" — использует только 4 ключевых слова (резерв)
    """
    title = citation.get('title', '').strip()
    if not title:
        return ""
    
    if mode == "full":
        # === РЕЖИМ 1: ПОЛНОЕ НАЗВАНИЕ (Основной) ===
        # Просто чистим от экстремальных спецсимволов, которые могут сломать URL
        # Оставляем двоеточия, тире и скобки — они помогают поиску!
        clean_title = title.replace('  ', ' ')  # убираем двойные пробелы
        # Можно убрать лишние кавычки, если они мешают
        clean_title = clean_title.replace('"', '').replace("'", "")
        return clean_title.strip()
        
    else:
        # === РЕЖИМ 2: КЛЮЧЕВЫЕ СЛОВА (Резервный, если полный не сработал) ===
        stopwords = {'the', 'and', 'of', 'in', 'a', 'an', 'for', 'on', 'with', 'by', 'at', 'to', 'is', 'are'}
        words = [w.strip('.,:;!?()[]') for w in title.split()]
        # Берем слова подлиннее, не стоп-слова, максимум 5 штук
        keywords = [w for w in words if len(w) > 4 and w.lower() not in stopwords][:5]
        return ' '.join(keywords)

def check_citation(citation: dict) -> dict:
    """
    Проверяет одну цитату. Возвращает результат с метриками.
    """
    query = build_query(citation, mode='full')
    expected_year = citation.get('year')
    expected_author = citation.get('authors', [''])[0].split()[0] if citation.get('authors') else ''
    
    start = time.time()
    result = {
        "query": query,
        "expected_year": expected_year,
        "expected_author": expected_author,
        "status": "ERROR",
        "found_title": None,
        "abstract": None,
        "doi": None,
        "response_time_ms": 0
    }
    
    try:
        resp = requests.get(API_URL_OPENALEX, params={"search": query, "per_page": 3}, headers=HEADERS, timeout=15)
        result["response_time_ms"] = round((time.time() - start) * 1000)
        resp.raise_for_status()
        papers = resp.json().get('results', [])
        
        if not papers:
            result["status"] = "NOT_FOUND"
            return result
        
        # Ищем совпадение по году + автору
        for paper in papers:
            year = paper.get('publication_year')
            authors = [a['author'].get('display_name', '') for a in paper.get('authorships', [])]
            
            # year_match = (year == expected_year)
            year_match = (year and abs(year - expected_year) <= 1)
            author_match = any(expected_author.lower() in a.lower() for a in authors if a)
            
            if year_match and author_match:
                result["status"] = "FOUND"
                result["found_title"] = paper.get('title')


                result["doi"] = paper.get('doi')
                result["journal"] = (paper.get('host_venue') or {}).get('display_name')

                abstract = restore_abstract(paper.get('abstract_inverted_index'))
                
                if not abstract and result["doi"]:
                    print(f" Нет абстракта, работаем по OpenALEX DOI...")
                    abstract_by_doi = fetch_abstract_openalex_doi(result["doi"])
                    if abstract_by_doi:
                        print(f"Абстракт был найден по DOI в OpenAlex:")
                        abstract = abstract_by_doi
                        break
                    
                    print(f" Нет абстракта, работаем по CrossRef DOI...")
                    abstract_by_doi = fetch_anstract_crossref_doi(result["doi"])
                    if abstract_by_doi:
                        print(f"Абстракт был найден в Crossref")
                        abstract = abstract_by_doi




                result["abstract"] = abstract

                return result
        
        # Не точное совпадение
        result = search_crossref(query, expected_year, expected_author)

        # result["found_title"] = papers[0].get('title')
        # result["note"] = f"year={papers[0].get('publication_year')}, author_match={any(expected_author.lower() in a.lower() for a in [x['author'].get('display_name','') for x in papers[0].get('authorships',[])])}"
        
    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
    
    return result


def search_crossref(title, year, author):
    responce = requests.get(API_URL_CROSS_REF, params={ "query.title": title, "rows": 3}, headers=HEADERS, timeout=15)
    items = responce.json().get('message', {}).get('items', [])
    print('ORIGINAL INFO: ')
    print(title, author, year)
    print("*"*85)
    print("Вызов CROSSREF")
    for item in items:
        found_title = item.get('title', [''])[0]
        found_doi = item.get("DOI")

        date_parts = item.get('published-print', {}).get('date-parts', [[0]])
        found_year = date_parts[0][0] if date_parts and date_parts[0] else None

        authors = item.get('author', [])
        found_author = authors[0].get('family', '') if authors else ''

        year_match = (found_year and year and abs(found_year - year) <= 1)
        author_match = (author and found_author and author.lower() in found_author.lower())

        if year_match and author_match:
            print('CROSS_REF_INFO:', found_doi)

            abstract = item.get('abstract')
            if found_doi:
                abstract = fetch_abstract_openalex_doi(found_doi)

            return {
                "status": "FOUND VIA CROSSREF", 
                "found_title": found_title,
                "doi": found_doi,
                "year": found_year,
                "author": found_author,
                "abstract": abstract,
            }
    return {"status": "NOT FOUND"}

def fetch_abstract_openalex_doi(doi):
    
    if not doi:
        return None
    
    try:
        resp = requests.get(
            API_URL_OPENALEX,
            params={"filter": f"doi:{doi}", "per_page": 1},
            headers=HEADERS,
            timeout=10
        )

        data = resp.json()
        results = data.get('results', [])

        if results:
            inverted = results[0].get('abstract_inverted_index')
            if inverted and isinstance(inverted, dict):
                sorted_words = sorted(inverted.items(), key = lambda x: min(x[1]) if isinstance(x[1], list) else x[1])
                return ' '.join([word for word, _ in sorted_words])
    except:
        pass
    
    return None

def fetch_anstract_crossref_doi(doi):

    if not doi:
        return None
    
    try: 
        resp = requests.get(
            API_URL_CROSS_REF + '/{doi}',
            headers=HEADERS,
            timeout=10
        )

        if resp.status_code != 200:
            return None
    
        data = resp.json()
        abstract = data.get('message', {}).get('abstract')

        if abstract:
            return abstract
    except: 
        pass

    return None

def run_test(citations_list: list, max_items: int = None):
    """
    Запускает тестирование списка цитат.
    """
    if max_items:
        citations_list = citations_list[:max_items]
    
    total = len(citations_list)
    stats = {
        "started_at": datetime.now().isoformat(),
        "total_citations": total,
        "found": 0,
        "not_found": 0,
        "cross_found": 0,
        "close_match": 0,
        "abstract_full": 0,
        "errors": 0,
        "results": [],
        "timing": {}
    }
    
    test_start = time.time()
    
    print(f"🔬 Запуск теста: {total} цитат")
    print(f"⏱️  Задержка между запросами: {DELAY_SEC}с\n")
    
    for i, cit in enumerate(citations_list, 1):
        print(f"[{i}/{total}] {cit.get('title', '')[:60]}...")
        
        res = check_citation(cit)
        stats["results"].append({**cit, "check_result": res})
        
        # Обновляем счётчики
        status = res.get('status')
        if status == 'FOUND':
            stats["found"] += 1
            print(f"   ✅ FOUND ({res['response_time_ms']}ms)")
        elif status == 'CLOSE_MATCH':
            stats["close_match"] += 1
            print(f"   ⚠️  CLOSE_MATCH")
        elif status == 'NOT_FOUND':
            stats["not_found"] += 1
            print(f"   ❌ NOT_FOUND")
        elif status == 'FOUND VIA CROSSREF':
            stats["cross_found"] += 1
            print(f"   FOUND VIA CROSSREF")
        else:
            stats["errors"] += 1
            print(f"   ⛔ ERROR: {res.get('error', 'unknown')}")
        
        abstract = res.get('abstract')

        if (abstract and len(abstract) > 0):
            stats["abstract_full"] += 1

        # Пауза (кроме последнего запроса)
        if i < total:
            time.sleep(DELAY_SEC)
    
    # Финальные метрики
    total_time = time.time() - test_start
    stats["timing"] = {
        "total_seconds": round(total_time, 2),
        "avg_per_request_ms": round((total_time / total) * 1000, 1),
        "requests_per_minute": round(60 * total / total_time, 1) if total_time > 0 else 0
    }
    stats["hit_rate_percent"] = round(100 * stats["found"] / total, 1) if total > 0 else 0
    stats["finished_at"] = datetime.now().isoformat()
    
    return stats

def print_summary(stats: dict):
    """Выводит красивую сводку в консоль"""
    t = stats["timing"]
    print("\n" + "🏁"*40)
    print("📊 ИТОГИ ТЕСТА")
    print("🏁"*40)
    print(f"📦 Всего цитат:     {stats['total_citations']}")
    print(f"✅ Найдено точно:   {stats['found']} ({stats['hit_rate_percent']}%)")
    print(f"Найдено через CROSSREF:   {stats['cross_found']}")
    print(f"Найдено abstract:   {stats['abstract_full']}")
    print(f"⚠️  Близкие совпадения: {stats['close_match']}")
    print(f"❌ Не найдено:      {stats['not_found']}")
    print(f"⛔ Ошибки:          {stats['errors']}")

    print(f"\n⏱️  Время выполнения: {t['total_seconds']}с")
    print(f"📈 Скорость:        {t['requests_per_minute']} запросов/мин")
    print(f"⚡ Среднее время:   {t['avg_per_request_ms']}мс/запрос")
    print("🏁"*40)

def save_report(stats: dict, filename: str = "results.json"):
    """Сохраняет отчёт в JSON (без дублирования больших абстрактов)"""
    # Для отчёта можно обрезать абстракты до 200 символов
    # for r in stats["results"]:
    #     if r.get("check_result", {}).get("abstract") and len(r["check_result"]["abstract"]) > 200:
    #         r["check_result"]["abstract"] = r["check_result"]["abstract"][:200] + "..."
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"💾 Отчёт сохранён: {filename}")

# === ЗАПУСК ===
if __name__ == "__main__":
    # 🔧 Настройки теста:
    # -1 = все цитаты, 10 = первые 10 для быстрой проверки
    TEST_LIMIT = -1  # Поставьте 10 для быстрого теста
    
    # Запускаем
    stats = run_test(citations, max_items=None if TEST_LIMIT < 0 else TEST_LIMIT)
    
    # Вывод и сохранение
    print_summary(stats)
    save_report(stats)
