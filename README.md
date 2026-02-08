# Threat-AI: Evidence-Based Threat Intelligence with Local LLM

**Evidence-based threat intelligence analysis system with Ollama LLM, Chroma vector database, and web UI.**

![Status](https://img.shields.io/badge/status-ready-brightgreen) ![Python](https://img.shields.io/badge/python-3.10+-blue) ![Model](https://img.shields.io/badge/model-llama3%3A8b-success)

## 🚀 Quick Start

### 1. Prerequisites
```bash
# Ollama must be running
ollama serve
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Build/Refresh Vector Store
```bash
python rebuild_vectorstore.py
```

### 4. Start Web UI
```bash
python app.py
```

Then open: **http://localhost:5000**

### 5. Interactive CLI (Alternative)
```bash
python app.py
```

## 📊 System Status

```
✅ Data: 503 threat actors → semantic chunks (after rebuild)
✅ Vector DB: Chroma (8.9MB, <100ms search)
✅ LLM: llama3:8b (Ollama, local inference)
✅ Embeddings: 384-dim (sentence-transformers)
✅ Web UI: Flask-based interface
✅ Ready for testing
```

## 🎯 Web UI Features

- **Query Interface**: Ask threat intelligence questions
- **Live Results**: Real-time analysis with evidence
- **Confidence Scoring**: 0-100% reliability metric
- **Evidence Display**: Cited sources with similarity scores
- **Last Known Activity**: Shows last card change/last seen when available
- **Sample Queries**: Pre-populated examples
- **System Status**: LLM mode, model info

## 📁 Project Structure

```
threat-ai/
├── app.py                 # Flask web UI + CLI
├── rebuild_vectorstore.py # Rebuild Chroma index
├── templates/
│   ├── chat.html          # Main chat UI
│   └── index.html         # Legacy UI
├── static/                # Frontend assets
├── config/
│   └── settings.yaml      # Configuration
├── data/
│   ├── raw/               # 503 threat actor profiles
│   ├── canonical/         # Normalized data
│   └── chroma_db/         # Vector database
├── ingestion/             # Data loading
├── chunking/              # Semantic segmentation
├── embeddings/            # Vector generation
├── retrieval/             # Semantic search
├── agent/                 # LLM integration
│   ├── interpreter.py     # Ollama integration ✨
│   └── guardrails.py      # Confidence scoring
├── evaluation/            # Audit trails
├── requirements.txt       # Dependencies
└── README.md
```

## 🔧 Configuration

**File:** `config/settings.yaml`

```yaml
ollama:
  model: llama3:8b          # Using 8B model
  host: http://localhost:11434
  timeout: 120
  temperature: 0.3
  max_tokens: 512
```

## 🧠 Local LLM (Ollama) Setup

1. Install Ollama from https://ollama.ai and start the service:
```bash
ollama serve
```

2. Pull or verify the model you want to use (example):
```bash
ollama pull llama3:8b
```

3. Point Threat-AI to your Ollama host/model in `config/settings.yaml`:
```yaml
ollama:
  model: llama3:8b
  host: http://localhost:11434
  timeout: 120
  temperature: 0.3
  max_tokens: 512
```

If Ollama is not running, Threat-AI falls back to a built-in summary generator.

## 📈 Architecture

```
Query
  ↓
Vector Search (Chroma DB)  [<100ms]
  ↓
Evidence Formatting
  ↓
Ollama LLM (llama3:8b)     [1-5s]
  ↓
Confidence Scoring
  ↓
Response with Evidence
```

## 🧪 Testing

**Test Web UI:**
```bash
python app.py
# Navigate to http://localhost:5000
```

**Test CLI:**
```bash
python app.py
> Query: What are APT28 tactics?
```

**Integration Tests:**
```bash
python test_ollama.py      # Ollama integration
python test_chroma.py      # Vector store
```

## 📊 Performance

- Vector search: <100ms
- Ollama inference: 1-5s (llama3:8b)
- Full response: 5-10s
- Storage: 11.4MB total

## 🔐 Security

✅ Local processing (no cloud)
✅ No API keys
✅ Persistent storage on disk
✅ Audit logging

## 📦 Dependencies

```
chromadb>=0.4.0
sentence-transformers>=2.2.0
ollama>=0.1.0
requests>=2.28.0
flask>=2.0.0
pyyaml>=6.0
pydantic>=2.0.0
```

Install:
```bash
pip install -r requirements.txt
```

## 🎓 Documentation

This README is the primary documentation. Configuration lives in `config/settings.yaml`, and the key entry points are `app.py` (web UI + CLI) and `rebuild_vectorstore.py` (index rebuild).

## ✨ Key Features

- **Web UI**: Beautiful, responsive interface
- **Ollama LLM**: Local inference (llama3:8b)
- **Evidence Grounding**: Every answer cites sources
- **Confidence Scoring**: Reliability (0-100%)
- **Semantic Search**: <100ms vector retrieval
- **Modular Design**: Independent components
- **Error Handling**: Graceful degradation

## 🚀 Usage Examples

### Web UI Query
```
Query: What vulnerabilities does Lazarus Group exploit?

Response:
  Lazarus Group is known for exploiting zero-day vulnerabilities in...
  Last Known Activity: 2025-08-16
  
Confidence: 84.5%

Evidence:
  [1] vulnerabilities (Score: 0.891) - Lazarus targets...
  [2] tactics (Score: 0.821) - Known for sophisticated...
```

### CLI Query
```bash
$ python app.py
> Query: Describe Emotet propagation
  Answer: Emotet is a polymorphic banking trojan that spreads...
  Confidence: 78.3%
  Sources: 3
```

## 📋 Data Pipeline

1. **503 Threat Actors** → Raw JSON
2. **Normalization** → Standardized fields
3. **Chunking** → 1,267 semantic segments
4. **Embedding** → 384-dimensional vectors
5. **Storage** → Chroma DB (persistent)
6. **Retrieval** → Cosine similarity search
7. **LLM** → Evidence-grounded answers

## 🛠️ Troubleshooting

**Ollama not connecting:**
```bash
# Start Ollama
ollama serve

# Check model
ollama list
```

**Slow responses:**
- Check CPU usage
- Reduce `max_tokens` in settings.yaml
- Use `mistral` model instead

**No results from search:**
Lower `similarity_threshold` in settings.yaml:
```yaml
retrieval:
  similarity_threshold: 0.4  # Was 0.6
```

**Missing new data fields (e.g., last known activity):**
Rebuild the vector store after data or code changes:
```bash
python rebuild_vectorstore.py
```

## 📚 Model Information

**llama3:8b** (Current)
- Parameters: 8 billion
- RAM: 4.7GB
- Speed: 1-3s per query
- Quality: Excellent reasoning
- Recommended: Yes ⭐

## 🎯 Next Steps

1. ✅ Web UI built
2. ✅ Ollama integrated
3. ✅ Testing ready
4. ⧖ Deploy to production
5. ⧖ Monitor performance
6. ⧖ Integrate threat feeds

## 📞 Support

- [Ollama Docs](https://ollama.ai/docs)
- [Chroma Docs](https://docs.trychroma.com)
- [Flask Docs](https://flask.palletsprojects.com)

---

**Status:** ✅ Production Ready | **Version:** 1.0.0 | **Date:** 2026-01-30

**Start Now:** `python start_ui.py` → Open http://localhost:5000










threat-ai/
│
├── README.md
├── requirements.txt
├── config/
│   ├── settings.yaml
│   └── logging.yaml
│
├── data/
│   ├── raw/
│   │   └── threat_actor_profiles.json
│   │
│   ├── canonical/
│   │   └── actors.json              # validated / normalized JSON
│   │
│   └── derived/
│       ├── semantic_chunks.jsonl    # text chunks + metadata
│       └── chunk_schema.json
│
├── ingestion/
│   ├── __init__.py
│   ├── load_raw.py                  # load raw JSON
│   ├── validate.py                  # schema validation
│   └── normalize.py                 # optional field normalization
│
├── chunking/
│   ├── __init__.py
│   ├── chunker.py                   # JSON → semantic documents
│   └── rules.py                     # chunking rules (explicit)
│
├── embeddings/
│   ├── __init__.py
│   ├── embedder.py                  # local embeddings
│   └── vector_store.py              # FAISS or equivalent
│
├── retrieval/
│   ├── __init__.py
│   ├── router.py                    # query → retrieval plan
│   └── retrieve.py                  # evidence selection
│
├── agent/
│   ├── __init__.py
│   ├── system_prompt.txt            # evidence-grounded rules
│   ├── interpreter.py               # LLM call (explain only)
│   └── guardrails.py                # confidence, uncertainty checks
│
├── feedback/
│   ├── __init__.py
│   ├── schema.json
│   └── store.py                     # analyst feedback storage
│
├── evaluation/
│   ├── __init__.py
│   ├── confidence.py                # coverage & confidence scores
│   └── audit.py                     # traceability checks
│
├── app.py                           # CLI entrypoint (MVP)
└── .gitignore




Query History (5-10% effort, high value)
Analytics Dashboard (15-20% effort, good insights)
Export to PDF/CSV (10% effort, essential)
Search Suggestions (10% effort, UX improvement)
RBAC/User System (20% effort, security critical)