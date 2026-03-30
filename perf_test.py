import time, app
app.initialize_components()

queries = ['APT28', 'What country is APT28 from?', 'What tools does APT28 use?', 'Give profile of APT28']
print('CURRENT APPROACH TIMING:')
for q in queries:
    start = time.time()
    result = app.process_query(q, use_cache=False)
    elapsed = time.time() - start
    print(f"Query: {q}")
    print(f"Time: {elapsed:.2f}s")
    print(f"Chunks: {len(result.get('evidence', []))}")
    print("---")
