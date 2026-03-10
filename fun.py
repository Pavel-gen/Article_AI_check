#!/usr/bin/env python3
"""
Simple Citation Checker — только search, без сложных фильтров.
Проверено на статье #1 (Sun et al., 2008).
"""

import requests

API_URL = "https://api.openalex.org/works"
HEADERS = {"User-Agent": "CitationChecker/1.0"}

def restore_abstract(inverted_index):
    """Восстановление текста из инвертированного индекса"""
    if not inverted_index or not isinstance(inverted_index, dict):
        return "Abstract not available"
    try:
        # Сортируем слова по позиции в исходном тексте
        sorted_words = sorted(inverted_index.items(), key=lambda x: min(x[1]) if isinstance(x[1], list) else x[1])
        return ' '.join([word for word, _ in sorted_words])
    except:
        return "Abstract parsing error"

def check_simple(query: str, expected_year: int, expected_author: str):
    """
    Простой поиск: только search параметр.
    """
    print(f"🔍 Запрос к API: '{query}'")
    
    params = {
        "search": query,
        "per_page": 5  # Берем 5 лучших результатов для выбора
    }
    
    try:
        resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        results = resp.json().get('results', [])
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return

    if not results:
        print("❌ Пустой ответ от API")
        return

    print(f"📚 Найдено статей: {len(results)}\n")

    # Перебираем результаты и ищем подходящий
    for i, paper in enumerate(results, 1):
        title = paper.get('title', '')
        year = paper.get('publication_year')
        
        # Простая проверка: год и фамилия автора
        authors = [a['author'].get('display_name', '') for a in paper.get('authorships', [])]
        author_match = any(expected_author.lower() in a.lower() for a in authors)
        year_match = (year == expected_year)
        
        print(f"--- Вариант #{i} ---")
        print(f"📄 {title}")
        print(f"👥 Авторы: {authors[:3]}")
        print(f"📅 Год: {year} (ожидался: {expected_year})")
        print(f"🎯 Совпадения: Год={'✅' if year_match else '❌'}, Автор={'✅' if author_match else '❌'}")
        
        # Если нашли то, что нужно — показываем абстракт и выходим
        if year_match and author_match:
            abstract = restore_abstract(paper.get('abstract_inverted_index'))
            doi = paper.get('doi')
            
            print(f"\n✅ ✅ ✅ СТАТЬЯ НАЙДЕНА ✅ ✅ ✅")
            print(f"\n📝 Abstract:\n{abstract}\n")
            if doi:
                print(f"🔗 DOI: {doi}")
            return  # Успех, выходим
            
        print()  # Пустая строка между вариантами

    print("⚠️ Ни один из результатов не подошел по критериям (год/автор)")

# === ЗАПУСК ===
if __name__ == "__main__":
    print("🔬 Simple Citation Checker\n")
    
    # Статья #1: Sun et al. (2008)
    # Используем короткий запрос, который сработал в отладке!
    check_simple(
        query="Peroxisome proliferator‐activated receptor gamma agonist, rosiglitazone, suppresses CD40 expression and attenuates inflammatory responses after lithium pilocarpine‐induced status epilepticus in rats",  # 3 ключевых слова
        expected_year=2008,
        expected_author="Hong Sun"
    )

    print("\n" + "="*50)
    print(">>> ПРОВЕРКА СТАТЬИ #2")
    check_simple(
        query="pioglitazone neuroprotection ischaemia",
        expected_year=2005,
        expected_author="Zhao"
    )
    
    # Статья #3: Racine (1972)
    print("\n" + "="*50)
    print(">>> ПРОВЕРКА СТАТЬИ #3")
    check_simple(
        query="seizure electrical stimulation Racine",
        expected_year=1972,
        expected_author="Racine"
    )