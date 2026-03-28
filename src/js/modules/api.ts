/**
 * API Client Module
 * Handles all HTTP communication with backend
 */

export interface StatusResponse {
  initialized: boolean;
  model: string;
  llm_mode: string;
}

type SampleItem = string | { query?: string };

export class APIClient {
  private baseURL: string = '/api';

  /**
   * Load system status
   */
  async loadStatus(): Promise<StatusResponse> {
    const response = await fetch(`${this.baseURL}/status`);
    const status = await response.json();

    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    if (status.initialized) {
      if (statusDot) statusDot.style.background = 'var(--success)';
      if (statusText) statusText.textContent = 'Online';
    } else {
      if (statusDot) statusDot.style.background = 'var(--error)';
      if (statusText) statusText.textContent = 'Offline';
    }

    return status;
  }

  /**
   * Load example prompts
   */
  async loadSamples(): Promise<string[]> {
    const response = await fetch(`${this.baseURL}/samples`);
    const data = await response.json();
    const rawSamples: SampleItem[] = Array.isArray(data.samples) ? data.samples : [];

    return rawSamples
      .map((sample) => (typeof sample === 'string' ? sample : sample.query || ''))
      .map((sample) => sample.trim())
      .filter((sample) => sample.length > 0);
  }

  /**
   * Load conversations list
   */
  async loadConversations(): Promise<any> {
    const response = await fetch(`${this.baseURL}/conversations`);
    return response.json();
  }

  /**
   * Create new conversation
   */
  async createConversation(title: string = 'New Chat'): Promise<any> {
    const response = await fetch(`${this.baseURL}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    return response.json();
  }

  /**
   * Get conversation by ID
   */
  async getConversation(convId: string): Promise<any> {
    const response = await fetch(`${this.baseURL}/conversations/${convId}`);
    return response.json();
  }

  /**
   * Send message to conversation
   */
  async sendMessage(convId: string, message: string): Promise<any> {
    const response = await fetch(`${this.baseURL}/conversations/${convId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    return response.json();
  }

  /**
   * Delete conversation
   */
  async deleteConversation(convId: string): Promise<void> {
    await fetch(`${this.baseURL}/conversations/${convId}`, {
      method: 'DELETE',
    });
  }

  /**
   * Submit feedback
   */
  async submitFeedback(feedback: Record<string, any>): Promise<void> {
    await fetch(`${this.baseURL}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(feedback),
    });
  }

  /**
   * Export to PDF
   */
  async exportPDF(result: Record<string, any>): Promise<Blob> {
    const response = await fetch(`${this.baseURL}/export/pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result }),
    });
    return response.blob();
  }

  /**
   * Export to CSV
   */
  async exportCSV(result: Record<string, any>): Promise<Blob> {
    const response = await fetch(`${this.baseURL}/export/csv`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ result }),
    });
    return response.blob();
  }
}
