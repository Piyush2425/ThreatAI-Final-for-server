# Quick Reference Guide

## 🎨 Theme Customization

### Change Primary Colors
Edit `static/css/style.css` lines 14-27:

```css
:root {
    --accent-primary: #00d9ff;    /* Cyan → Change to your color */
    --accent-secondary: #7c3aed;  /* Purple → Change to your color */
}
```

### Available Theme Variables
- **Backgrounds**: `--bg-primary`, `--bg-secondary`, `--bg-tertiary`
- **Text**: `--text-primary`, `--text-secondary`, `--text-muted`
- **Accents**: `--accent-primary`, `--accent-secondary`, `--accent-danger`, `--accent-success`
- **Effects**: `--border-color`, `--shadow-sm`, `--shadow-md`, `--shadow-lg`

---

## 📝 File Locations

| What | Where | What To Edit |
|------|-------|--------------|
| **HTML Structure** | `templates/index.html` | Add/modify DOM elements |
| **Styles** | `static/css/style.css` | Change colors, spacing, fonts |
| **Functionality** | `static/js/app.js` | Add/modify functions |
| **Flask Routes** | `app.py` | Add/modify backend endpoints |

---

## 🔧 Adding New Features

### Add a New Button
1. **HTML** (`templates/index.html`): Add button element
2. **CSS** (`static/css/style.css`): Style it using theme variables
3. **JS** (`static/js/app.js`): Add click handler

Example:
```html
<!-- HTML -->
<button class="btn btn-primary" onclick="myFunction()">Click Me</button>

/* CSS - already styled with .btn .btn-primary */

// JS
function myFunction() {
    console.log("Button clicked!");
}
```

### Add a New API Endpoint
1. **JS** (`static/js/app.js`): Add fetch call
2. **Python** (`app.py`): Add Flask route

Example:
```javascript
// JS: static/js/app.js
async function getMyData() {
    const response = await fetch('/api/mydata');
    return await response.json();
}

# Python: app.py
@app.route('/api/mydata')
def get_my_data():
    return jsonify({'data': 'value'})
```

---

## 🎯 Common Tasks

### Change Button Color
1. Find button in `static/css/style.css`
2. Change color to use a theme variable or custom color
```css
.btn-primary {
    background: linear-gradient(135deg, var(--accent-secondary), var(--accent-primary));
}
```

### Make Text Larger
1. Edit relevant class in `static/css/style.css`
2. Change `font-size` property
```css
.panel-title {
    font-size: 24px;  /* Changed from 20px */
}
```

### Add New Section
1. Add HTML in `templates/index.html`
2. Add CSS styling in `static/css/style.css`
3. Add functionality in `static/js/app.js` if needed

---

## 🚀 Running the App

```bash
# Default: Web UI with auto-open browser
python app.py --web

# Web UI on custom port
python app.py --web --port 8000

# Web UI without auto-opening browser
python app.py --web --no-browser

# CLI mode
python app.py --cli
```

---

## 🐛 Debugging Tips

### Check Console
Press `F12` → Console tab for JavaScript errors

### Check Network
Press `F12` → Network tab to see API calls

### Check Styling
Press `F12` → Elements tab to inspect CSS

### Server Logs
Look at terminal where Flask is running for backend errors

---

## 📦 Project Structure

```
threat-ai/
├── static/                      # Served by Flask
│   ├── css/
│   │   └── style.css           # 721 lines - All CSS
│   └── js/
│       └── app.js              # 300 lines - All JS
├── templates/                   # HTML templates
│   └── index.html              # 157 lines - Main page
├── agent/                       # Threat intelligence logic
├── embeddings/                  # Vector embeddings
├── retrieval/                   # Query retrieval
├── chunking/                    # Text chunking
├── ingestion/                   # Data ingestion
├── evaluation/                  # Quality evaluation
├── feedback/                    # User feedback
├── config/                      # Configuration files
├── data/                        # Data storage
├── app.py                       # Main Flask application
├── requirements.txt             # Python dependencies
└── STRUCTURE.md                 # Detailed documentation
```

---

## 🎨 CSS Sections

`static/css/style.css` is organized into sections:

1. **Reset & Variables** - CSS variables and base styles
2. **Header Section** - Top bar and branding
3. **Status Bar** - Status cards
4. **Main Layout** - Grid layout
5. **Panel Content** - Panel styling
6. **Form Elements** - Inputs and textareas
7. **Buttons** - Button styles
8. **Samples Section** - Sample queries
9. **Results Section** - Results display
10. **Loading State** - Loading spinner
11. **Result Card** - Result formatting
12. **Evidence Section** - Evidence display
13. **Metadata** - Metadata formatting
14. **Error State** - Error styling
15. **Feedback Section** - Feedback form
16. **Responsive Design** - Media queries
17. **Scrollbar Styling** - Custom scrollbars

---

## 📱 Responsive Breakpoints

The app is responsive for:
- **Desktop**: Full layout (1025px and above)
- **Tablet**: Single column (769px - 1024px)
- **Mobile**: Mobile optimized (768px and below)

Edit media queries in `static/css/style.css` around line 700.

---

## 🔐 Security Notes

- ✓ HTML escaping in JS: `escapeHtml()` function prevents XSS
- ✓ Input validation: Check user inputs before processing
- ✓ CORS: Configure as needed for your deployment

---

## 📚 Further Customization

For detailed information, see:
- `STRUCTURE.md` - Full structure documentation
- `ORGANIZATION_COMPLETE.md` - Organization summary
- Flask docs: https://flask.palletsprojects.com/
- CSS docs: https://developer.mozilla.org/en-US/docs/Web/CSS
- JavaScript docs: https://developer.mozilla.org/en-US/docs/Web/JavaScript

---

**Last Updated**: 2026-01-30  
**Version**: 1.0 - Code Reorganized
