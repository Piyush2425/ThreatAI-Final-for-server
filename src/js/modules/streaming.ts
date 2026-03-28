/**
 * Response Streaming Handler Module
 * Handles Server-Sent Events (SSE) for token-by-token progressive reveal
 */

export interface StreamChunk {
  type: 'token' | 'complete';
  token?: string;
  delay_ms?: number;
  progress?: number;
  metadata?: Record<string, any>;
  followup_questions?: string[];
  error?: string;
}

export class StreamingHandler {
  private ui: any;
  private chatManager: any;

  constructor(_api: any, ui: any, chatManager: any) {
    this.ui = ui;
    this.chatManager = chatManager;
  }

  /**
   * Stream a message response token-by-token with progressive reveal
   */
  async streamMessage(convId: string, message: string): Promise<void> {
    const input = document.getElementById('message-input') as HTMLTextAreaElement;
    if (!input || this.chatManager.isWaitingForResponse) return;

    // Hide welcome if visible
    const welcomeScreen = document.getElementById('welcome-screen');
    const messagesContainer = document.getElementById('messages-container');
    if (welcomeScreen && welcomeScreen.style.display !== 'none') {
      welcomeScreen.style.display = 'none';
      if (messagesContainer) messagesContainer.style.display = 'block';
    }

    // Clear input
    input.value = '';
    input.style.height = 'auto';

    // Append user message
    this.chatManager.appendUserMessage(message);

    // Set title from first question
    if (this.chatManager.shouldSetTitleFromQuestion()) {
      this.chatManager.setCurrentTitle(this.chatManager.deriveChatTitle(message));
      const titleEl = document.querySelector('.conversation-title h2');
      if (titleEl) titleEl.textContent = this.chatManager.getCurrentTitle();
    }

    // Add typing indicator
    this.chatManager.appendTypingIndicator();

    // Disable send button
    this.chatManager.setWaitingForResponse(true);
    const sendBtn = document.getElementById('send-btn') as HTMLButtonElement;
    if (sendBtn) sendBtn.disabled = true;

    try {
      // Create message container for progressive reveal
      const messagesDiv = document.getElementById('messages-container');
      if (!messagesDiv) return;

      const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
      let messageHTML = `
        <div class="message assistant" id="${messageId}">
          <div class="message-avatar" aria-label="Assistant">AI</div>
          <div class="message-content">
            <div class="message-header">
              <span class="message-role">THREAT-AI</span>
              <span class="message-time">${new Date().toLocaleTimeString()}</span>
            </div>
            <div class="message-text" id="${messageId}-text"></div>
            <div id="${messageId}-actions" style="display: none;"></div>
          </div>
        </div>
      `;

      this.chatManager.removeTypingIndicator();
      messagesDiv.insertAdjacentHTML('beforeend', messageHTML);

      const textContainer = document.getElementById(`${messageId}-text`);
      const actionsContainer = document.getElementById(`${messageId}-actions`);

      if (!textContainer) return;

      // Open SSE stream
      const response = await fetch(`/api/conversations/${convId}/message/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });

      if (!response.ok || !response.body) throw new Error('Stream failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let accumulatedText = '';
      let lastChunkTime = Date.now();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines[lines.length - 1] || ''; // Keep incomplete line in buffer

        for (let i = 0; i < lines.length - 1; i++) {
          const line = (lines[i] || '').trim();
          if (!line.startsWith('data: ')) continue;

          try {
            const chunk: StreamChunk = JSON.parse(line.substring(6));

            if (chunk.type === 'token') {
              // Progressive reveal with configurable delay
              const now = Date.now();
              const timeSinceLastChunk = now - lastChunkTime;
              const delay = Math.max(0, (chunk.delay_ms || 50) - timeSinceLastChunk);

              await new Promise((resolve) => setTimeout(resolve, delay));

              accumulatedText += chunk.token || '';
              textContainer.textContent = accumulatedText;

              // Show progress indicator (optional, can be styled)
              if (chunk.progress) {
                // Update any progress indicator if needed
              }

              lastChunkTime = Date.now();
              this.chatManager.scrollToBottom();
            } else if (chunk.type === 'complete') {
              // Stream complete - show metadata, actions, follow-ups
              if (chunk.metadata) {
                // Store metadata for later use
                this.chatManager.messageMetadata[messageId] = {
                  content: accumulatedText,
                  metadata: chunk.metadata,
                };

                // Show evidence links if available
                const rawLinks: string[] = (chunk.metadata.evidence || [])
                  .flatMap((e: any) => (Array.isArray(e?.links) ? e.links : []))
                  .filter(
                    (link: any): link is string => typeof link === 'string' && /^https?:\/\//i.test(link)
                  );
                const evidenceLinks: string[] = Array.from(new Set(rawLinks));

                if (evidenceLinks.length > 0) {
                  const evidenceHTML = `
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
                  textContainer.insertAdjacentHTML('afterend', evidenceHTML);
                }

                // Keep report prompt and follow-ups continuous in the message body.
                const showReportSuggestion =
                  chunk.metadata.report_suggestion && !chunk.metadata.report_requested;
                const reportSuggestionText =
                  chunk.metadata.report_suggestion_text ||
                  'Would you like me to generate a downloadable report from this answer? Reply with: yes generate report.';
                const normalizedFollowups = (chunk.followup_questions || []).map((q: string) =>
                  this.chatManager.normalizeFollowupQuestion(q)
                );

                let composedText = accumulatedText;
                if (showReportSuggestion) {
                  composedText += `\n\n${reportSuggestionText}`;
                }
                if (normalizedFollowups.length > 0) {
                  composedText += '\n\nSuggested follow-ups:\n';
                  composedText += normalizedFollowups
                    .map((q: string, i: number) => `${i + 1}. ${q}`)
                    .join('\n');
                  composedText += '\nReply with any question above to continue.';
                }

                this.chatManager.messageMetadata[messageId] = {
                  content: composedText,
                  metadata: chunk.metadata,
                };

                // Show action buttons
                const showReportActions = chunk.metadata.report_requested;
                if (actionsContainer) {
                  const actionsHTML = `
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
                  actionsContainer.insertAdjacentHTML('beforeend', actionsHTML);
                  actionsContainer.style.display = 'block';
                }
              }

              // Reload conversations
              textContainer.innerHTML = this.ui.formatAssistantText(
                this.chatManager.messageMetadata[messageId]?.content || accumulatedText
              );
              await this.chatManager.loadConversations();
            }
          } catch (e) {
            console.error('Error parsing chunk:', e);
          }
        }
      }
    } catch (error: any) {
      console.error('Stream error:', error);
      this.chatManager.appendErrorMessage(error.message || 'Stream failed');
    } finally {
      this.chatManager.setWaitingForResponse(false);
      if (sendBtn) sendBtn.disabled = false;
      input.focus();
    }
  }
}
