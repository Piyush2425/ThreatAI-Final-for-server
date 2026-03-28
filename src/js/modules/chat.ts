/**
 * Chat Manager Module
 * Handles conversation management and message flow
 */

import { APIClient } from './api';
import { UIManager } from './ui';
import { StreamingHandler } from './streaming';

export class ChatManager {
  private api: APIClient;
  private ui: UIManager;
  private streaming: StreamingHandler;
  private currentConversationId: string | null = null;
  private currentConversationTitle = 'Threat Intelligence Chat';
  isWaitingForResponse: boolean = false;
  messageMetadata: Record<string, any> = {};

  constructor(api: APIClient, ui: UIManager) {
    this.api = api;
    this.ui = ui;
    this.streaming = new StreamingHandler(api, ui, this);
  }

  /**
   * Load conversations and display in sidebar
   */
  async loadConversations(): Promise<void> {
    try {
      const data = await this.api.loadConversations();
      this.ui.updateConversationsList(data.conversations || [], this.currentConversationId);
    } catch (error) {
      console.error('Error loading conversations:', error);
    }
  }

  /**
   * Load and display example prompts
   */
  async loadExamplePrompts(): Promise<void> {
    try {
      const samples = await this.api.loadSamples();
      this.ui.updateExamplePrompts(samples);
    } catch (error) {
      console.error('Error loading examples:', error);
    }
  }

  /**
   * Create new conversation
   */
  async createNewChat(): Promise<void> {
    try {
      const data = await this.api.createConversation();
      this.currentConversationId = data.conversation_id;
      this.currentConversationTitle = 'Threat Intelligence Chat';

      // Show welcome screen
      const welcomeScreen = document.getElementById('welcome-screen');
      const messagesContainer = document.getElementById('messages-container');
      if (welcomeScreen) welcomeScreen.style.display = 'flex';
      if (messagesContainer) messagesContainer.style.display = 'none';

      // Update title
      const titleEl = document.querySelector('.conversation-title h2');
      if (titleEl) titleEl.textContent = this.currentConversationTitle;

      // Reload conversations
      await this.loadConversations();

      // Focus input
      const input = document.getElementById('message-input') as HTMLTextAreaElement;
      if (input) input.focus();
    } catch (error) {
      this.ui.showError('Error creating new chat');
    }
  }

  /**
   * Load existing conversation
   */
  async loadConversation(convId: string): Promise<void> {
    try {
      const conversation = await this.api.getConversation(convId);
      this.currentConversationId = convId;
      this.currentConversationTitle = conversation.title || 'Threat Intelligence Chat';

      // Hide welcome, show messages
      const welcomeScreen = document.getElementById('welcome-screen');
      const messagesContainer = document.getElementById('messages-container');
      if (welcomeScreen) welcomeScreen.style.display = 'none';
      if (messagesContainer) messagesContainer.style.display = 'block';

      // Update title
      const titleEl = document.querySelector('.conversation-title h2');
      if (titleEl) titleEl.textContent = this.currentConversationTitle;

      // Render messages
      if (messagesContainer) {
        messagesContainer.innerHTML = '';
        for (const msg of conversation.messages) {
          if (msg.role === 'user') {
            this.appendUserMessage(msg.content, msg.timestamp);
          } else {
            this.appendAssistantMessage(msg.content, msg.metadata, msg.timestamp);
          }
        }
      }

      // Update conversations list
      await this.loadConversations();

      // Scroll to bottom
      this.scrollToBottom();
    } catch (error) {
      this.ui.showError('Error loading conversation');
    }
  }

  /**
   * Delete conversation
   */
  async deleteConversation(convId: string): Promise<void> {
    if (!confirm('Delete this conversation?')) return;

    try {
      await this.api.deleteConversation(convId);
      if (convId === this.currentConversationId) {
        await this.createNewChat();
      } else {
        await this.loadConversations();
      }
    } catch (error) {
      this.ui.showError('Error deleting conversation');
    }
  }

  /**
   * Use example prompt
   */
  useExample(prompt: string): void {
    const input = document.getElementById('message-input') as HTMLTextAreaElement;
    if (input) {
      input.value = prompt;
      input.focus();
      this.sendMessage();
    }
  }

  /**
   * Send message with streaming (token-by-token progressive reveal)
   */
  async sendMessage(): Promise<void> {
    const input = document.getElementById('message-input') as HTMLTextAreaElement;
    const message = input.value.trim();

    if (!message || this.isWaitingForResponse) return;

    // Use streaming handler for progressive reveal
    await this.streaming.streamMessage(this.currentConversationId!, message);
  }

  /**
   * Get current conversation ID
   */
  getCurrentConversationId(): string | null {
    return this.currentConversationId;
  }

  /**
   * Get current conversation title
   */
  getCurrentTitle(): string {
    return this.currentConversationTitle;
  }

  /**
   * Set current conversation title
   */
  setCurrentTitle(title: string): void {
    this.currentConversationTitle = title;
  }

  /**
   * Set waiting for response flag
   */
  setWaitingForResponse(waiting: boolean): void {
    this.isWaitingForResponse = waiting;
  }

  /**
   * Get the API client for streaming handler
   */
  getApi(): APIClient {
    return this.api;
  }

  /**
   * Get the UI manager for streaming handler
   */
  getUi(): UIManager {
    return this.ui;
  }

  /**
   * Set title from question only on first user prompt in the current chat.
   */
  shouldSetTitleFromQuestion(): boolean {
    return this.currentConversationTitle === 'Threat Intelligence Chat' || this.currentConversationTitle === 'New Chat';
  }

  /**
   * Build a short, readable title from the user's question.
   */
  deriveChatTitle(question: string): string {
    const normalized = question.replace(/\s+/g, ' ').trim();
    if (!normalized) {
      return 'Threat Intelligence Chat';
    }

    const maxLength = 60;
    if (normalized.length <= maxLength) {
      return normalized;
    }

    return `${normalized.slice(0, maxLength).trim()}...`;
  }

  /**
   * Normalize follow-up question wording for cleaner actor display.
   * Helps with legacy metadata that may include alias-heavy actor labels.
   */
  normalizeFollowupQuestion(question: string): string {
    if (!question) return question;

    const patterns: Array<[RegExp, number]> = [
      [/^(What infrastructure does\s+)(.+?)(\s+use\?)$/i, 2],
      [/^(What malware campaigns has\s+)(.+?)(\s+conducted\?)$/i, 2],
      [/^(What vulnerabilities does\s+)(.+?)(\s+typically exploit\?)$/i, 2],
    ];

    for (const [pattern, subjectIndex] of patterns) {
      const match = question.match(pattern);
      if (!match) continue;

      const subject = (match[subjectIndex] || '').trim();
      const firstAlias = subject.split(',')[0]?.trim() || subject;
      return `${match[1]}${firstAlias}${match[3]}`;
    }

    return question;
  }

  /**
   * Append user message to chat
   */
  appendUserMessage(content: string, timestamp: string | null = null): void {
    const container = document.getElementById('messages-container');
    if (!container) return;

    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

    const messageHTML = `
      <div class="message user">
        <div class="message-avatar" aria-label="User">U</div>
        <div class="message-content">
          <div class="message-header">
            <span class="message-role">You</span>
            <span class="message-time">${time}</span>
          </div>
          <div class="message-text">${this.ui.escapeHtml(content)}</div>
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', messageHTML);
    this.scrollToBottom();
  }

  /**
   * Append assistant message to chat
   */
  appendAssistantMessage(content: string, metadata: any = {}, timestamp: string | null = null): void {
    const container = document.getElementById('messages-container');
    if (!container) return;

    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

    const showReportActions = Boolean(metadata?.report_requested);
    const showReportSuggestion = Boolean(metadata?.report_suggestion) && !showReportActions;
    const reportSuggestionText =
      metadata?.report_suggestion_text ||
      'Would you like me to generate a downloadable report from this answer? Reply with: yes generate report.';
    const followupQuestions = (metadata?.followup_questions || []).map((q: string) =>
      this.normalizeFollowupQuestion(q)
    );

    // Keep suggestions continuous in the same assistant message body (ChatGPT-like flow).
    let composedContent = content;
    if (showReportSuggestion) {
      composedContent += `\n\n${reportSuggestionText}`;
    }
    if (followupQuestions.length > 0) {
      composedContent += '\n\nSuggested follow-ups:\n';
      composedContent += followupQuestions.map((q: string, i: number) => `${i + 1}. ${q}`).join('\n');
      composedContent += '\nReply with any question above to continue.';
    }

    // Store metadata
    this.messageMetadata[messageId] = { content: composedContent, metadata };

    let messageHTML = `
      <div class="message assistant">
        <div class="message-avatar" aria-label="Assistant">AI</div>
        <div class="message-content">
          <div class="message-header">
            <span class="message-role">THREAT-AI</span>
            <span class="message-time">${time}</span>
          </div>
          <div class="message-text">${this.ui.formatAssistantText(composedContent)}</div>
    `;

    // Add evidence links if available
    const rawLinks: string[] = (metadata?.evidence || [])
      .flatMap((e: any) => (Array.isArray(e?.links) ? e.links : []))
      .filter((link: any): link is string => typeof link === 'string' && /^https?:\/\//i.test(link));
    const evidenceLinks: string[] = Array.from(new Set(rawLinks));

    if (evidenceLinks.length > 0) {
      messageHTML += `
        <div class="message-evidence">
          <details class="evidence-details">
            <summary class="evidence-summary">
              <span>Resource Links</span>
              <span class="evidence-count">${evidenceLinks.length}</span>
              <span class="evidence-toggle">Show</span>
            </summary>
            <div class="evidence-list">
              ${evidenceLinks
                .slice(0, 8)
                .map(
                  (link: string, i: number) => `
                <div class="evidence-item">
                  <div class="evidence-source">[${i + 1}]</div>
                  <div class="evidence-text">
                    <a href="${this.ui.escapeHtml(link)}" target="_blank" rel="noopener noreferrer">${this.ui.escapeHtml(link)}</a>
                  </div>
                </div>
              `
                )
                .join('')}
            </div>
          </details>
        </div>
      `;
    }

    messageHTML += `
      <div class="message-actions">
        <button class="action-btn feedback-btn" onclick="alert('Feedback coming soon')" title="Provide Feedback">
          Feedback
        </button>
        <button class="action-btn" onclick="chatManager.copyMessage('${messageId}')" title="Copy">
          Copy
        </button>
        ${
          showReportActions
            ? `<button class="action-btn" onclick="chatManager.exportPDF('${messageId}')" title="Export PDF">Export PDF</button>`
            : ''
        }
      </div>
    `;

    messageHTML += `
          </div>
        </div>
      `;

    container.insertAdjacentHTML('beforeend', messageHTML);
    this.scrollToBottom();
  }

  /**
   * Append error message
   */
  appendErrorMessage(error: string): void {
    const container = document.getElementById('messages-container');
    if (!container) return;

    const messageHTML = `
      <div class="message assistant">
        <div class="message-avatar" aria-label="System">!</div>
        <div class="message-content">
          <div class="message-header">
            <span class="message-role">System</span>
            <span class="message-time">${new Date().toLocaleTimeString()}</span>
          </div>
          <div class="message-text" style="color: var(--error);">
            <strong>Error:</strong> ${this.ui.escapeHtml(error)}
          </div>
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', messageHTML);
    this.scrollToBottom();
  }

  /**
   * Append typing indicator
   */
  appendTypingIndicator(): void {
    const container = document.getElementById('messages-container');
    if (!container) return;

    const indicatorHTML = `
      <div class="message assistant typing-message">
        <div class="message-avatar" aria-label="Assistant">AI</div>
        <div class="message-content">
          <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', indicatorHTML);
    this.scrollToBottom();
  }

  /**
   * Remove typing indicator
   */
  removeTypingIndicator(): void {
    const indicator = document.querySelector('.typing-message');
    if (indicator) indicator.remove();
  }

  /**
   * Scroll chat to bottom
   */
  scrollToBottom(): void {
    const container = document.getElementById('chat-container');
    if (container) {
      setTimeout(() => {
        container.scrollTop = container.scrollHeight;
      }, 100);
    }
  }

  /**
   * Copy message to clipboard
   */
  copyMessage(messageId: string): void {
    const data = this.messageMetadata[messageId];
    if (!data) return;

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(data.content);
      this.ui.showToast('✓ Copied to clipboard', 'success');
    }
  }

  /**
   * Export message as PDF
   */
  async exportPDF(messageId: string): Promise<void> {
    const data = this.messageMetadata[messageId];
    if (!data) return;

    try {
      const blob = await this.api.exportPDF({
        query: 'Chat Export',
        answer: data.content,
        evidence: data.metadata.evidence || [],
        confidence: data.metadata.confidence || 0,
        trace_id: data.metadata.trace_id || '',
        source_count: data.metadata.source_count || 0,
        timestamp: new Date().toISOString(),
      });

      this.ui.downloadFile(blob, `threat-ai-report-${Date.now()}.pdf`);
      this.ui.showToast('✓ PDF exported', 'success');
    } catch (error) {
      this.ui.showToast('Failed to export PDF', 'error');
    }
  }

  /**
   * Send report generation confirmation from assistant suggestion.
   */
  requestReportFromSuggestion(): void {
    const input = document.getElementById('message-input') as HTMLTextAreaElement;
    if (!input) return;

    input.value = 'Yes, generate report';
    this.sendMessage();
  }
}
