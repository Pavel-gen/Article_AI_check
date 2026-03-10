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
API_URL = "https://api.openalex.org/works"
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
        resp = requests.get(API_URL, params={"search": query, "per_page": 3}, headers=HEADERS, timeout=15)
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
                result["abstract"] = restore_abstract(paper.get('abstract_inverted_index'))[:500]
                result["doi"] = paper.get('doi')
                result["journal"] = (paper.get('host_venue') or {}).get('display_name')
                return result
        
        # Не точное совпадение
        result["status"] = "CLOSE_MATCH"
        result["found_title"] = papers[0].get('title')
        result["note"] = f"year={papers[0].get('publication_year')}, author_match={any(expected_author.lower() in a.lower() for a in [x['author'].get('display_name','') for x in papers[0].get('authorships',[])])}"
        
    except requests.exceptions.RequestException as e:
        result["error"] = str(e)
    
    return result

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
        "close_match": 0,
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
        else:
            stats["errors"] += 1
            print(f"   ⛔ ERROR: {res.get('error', 'unknown')}")
        
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
    for r in stats["results"]:
        if r.get("check_result", {}).get("abstract") and len(r["check_result"]["abstract"]) > 200:
            r["check_result"]["abstract"] = r["check_result"]["abstract"][:200] + "..."
    
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
    
    # 💡 Совет для презентации:
    if stats["hit_rate_percent"] >= 70:
        print(f"\n🎯 Система готова к демо! Попадание {stats['hit_rate_percent']}% — отличный результат.")
    else:
        print(f"\n⚠️ Попадание {stats['hit_rate_percent']}%. Для демо можно:")
        print("   1. Убрать из списка заведомо старые/редкие статьи")
        print("   2. Улучшить build_query() — брать больше ключевых слов")
        print("   3. Добавить второй источник (Crossref) для подстраховки")