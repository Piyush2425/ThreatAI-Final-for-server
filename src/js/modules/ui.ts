/**
 * UI Manager Module
 * Handles all user interface updates and interactions
 */

export class UIManager {
  /**
   * Show error message
   */
  showError(message: string): void {
    console.error('❌', message);
    const resultsDiv = document.getElementById('results');
    if (resultsDiv) {
      resultsDiv.innerHTML = `
        <div style="padding: 20px; color: var(--error); text-align: center;">
          <strong>Error:</strong> ${this.escapeHtml(message)}
        </div>
      `;
    }
  }

  /**
   * Show loading state
   */
  showLoading(): void {
    const resultsDiv = document.getElementById('results');
    if (resultsDiv) {
      resultsDiv.innerHTML = `
        <div class="loading">
          <div class="spinner"></div>
          <div class="loading-text">Analyzing threat intelligence...</div>
        </div>
      `;
    }
  }

  /**
   * Show success toast
   */
  showToast(message: string, type: 'success' | 'error' | 'info' = 'success'): void {
    const toast = document.createElement('div');
    toast.className = `feedback-toast feedback-toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => document.body.removeChild(toast), 300);
    }, 3000);
  }

  /**
   * Update sidebar conversation list
   */
  updateConversationsList(conversations: any[], activeId: string | null): void {
    const listContainer = document.getElementById('conversations-list');
    if (!listContainer) return;

    if (conversations.length === 0) {
      listContainer.innerHTML = '<div class="empty-conversations">No conversations yet</div>';
      return;
    }

    listContainer.innerHTML = conversations
      .map(
        (conv) => `
      <div class="conversation-item ${conv.id === activeId ? 'active' : ''}" 
           onclick="chatManager.loadConversation('${conv.id}')">
        <span class="conversation-title">${this.escapeHtml(conv.title)}</span>
        <button class="conversation-delete" onclick="event.stopPropagation(); chatManager.deleteConversation('${conv.id}')" title="Delete">
          x
        </button>
      </div>
    `
      )
      .join('');
  }

  /**
   * Update example prompts grid
   */
  updateExamplePrompts(samples: string[]): void {
    const container = document.getElementById('example-prompts');
    if (!container) return;

    container.innerHTML = samples
      .slice(0, 4)
      .map(
        (sample) => `
      <div class="prompt-card" onclick="chatManager.useExample('${this.escapeHtml(sample).replace(/'/g, "\\'")}')">
        <div class="prompt-card-text">${this.escapeHtml(sample)}</div>
      </div>
    `
      )
      .join('');
  }

  /**
   * Escape HTML to prevent XSS
   */
  escapeHtml(text: string): string {
    const map: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;',
    };
    return String(text).replace(/[&<>"']/g, (m) => map[m] || m);
  }

  /**
   * Format assistant text safely with minimal markdown and clickable URLs.
   */
  formatAssistantText(text: string): string {
    const escaped = this.escapeHtml(text || '');
    const withBold = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    const withLinks = withBold.replace(
      /(https?:\/\/[^\s<]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
    );
    return withLinks.replace(/\n/g, '<br>');
  }

  /**
   * Download file helper
   */
  downloadFile(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  }

  /**
   * Toggle sidebar visibility
   */
  toggleSidebar(): void {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
      sidebar.classList.toggle('open');
    }
  }

  /**
   * Open settings modal and sync current theme selection.
   */
  openSettings(): void {
    const modal = document.getElementById('settings-modal');
    const selector = document.getElementById('settings-theme-select') as HTMLSelectElement | null;
    const themeManager = (window as any).themeManager;

    if (selector && themeManager?.getTheme) {
      selector.value = themeManager.getTheme();
    }

    if (modal) {
      modal.style.display = 'flex';
    }
  }

  /**
   * Close settings modal.
   */
  closeSettings(): void {
    const modal = document.getElementById('settings-modal');
    if (modal) {
      modal.style.display = 'none';
    }
  }

  /**
   * Save settings and apply selected theme.
   */
  saveSettings(): void {
    const selector = document.getElementById('settings-theme-select') as HTMLSelectElement | null;
    const selectedTheme = selector?.value;
    const themeManager = (window as any).themeManager;

    if ((selectedTheme === 'light' || selectedTheme === 'dark') && themeManager?.setTheme) {
      themeManager.setTheme(selectedTheme);
      this.showToast(`Theme set to ${selectedTheme}`, 'success');
    }

    this.closeSettings();
  }
}
