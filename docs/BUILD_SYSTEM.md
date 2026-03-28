# THREAT-AI TypeScript Build System

## Overview

The frontend has been modernized with a production-ready build pipeline using:
- **TypeScript 5.3** - Type-safe JavaScript
- **Esbuild** - Fast bundler and minifier
- **ESLint** & **Prettier** - Code quality and formatting
- **Vitest** - Unit testing framework

## Architecture

### Modular Structure

```
src/js/
├── main.ts              # Application entry point
└── modules/
    ├── theme.ts         # Theme management (dark/light mode)
    ├── api.ts           # API client and HTTP utilities
    ├── ui.ts            # UI helpers and DOM utilities
    └── chat.ts          # Chat logic and message handling
```

Each module is a standalone class that handles specific functionality:

- **ThemeManager**: Handles dark/light theme switching with localStorage persistence
- **APIClient**: Wraps all backend API calls with error handling
- **UIManager**: DOM manipulation, notifications, toast messages
- **ChatManager**: Conversation management, message sending, exports

## Development Workflow

### Installation

```bash
npm install
```

### Build Commands

```bash
# Development build (with source maps)
npm run dev

# Production build (minified, optimized)
npm run build

# Watch mode (auto-rebuild on file changes)
npm run watch

# Lint code
npm run lint

# Format code
npm run format

# Run tests
npm run test
```

### Local Development

```bash
# Terminal 1: Start development server with watch
npm run dev

# Terminal 2: Start Flask backend
python app.py
```

## Module API Reference

### ThemeManager

```typescript
const themeManager = window.themeManager;

// Initialize theme on app startup
themeManager.init();

// Toggle between light and dark theme
themeManager.toggle();

// Get current theme
const theme = themeManager.getTheme(); // 'light' | 'dark'
```

### APIClient

```typescript
const api = window.apiClient;

// Load system status
const status = await api.loadStatus();

// Conversation management
const conversations = await api.loadConversations();
const conv = await api.createConversation('My Chat');
await api.deleteConversation(convId);

// Messaging
const response = await api.sendMessage(convId, 'Your message');

// Export functionality
const pdfBlob = await api.exportPDF(result);
const csvBlob = await api.exportCSV(result);
```

### UIManager

```typescript
const ui = window.uiManager;

// Show messages
ui.showError('Error message');
ui.showLoading();
ui.showToast('Success!', 'success');

// DOM updates
ui.updateConversationsList(conversations, activeId);
ui.updateExamplePrompts(samples);

// Utilities
ui.escapeHtml(userInput);
ui.downloadFile(blob, 'filename.pdf');
ui.toggleSidebar();
```

### ChatManager

```typescript
const chat = window.chatManager;

// Conversation management
await chat.createNewChat();
await chat.loadConversation(convId);
await chat.deleteConversation(convId);

// Message handling
await chat.sendMessage();
await chat.loadConversations();

// Utilities
chat.useExample('Example prompt');
chat.copyMessage(messageId);
await chat.exportPDF(messageId);
```

## TypeScript Configuration

See `tsconfig.json` for strict type checking settings:

- Strict mode enabled (`strict: true`)
- Target: ES2020
- Module: ESNext (Esbuild handles module resolution)
- Path aliases:
  - `@/*` → `src/*`
  - `@components/*` → `src/components/*`
  - `@utils/*` → `src/utils/*`
  - `@types/*` → `src/types/*`

## Code Style

### ESLint Rules

- TypeScript strict checks enabled
- No `var` declarations (use `const`/`let`)
- No unused variables (prefix with `_` to ignore)
- Semicolons required
- Max line length: 100 characters

### Prettier Formatting

- 2-space indentation
- Single quotes for strings
- Trailing commas (ES5 compatible)
- Print width: 100 characters

Format all files:
```bash
npm run format
```

## Building for Deployment

### Production Build

```bash
npm run build
```

This creates a minified bundle at `static/dist/app.js` (~13KB minified).

### HTML Integration

The HTML template (`templates/chat.html`) loads the bundled app:

```html
<script src="{{ url_for('static', filename='dist/app.js') }}"></script>
```

### Testing Build Output

```bash
# Build and verify bundle size
npm run build
ls -lh static/dist/app.js
```

## Debugging

### Source Maps

For development debugging:

```bash
# Build with source maps (not minified)
npm run dev
```

Then in browser DevTools, you can see original TypeScript source code.

### Console Logging

The app uses console logging for debugging:

```typescript
console.log('💬', 'User message');
console.error('❌', 'Error message');
console.warn('⚠️', 'Warning');
```

## Troubleshooting

### Build fails with "Cannot find module"

Ensure the module file exists and import path is correct:

```typescript
// ✓ Correct
import { APIClient } from './modules/api';

// ✗ Wrong
import { APIClient } from './api'; // Missing 'modules/' path
```

### Scripts not executing in browser

Check that modules are exposed to window:

```javascript
// In HTML event handler, should work:
createNewChat(); // Calls window.chatManager.createNewChat()
```

### Theme not applying

Ensure `ThemeManager.init()` is called early in app initialization (it is, by default).

## Future Enhancements

- [ ] Add Vitest unit tests
- [ ] Setup GitHub Actions CI/CD
- [ ] Add Storybook for component documentation
- [ ] Database-backed conversation history
- [ ] User authentication
- [ ] Real-time updates with WebSockets

## Files Reference

- **Main**: `src/js/main.ts` - Application entry point
- **Modules**: `src/js/modules/*.ts` - Feature implementations
- **Build**: `scripts/build.mjs` - Esbuild configuration
- **Config**: `tsconfig.json`, `.eslintrc.json`, `.prettierrc`
- **Output**: `static/dist/app.js` - Bundled application (generated)
- **HTML**: `templates/chat.html` - Application template
- **Styles**: `static/css/chat.css` - Application styling

## Version Info

- TypeScript: 5.3.3
- Esbuild: 0.20.0
- ESLint: 8.57.1 (consider upgrading)
- Prettier: 3.1.1
- Node.js: 18+ recommended
