/**
 * THREAT-AI Chat Interface JavaScript
 * Conversational AI system
 */

// ============================================
// GLOBAL STATE
// ============================================
let currentConversationId = null;
let isWaitingForResponse = false;

// ============================================
// INITIALIZATION
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    loadSystemStatus();
    loadConversations();
    loadExamplePrompts();
    setupInputHandlers();
    createNewChat();
});

/**
 * Load system status
 */
async function loadSystemStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        
        document.getElementById('model-name').textContent = status.model || 'N/A';
        
        const statusDot = document.getElementById('status-dot');
        const statusText = document.getElementById('status-text');
        
        if (status.initialized) {
            statusDot.style.background = 'var(--success)';
            statusText.textContent = 'Online';
        } else {
            statusDot.style.background = 'var(--error)';
            statusText.textContent = 'Offline';
        }
    } catch (error) {
        console.error('Error loading status:', error);
    }
}

/**
 * Load conversations list
 */
async function loadConversations() {
    try {
        const response = await fetch('/api/conversations');
        const data = await response.json();
        
        const listContainer = document.getElementById('conversations-list');
        
        if (data.conversations.length === 0) {
            listContainer.innerHTML = '<div class="empty-conversations">No conversations yet</div>';
            return;
        }
        
        listContainer.innerHTML = data.conversations.map(conv => `
            <div class="conversation-item ${conv.id === currentConversationId ? 'active' : ''}" 
                 onclick="loadConversation('${conv.id}')">
                <span class="conversation-title">${escapeHtml(conv.title)}</span>
                <button class="conversation-delete" onclick="event.stopPropagation(); deleteConversation('${conv.id}')" title="Delete">
                    🗑️
                </button>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading conversations:', error);
    }
}

/**
 * Load example prompts
 */
async function loadExamplePrompts() {
    try {
        const response = await fetch('/api/samples');
        const data = await response.json();
        
        const container = document.getElementById('example-prompts');
        container.innerHTML = data.samples.slice(0, 4).map(sample => `
            <div class="prompt-card" onclick="useExample('${escapeHtml(sample).replace(/'/g, "\\'")}')">
                <div class="prompt-card-text">${escapeHtml(sample)}</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading examples:', error);
    }
}

/**
 * Setup input handlers
 */
function setupInputHandlers() {
    const input = document.getElementById('message-input');
    
    // Auto-resize textarea
    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = input.scrollHeight + 'px';
    });
    
    // Enter to send, Shift+Enter for new line
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// ============================================
// CONVERSATION MANAGEMENT
// ============================================

/**
 * Create new chat
 */
async function createNewChat() {
    try {
        const response = await fetch('/api/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'New Chat' })
        });
        
        const data = await response.json();
        currentConversationId = data.conversation_id;
        
        // Show welcome screen
        document.getElementById('welcome-screen').style.display = 'flex';
        document.getElementById('messages-container').style.display = 'none';
        document.getElementById('messages-container').innerHTML = '';
        
        // Update conversation title
        document.querySelector('.conversation-title h2').textContent = 'Threat Intelligence Chat';
        
        // Reload conversations list
        loadConversations();
        
        // Focus input
        document.getElementById('message-input').focus();
        
    } catch (error) {
        console.error('Error creating conversation:', error);
        alert('Error creating new chat');
    }
}

/**
 * Load existing conversation
 */
async function loadConversation(convId) {
    try {
        const response = await fetch(`/api/conversations/${convId}`);
        const conversation = await response.json();
        
        currentConversationId = convId;
        
        // Hide welcome, show messages
        document.getElementById('welcome-screen').style.display = 'none';
        document.getElementById('messages-container').style.display = 'block';
        
        // Update title
        document.querySelector('.conversation-title h2').textContent = conversation.title;
        
        // Render messages
        const container = document.getElementById('messages-container');
        container.innerHTML = '';
        
        conversation.messages.forEach(msg => {
            if (msg.role === 'user') {
                appendUserMessage(msg.content, msg.timestamp);
            } else {
                appendAssistantMessage(msg.content, msg.metadata, msg.timestamp);
            }
        });
        
        // Update conversations list
        loadConversations();
        
        // Scroll to bottom
        scrollToBottom();
        
    } catch (error) {
        console.error('Error loading conversation:', error);
        alert('Error loading conversation');
    }
}

/**
 * Delete conversation
 */
async function deleteConversation(convId) {
    if (!confirm('Delete this conversation?')) {
        return;
    }
    
    try {
        await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
        
        if (convId === currentConversationId) {
            createNewChat();
        } else {
            loadConversations();
        }
    } catch (error) {
        console.error('Error deleting conversation:', error);
        alert('Error deleting conversation');
    }
}

// ============================================
// MESSAGING
// ============================================

/**
 * Send message
 */
async function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    
    if (!message || isWaitingForResponse) {
        return;
    }
    
    // Hide welcome screen if visible
    if (document.getElementById('welcome-screen').style.display !== 'none') {
        document.getElementById('welcome-screen').style.display = 'none';
        document.getElementById('messages-container').style.display = 'block';
    }
    
    // Clear input
    input.value = '';
    input.style.height = 'auto';
    
    // Append user message
    appendUserMessage(message);
    
    // Show typing indicator
    appendTypingIndicator();
    
    // Disable send button
    isWaitingForResponse = true;
    document.getElementById('send-btn').disabled = true;
    
    try {
        const response = await fetch(`/api/conversations/${currentConversationId}/message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });
        
        const data = await response.json();
        
        // Remove typing indicator
        removeTypingIndicator();
        
        if (response.ok) {
            // Append assistant response
            appendAssistantMessage(data.assistant_message, data.metadata);
            
            // Update conversation title if first message
            document.querySelector('.conversation-title h2').textContent = data.assistant_message.substring(0, 50);
            
            // Reload conversations list
            loadConversations();
        } else {
            appendErrorMessage(data.error || 'Unknown error');
        }
        
    } catch (error) {
        removeTypingIndicator();
        appendErrorMessage(`Connection error: ${error.message}`);
    } finally {
        isWaitingForResponse = false;
        document.getElementById('send-btn').disabled = false;
        input.focus();
    }
}

/**
 * Use example prompt
 */
function useExample(prompt) {
    document.getElementById('message-input').value = prompt;
    document.getElementById('message-input').focus();
    sendMessage();
}

// ============================================
// MESSAGE RENDERING
// ============================================

/**
 * Append user message
 */
function appendUserMessage(content, timestamp = null) {
    const container = document.getElementById('messages-container');
    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    
    const messageHTML = `
        <div class="message user">
            <div class="message-avatar">👤</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-role">You</span>
                    <span class="message-time">${time}</span>
                </div>
                <div class="message-text">${escapeHtml(content)}</div>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', messageHTML);
    scrollToBottom();
}

/**
 * Append assistant message
 */
function appendAssistantMessage(content, metadata = {}, timestamp = null) {
    const container = document.getElementById('messages-container');
    const time = timestamp ? new Date(timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    
    // Generate unique ID for this message
    const messageId = 'msg-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    
    // Store metadata globally for export
    if (!window.messageMetadata) window.messageMetadata = {};
    window.messageMetadata[messageId] = {
        content: content,
        metadata: metadata
    };
    
    let messageHTML = `
        <div class="message assistant">
            <div class="message-avatar">🛡️</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-role">Threat-AI</span>
                    <span class="message-time">${time}</span>
                </div>
                <div class="message-text">${escapeHtml(content)}</div>
    `;
    
    // Add evidence if available
    if (metadata.evidence && metadata.evidence.length > 0) {
        messageHTML += `
            <div class="message-evidence">
                <div class="evidence-header">
                    <span>📚 Evidence Sources</span>
                    <span class="evidence-count">${metadata.evidence.length}</span>
                </div>
                <div class="evidence-list">
                    ${metadata.evidence.slice(0, 3).map((e, i) => `
                        <div class="evidence-item">
                            <div class="evidence-source">[${i+1}] ${escapeHtml(e.actor || 'Unknown')} • ${escapeHtml(e.source)}</div>
                            <div class="evidence-text">${escapeHtml(e.text)}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    // Add export and feedback buttons
    messageHTML += `
                <div class="message-actions">
                    <button class="action-btn feedback-btn" onclick="openFeedbackModal('${messageId}')" title="Provide Feedback">
                        💬 Feedback
                    </button>
                    <button class="action-btn" onclick="exportMessagePDF('${messageId}')" title="Export as PDF">
                        📄 PDF
                    </button>
                    <button class="action-btn" onclick="exportMessageCSV('${messageId}')" title="Export as CSV">
                        📊 CSV
                    </button>
                    <button class="action-btn-icon" onclick="quickFeedback('${messageId}', 'positive')" title="Helpful">
                        👍
                    </button>
                    <button class="action-btn-icon" onclick="quickFeedback('${messageId}', 'negative')" title="Not Helpful">
                        👎
                    </button>
                </div>
    `;
    
    messageHTML += `
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', messageHTML);
    scrollToBottom();
}

/**
 * Append error message
 */
function appendErrorMessage(error) {
    const container = document.getElementById('messages-container');
    
    const messageHTML = `
        <div class="message assistant">
            <div class="message-avatar">⚠️</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-role">System</span>
                    <span class="message-time">${new Date().toLocaleTimeString()}</span>
                </div>
                <div class="message-text" style="color: var(--error);">
                    <strong>Error:</strong> ${escapeHtml(error)}
                </div>
            </div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', messageHTML);
    scrollToBottom();
}

/**
 * Append typing indicator
 */
function appendTypingIndicator() {
    const container = document.getElementById('messages-container');
    
    const indicatorHTML = `
        <div class="message assistant typing-message">
            <div class="message-avatar">🛡️</div>
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
    scrollToBottom();
}

/**
 * Remove typing indicator
 */
function removeTypingIndicator() {
    const indicator = document.querySelector('.typing-message');
    if (indicator) {
        indicator.remove();
    }
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

/**
 * Scroll chat to bottom
 */
function scrollToBottom() {
    const container = document.getElementById('chat-container');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 100);
}

/**
 * Escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Toggle sidebar (mobile)
 */
function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('open');
}

/**
 * Show settings (placeholder)
 */
function showSettings() {
    alert('Settings feature coming soon!');
}

// ============================================
// EXPORT FUNCTIONALITY
// ============================================

/**
 * Export message as PDF
 */
async function exportMessagePDF(messageId) {
    try {
        const msgData = window.messageMetadata[messageId];
        if (!msgData) {
            throw new Error('Message data not found');
        }
        
        const response = await fetch('/api/export/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                result: {
                    query: 'Chat Export',
                    answer: msgData.content,
                    evidence: msgData.metadata.evidence || [],
                    confidence: msgData.metadata.confidence || 0,
                    model: msgData.metadata.model || 'Unknown',
                    trace_id: msgData.metadata.trace_id || '',
                    source_count: msgData.metadata.source_count || 0,
                    timestamp: new Date().toISOString()
                }
            })
        });
        
        if (!response.ok) {
            throw new Error('Export failed');
        }
        
        const blob = await response.blob();
        downloadFile(blob, `threat-ai-report-${Date.now()}.pdf`, 'application/pdf');
        
    } catch (error) {
        console.error('Error exporting PDF:', error);
        alert('Error exporting PDF: ' + error.message);
    }
}

/**
 * Export message as CSV
 */
async function exportMessageCSV(messageId) {
    try {
        const msgData = window.messageMetadata[messageId];
        if (!msgData) {
            throw new Error('Message data not found');
        }
        
        const response = await fetch('/api/export/csv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                result: {
                    query: 'Chat Export',
                    answer: msgData.content,
                    evidence: msgData.metadata.evidence || [],
                    confidence: msgData.metadata.confidence || 0,
                    model: msgData.metadata.model || 'Unknown',
                    trace_id: msgData.metadata.trace_id || '',
                    source_count: msgData.metadata.source_count || 0,
                    timestamp: new Date().toISOString()
                }
            })
        });
        
        if (!response.ok) {
            throw new Error('Export failed');
        }
        
        const blob = await response.blob();
        downloadFile(blob, `threat-ai-export-${Date.now()}.csv`, 'text/csv');
        
    } catch (error) {
        console.error('Error exporting CSV:', error);
        alert('Error exporting CSV: ' + error.message);
    }
}

/**
 * Download file helper
 */
function downloadFile(blob, filename, mimeType) {
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

// ============================================
// FEEDBACK SYSTEM
// ============================================

let currentFeedbackMessageId = null;
let currentFeedbackRating = 0;

/**
 * Quick feedback (thumbs up/down)
 */
async function quickFeedback(messageId, type) {
    const msgData = window.messageMetadata[messageId];
    if (!msgData) return;
    
    // Visual feedback
    const buttons = event.target.closest('.message-actions').querySelectorAll('.action-btn-icon');
    buttons.forEach(btn => btn.classList.remove('active'));
    event.target.classList.add('active');
    
    try {
        await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: 'Chat message',
                answer: msgData.content,
                rating: type === 'positive' ? 5 : 1,
                relevance: type === 'positive' ? 'relevant' : 'not_relevant',
                accuracy: '',
                comments: `Quick feedback: ${type}`,
                trace_id: msgData.metadata.trace_id || ''
            })
        });
    } catch (error) {
        console.error('Error submitting quick feedback:', error);
    }
}

/**
 * Open feedback modal
 */
function openFeedbackModal(messageId) {
    currentFeedbackMessageId = messageId;
    currentFeedbackRating = 0;
    
    // Reset form
    document.querySelectorAll('#modal-rating-stars .star-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById('modal-relevance').value = '';
    document.getElementById('modal-accuracy').value = '';
    document.getElementById('modal-comments').value = '';
    
    // Show modal
    document.getElementById('feedback-modal').style.display = 'flex';
}

/**
 * Close feedback modal
 */
function closeFeedbackModal() {
    document.getElementById('feedback-modal').style.display = 'none';
    currentFeedbackMessageId = null;
    currentFeedbackRating = 0;
}

/**
 * Set rating in modal
 */
function setModalRating(rating) {
    currentFeedbackRating = rating;
    
    const stars = document.querySelectorAll('#modal-rating-stars .star-btn');
    stars.forEach((star, index) => {
        if (index < rating) {
            star.classList.add('active');
        } else {
            star.classList.remove('active');
        }
    });
}

/**
 * Submit feedback
 */
async function submitFeedback() {
    if (!currentFeedbackMessageId) return;
    
    const msgData = window.messageMetadata[currentFeedbackMessageId];
    if (!msgData) {
        alert('Message data not found');
        return;
    }
    
    const relevance = document.getElementById('modal-relevance').value;
    const accuracy = document.getElementById('modal-accuracy').value;
    const comments = document.getElementById('modal-comments').value;
    
    if (currentFeedbackRating === 0 && !relevance && !accuracy && !comments) {
        alert('Please provide at least one piece of feedback');
        return;
    }
    
    try {
        const response = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: 'Chat message',
                answer: msgData.content,
                rating: currentFeedbackRating || 0,
                relevance: relevance,
                accuracy: accuracy,
                comments: comments,
                trace_id: msgData.metadata.trace_id || '',
                evidence_count: msgData.metadata.evidence ? msgData.metadata.evidence.length : 0
            })
        });
        
        if (response.ok) {
            closeFeedbackModal();
            
            // Show success message
            const toast = document.createElement('div');
            toast.className = 'feedback-toast';
            toast.textContent = '✓ Thank you for your feedback!';
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.classList.add('show');
            }, 10);
            
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => document.body.removeChild(toast), 300);
            }, 3000);
        } else {
            alert('Error submitting feedback');
        }
    } catch (error) {
        console.error('Error submitting feedback:', error);
        alert('Error submitting feedback: ' + error.message);
    }
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && document.getElementById('feedback-modal').style.display === 'flex') {
        closeFeedbackModal();
    }
});
