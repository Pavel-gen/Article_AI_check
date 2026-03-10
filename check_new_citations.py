#!/usr/bin/env python3
"""
Citation Checker with Diff View
Показывает ближайший результат даже если точное совпадение не найдено
"""

import requests
import difflib
import time

API_URL = "https://api.openalex.org/works"
HEADERS = {"User-Agent": "CitationChecker/1.0"}

def restore_abstract(inverted_index):
    """Восстанавливает текст abstract из инвертированного индекса"""
    if not inverted_index or not isinstance(inverted_index, dict):
        return "Abstract not available"
    try:
        sorted_words = sorted(inverted_index.items(), key=lambda x: min(x[1]) if isinstance(x[1], list) else x[1])
        return ' '.join([word for word, _ in sorted_words])
    except:
        return "Abstract parsing error"

def calculate_similarity(str1: str, str2: str) -> float:
    """Считает коэффициент похожести строк (0.0 - 1.0)"""
    return difflib.SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

def show_comparison(expected: dict, found: dict):
    """Показывает наглядное сравнение ожидаемого и найденного"""
    print(f"\n🔍 СРАВНЕНИЕ:")
    print(f"{'Поле':<20} | {'Ожидалось':<40} | {'Найдено':<40}")
    print("-" * 85)
    
    # Название
    exp_title = expected.get('query', '')[:37] + "..." if len(expected.get('query', '')) > 40 else expected.get('query', '')
    fnd_title = found.get('title', '')[:37] + "..." if len(found.get('title', '')) > 40 else found.get('title', '')
    title_sim = calculate_similarity(expected.get('query', ''), found.get('title', ''))
    print(f"{'📄 Заголовок':<20} | {exp_title:<40} | {fnd_title:<40}")
    print(f"{'   ↳ Похожесть':<20} | {'':<40} | {title_sim*100:.1f}%")
    
    # Год
    exp_year = str(expected.get('year', 'N/A'))
    fnd_year = str(found.get('publication_year', 'N/A'))
    year_match = "✅" if exp_year == fnd_year else "❌"
    print(f"{'📅 Год':<20} | {exp_year:<40} | {fnd_year:<40} {year_match}")
    
    # Автор
    exp_author = expected.get('author', 'N/A')
    fnd_authors = [a['author'].get('display_name', '') for a in found.get('authorships', [])[:2]]
    fnd_author_str = ', '.join(fnd_authors) if fnd_authors else 'N/A'
    author_match = "✅" if any(exp_author.lower() in a.lower() for a in fnd_authors) else "❌"
    print(f"{'👥 Автор':<20} | {exp_author:<40} | {fnd_author_str[:37]+'...' if len(fnd_author_str)>40 else fnd_author_str:<40} {author_match}")
    
    # Журнал
    fnd_journal = (found.get('host_venue') or {}).get('display_name', 'N/A')
    print(f"{'📚 Журнал':<20} | {'(не указан)':<40} | {fnd_journal[:37]+'...' if len(fnd_journal)>40 else fnd_journal:<40}")

def check_with_diff(query: str, expected_year: int, expected_author: str, show_closest: bool = True):
    """
    Поиск с показом ближайшего результата даже при неудаче.
    """
    print(f"🔍 Запрос: '{query[:80]}{'...' if len(query)>80 else ''}'")
    
    params = {"search": query, "per_page": 3}
    
    try:
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        results = resp.json().get('results', [])
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

    if not results:
        print("❌ API вернул пустой список")
        return False

    # Перебираем результаты
    for i, paper in enumerate(results, 1):
        title = paper.get('title', '')
        year = paper.get('publication_year')
        authors = [a['author'].get('display_name', '') for a in paper.get('authorships', [])]
        
        # Считаем баллы
        score = 0
        if year == expected_year:
            score += 1
        if any(expected_author.lower() in a.lower() for a in authors):
            score += 1
        
        # Если полное совпадение — показываем абстракт и возвращаем успех
        if score >= 2:
            abstract = restore_abstract(paper.get('abstract_inverted_index'))
            doi = paper.get('doi')
            journal = (paper.get('host_venue') or {}).get('display_name', 'N/A')
            
            print(f"\n✅ ✅ ✅ СТАТЬЯ ПОДТВЕРЖДЕНА ✅ ✅ ✅")
            print(f"📄 {title}")
            print(f"👥 {', '.join(authors[:3])}")
            print(f"📅 {year} | 📚 {journal}")
            if doi:
                print(f"🔗 DOI: {doi}")
            print(f"\n📝 Abstract:\n{abstract[:500]}{'...' if len(abstract)>500 else ''}\n")
            return True
        
        # Если это первый результат и включён режим show_closest — показываем сравнение
        if i == 1 and show_closest:
            print(f"\n⚠️ Точное совпадение не найдено. Ближайший результат:")
            show_comparison(
                expected={"query": query, "year": expected_year, "author": expected_author},
                found=paper
            )
            # Показываем абстракт ближайшего для контекста
            abstract = restore_abstract(paper.get('abstract_inverted_index'))
            if abstract and abstract != "Abstract not available":
                print(f"\n📝 Abstract (найденной статьи):\n{abstract[:300]}{'...' if len(abstract)>300 else ''}")

    print(f"\n❌ Ни один из {len(results)} результатов не подошел по критериям")
    return False

# === ЦИТАТЫ ДЛЯ ПРОВЕРКИ ===
CITATIONS = [
    {"description": "#23 Giambarberi (2022)", "author": "Giambarberi", "year": 2022, "query": "Suicide and Epilepsy"},
    {"description": "#24 Löscher (2020)", "author": "Löscher", "year": 2020, "query": "Drug Resistance in Epilepsy: Clinical Impact, Potential Mechanisms, and New Innovative Treatment Options"},
    {"description": "#25 Rogawski (2016)", "author": "Rogawski", "year": 2016, "query": "Mechanisms of Action of Antiseizure Drugs and the Ketogenic Diet"},
    {"description": "#26 Mula (2021)", "author": "Mula", "year": 2021, "query": "Pharmacological treatment of focal epilepsy in adults: an evidence based approach"},
    {"description": "#27 Beghi (2020)", "author": "Beghi", "year": 2020, "query": "The Epidemiology of Epilepsy"},
    {"description": "#28 Chen (2017)", "author": "Chen", "year": 2017, "query": "Psychiatric and behavioral side effects of antiepileptic drugs in adults with epilepsy"},
    {"description": "#29 Löscher & Schmidt (2006)", "author": "Löscher", "year": 2006, "query": "Experimental and Clinical Evidence for Loss of Effect (Tolerance) during Prolonged Treatment with Antiepileptic Drugs"}
]

# === ЗАПУСК ===
if __name__ == "__main__":
    print("🔬 Citation Checker with Diff View\n")
    
    results = []
    for cit in CITATIONS:
        print(f"\n{'='*85}")
        print(f"📋 {cit['description']}")
        print('='*85)
        found = check_with_diff(cit['query'], cit['year'], cit['author'], show_closest=True)
        results.append((cit['description'], found))
        time.sleep(1.5)  # Пауза чтобы не превысить лимиты
    
    # Итоговый отчёт
    print("\n" + "🏁"*40)
    print("📊 ИТОГОВЫЙ ОТЧЁТ")
    print("🏁"*40)
    for desc, found in results:
        status = "✅ НАЙДЕНА" if found else "❌ не найдена"
        print(f"{status:<12} | {desc}")
    
    found_count = sum(1 for _, f in results if f)
    print(f"\n🎯 Всего подтверждено: {found_count}/{len(results)}")