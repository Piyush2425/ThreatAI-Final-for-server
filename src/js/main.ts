/**
 * THREAT-AI Main Application Entrypoint
 * Production-ready chat interface with modular architecture
 */

import { ThemeManager } from './modules/theme';
import { ChatManager } from './modules/chat';
import { UIManager } from './modules/ui';
import { APIClient } from './modules/api';

// Extend window interface for TypeScript
declare global {
  interface Window {
    themeManager?: ThemeManager;
    chatManager?: ChatManager;
    uiManager?: UIManager;
    apiClient?: APIClient;
  }
}

/**
 * Application initialization
 */
class ThreatAI {
  private themeManager: ThemeManager;
  private chatManager: ChatManager;
  private uiManager: UIManager;
  private api: APIClient;

  constructor() {
    this.api = new APIClient();
    this.themeManager = new ThemeManager();
    this.uiManager = new UIManager();
    this.chatManager = new ChatManager(this.api, this.uiManager);
  }

  /**
   * Initialize the application
   */
  async init(): Promise<void> {
    try {
      console.log('🚀 Initializing THREAT-AI...');

      // Initialize theme (must be first)
      this.themeManager.init();

      // Load system status
      await this.api.loadStatus();

      // Load conversations
      await this.chatManager.loadConversations();

      // Load example prompts
      await this.chatManager.loadExamplePrompts();

      // Setup input handlers
      this.setupInputHandlers();

      // Create initial chat
      await this.chatManager.createNewChat();

      // Expose managers to window
      this.exposeManagers();

      console.log('✅ THREAT-AI initialized successfully');
    } catch (error) {
      console.error('❌ Initialization failed:', error);
      this.uiManager.showError('Failed to initialize application');
    }
  }

  /**
   * Setup keyboard and input event handlers
   */
  private setupInputHandlers(): void {
    const input = document.getElementById('message-input') as HTMLTextAreaElement;
    if (!input) return;

    // Auto-resize textarea
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = input.scrollHeight + 'px';
    });

    // Enter to send, Shift+Enter for new line
    input.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.chatManager.sendMessage();
      }
    });
  }

  /**
   * Expose managers as window globals for DOM event handlers
   */
  private exposeManagers(): void {
    window.themeManager = this.themeManager;
    window.chatManager = this.chatManager;
    window.uiManager = this.uiManager;
    window.apiClient = this.api;
  }
}

// Initialize application when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    const app = new ThreatAI();
    app.init();
  });
} else {
  const app = new ThreatAI();
  app.init();
}
