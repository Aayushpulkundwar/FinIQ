def _levenshtein(a, b):
    if abs(len(a) - len(b)) > 2: return 99
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        ndp = [i + 1] + [0] * len(b)
        for j, cb in enumerate(b):
            ndp[j + 1] = min(dp[j + 1] + 1, ndp[j] + 1, dp[j] + (0 if ca == cb else 1))
        dp = ndp
    return dp[-1]

def _stem(w):
    for suffix in ('ings', 'ing', 'ment', 'ments', 'tion', 'ed', 's'):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    return w

_NEWS_ROOTS = {'news', 'newz', 'headline', 'headlin', 'update', 'updat', 'develop', 'happen', 'event', 'announc', 'report', 'latest', 'recent', 'current', 'today', 'break', 'press', 'release', 'buzz', 'catch'}
_NEWS_PHRASES = ['catch me up', 'what is happening', 'whats happening', "what's happening", 'press release', 'market update']

def _is_news_intent(query):
    q = query.lower().strip()
    for phrase in _NEWS_PHRASES:
        if phrase in q: return True
    punct = '?!.,;:'
    for token in q.split():
        token_clean = token.strip(punct).lower()
        stemmed = _stem(token_clean)
        for root in _NEWS_ROOTS:
            if stemmed == root or token_clean == root: return True
            if len(token_clean) >= 4 and _levenshtein(token_clean, root) <= 1: return True
    return False

tests = [
    # Typo cases - Before: FAIL, After: PASS
    ('give me the most recent newz on bharti airtel', True),
    ('recen news on arvind', True),
    ('lates updates on bhartiartl', True),
    ('any nws today on this company', True),
    ('headlins for airtel', True),
    # Clean news intent - should pass
    ('give me the most recent news on X', True),
    ('what is happening with arvind', True),
    ("what's happening with arvind", True),
    ('catch me up on bharti airtel', True),
    ('latest updates on X', True),
    ('any news on X today', True),
    ('X news', True),
    ('recent developments for X', True),
    ('breaking news on airtel', True),
    # NON-news queries - must NOT trigger
    ('what is the revenue of bharti airtel', False),
    ('give me the balance sheet for fy25', False),
    ('what is the DCF valuation', False),
    ('calculate wacc for arvind', False),
    ('financial statements for airtel', False),
]

print('=== CLASSIFIER TEST RESULTS ===')
passed = 0
for query, expected in tests:
    result = _is_news_intent(query)
    status = 'PASS' if result == expected else 'FAIL'
    if result == expected: passed += 1
    print(f'  [{status}] is_news={result} (expected={expected}): "{query}"')
print(f'\n{passed}/{len(tests)} passed')
