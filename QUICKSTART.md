# QUICK START GUIDE

## 🚀 3 Steps to Run Threat-AI

### Step 1: Start Ollama Server (Terminal 1)
```bash
ollama serve
```
Expected output: `Listening on 127.0.0.1:11434`

### Step 2: Start Web UI (Terminal 2)
```bash
cd "c:\Users\Admin\OneDrive\Documents\AI for ThreatActix\threat-ai"
python start_ui.py
```

### Step 3: Open Browser
Navigate to: **http://localhost:5000**

---

## 📊 What You'll See

### Web Interface
- Clean, modern design
- Status panel (LLM mode, model, status)
- Query input box
- Sample queries for quick testing
- Live results with evidence
- Confidence scoring
- Source citations

### Sample Queries to Try
```
1. What are common tactics used by APT28?
2. Describe REvil ransomware variants
3. What vulnerabilities does Lazarus Group exploit?
4. How does Emotet propagate?
5. What infrastructure does Turla use?
```

---

## 🎯 Current Configuration

**Model:** `llama3:8b` (4.7GB)
**Host:** `http://localhost:11434`
**Web UI Port:** `5000`
**Vector DB:** Chroma (1,267 chunks)
**Embeddings:** 384-dim vectors

---

## ⚠️ If Ollama Not Running

You'll see: `✗ Error: Cannot connect to Ollama`

**Solution:**
1. Make sure Ollama is installed
2. Run `ollama serve` in a terminal
3. Refresh the web page

---

## 📝 Alternative: CLI Mode

Instead of web UI, use CLI:
```bash
python app.py
> Query: What is Lazarus Group?
> Query: quit
```

---

## 🔍 Troubleshooting

### Issue: Page shows "Loading..." forever
**Fix:** Check if `ollama serve` is running

### Issue: Slow responses
**Fix:** 
- Check CPU usage (model.inference uses CPU)
- Close other applications
- Increase system RAM

### Issue: "No relevant threat intelligence found"
**Fix:** Try simpler queries or different keywords

---

## 📚 Files to Know

- `web_ui.py` - Flask web server
- `start_ui.py` - Startup script
- `app.py` - CLI application
- `config/settings.yaml` - Configuration
- `agent/interpreter.py` - Ollama integration
- `templates/index.html` - Web UI interface

---

## ✅ System Status

```
✓ Data: 503 threat actors indexed
✓ Vector DB: Chroma (8.9MB)
✓ LLM: llama3:8b ready
✓ Web UI: Flask application
✓ Configuration: YAML-based
✓ Ready for testing!
```

---

## 🎓 Next Steps

1. Test web UI with sample queries
2. Try different threat actors
3. Check confidence scores
4. Review evidence citations
5. Integrate with your workflows

---

**Questions?** Check README.md or SYSTEM_SUMMARY.md
