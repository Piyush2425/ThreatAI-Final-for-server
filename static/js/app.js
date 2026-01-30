/**
 * THREAT-AI Application JavaScript
 * Main functionality for threat intelligence queries and UI interactions
 */

// ============================================
// STATUS & INITIALIZATION
// ============================================

/**
 * Load and display system status
 */
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        
        document.getElementById('status-llm').textContent = status.llm_mode;
        document.getElementById('status-model').textContent = status.model;
        document.getElementById('status-init').textContent = status.initialized ? '✓ Ready' : '✗ Error';
        
        // Update status color
        const statusEl = document.getElementById('status-init');
        if (status.initialized) {
            statusEl.style.color = 'var(--accent-success)';
        } else {
            statusEl.style.color = 'var(--accent-danger)';
        }
    } catch (error) {
        console.error('Error loading status:', error);
        document.getElementById('status-init').textContent = '✗ Error';
        document.getElementById('status-init').style.color = 'var(--accent-danger)';
    }
}

/**
 * Load sample queries from API
 */
async function loadSamples() {
    try {
        const response = await fetch('/api/samples');
        const data = await response.json();
        const container = document.getElementById('sample-buttons');
        
        data.samples.forEach(sample => {
            const btn = document.createElement('button');
            btn.className = 'sample-btn';
            btn.textContent = sample;
            btn.type = 'button';
            btn.onclick = (e) => {
                e.preventDefault();
                document.getElementById('query').value = sample;
                document.getElementById('query').focus();
            };
            container.appendChild(btn);
        });
    } catch (error) {
        console.error('Error loading samples:', error);
    }
}

// ============================================
// QUERY & RESULTS
// ============================================

let lastResult = null;

/**
 * Submit query for threat analysis
 */
async function submitQuery() {
    const query = document.getElementById('query').value.trim();
    if (!query) {
        showError('Please enter a threat intelligence query');
        return;
    }

    const btn = document.getElementById('submit-btn');
    const resultsDiv = document.getElementById('results');

    btn.disabled = true;
    resultsDiv.innerHTML = `
        <div class="loading">
            <div class="spinner"></div>
            <div class="loading-text">🔍 Analyzing threat intelligence...</div>
            <div class="loading-text" style="margin-top: 8px; opacity: 0.7;">Searching vector database and generating insights</div>
        </div>
    `;

    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
        });

        const result = await response.json();

        if (!response.ok) {
            showError(result.error || 'Unknown error occurred');
            return;
        }

        displayResults(result);
        showFeedbackSection();

    } catch (error) {
        showError(`Connection error: ${error.message}`);
    } finally {
        btn.disabled = false;
    }
}

/**
 * Display query results with formatting
 */
function displayResults(result) {
    lastResult = result;
    const confidence = result.confidence || 0;
    const confidencePercent = (confidence * 100).toFixed(1);
    
    let html = '<div class="result-card">';
    
    // Header
    html += '<div class="result-header">';
    html += `<div class="result-query">${escapeHtml(result.query)}</div>`;
    html += `<div class="confidence-badge">`;
    html += `<span>Confidence</span>`;
    html += `<div class="confidence-bar"><div class="confidence-fill" style="width: ${confidencePercent}%"></div></div>`;
    html += `<span>${confidencePercent}%</span>`;
    html += `</div>`;
    html += '</div>';
    
    // Answer
    html += `<div class="result-answer">${escapeHtml(result.answer)}</div>`;
    
    // Evidence
    if (result.evidence && result.evidence.length > 0) {
        html += '<div class="evidence-section">';
        html += '<div class="evidence-header">';
        html += '<span>📚 Evidence Sources</span>';
        html += `<span class="evidence-count">${result.evidence.length}</span>`;
        html += '</div>';
        html += '<div class="evidence-list">';
        
        result.evidence.forEach((e, i) => {
            html += '<div class="evidence-item">';
            html += '<div class="evidence-meta">';
            html += `<span class="evidence-source">[${i+1}] ${escapeHtml(e.actor || 'Unknown')} • ${escapeHtml(e.source)}</span>`;
            html += `<span class="evidence-score">Score: ${e.score.toFixed(3)}</span>`;
            html += '</div>';
            html += `<div class="evidence-text">${escapeHtml(e.text)}</div>`;
            html += '</div>';
        });
        
        html += '</div></div>';
    }
    
    // Metadata
    html += '<div class="metadata">';
    html += `<div class="metadata-item">`;
    html += `<span class="metadata-label">Model</span>`;
    html += `<span class="metadata-value">${escapeHtml(result.model)}</span>`;
    html += `</div>`;
    html += `<div class="metadata-item">`;
    html += `<span class="metadata-label">Sources</span>`;
    html += `<span class="metadata-value">${result.source_count}</span>`;
    html += `</div>`;
    html += `<div class="metadata-item">`;
    html += `<span class="metadata-label">Timestamp</span>`;
    html += `<span class="metadata-value">${new Date(result.timestamp).toLocaleTimeString()}</span>`;
    html += `</div>`;
    if (result.trace_id) {
        html += `<div class="metadata-item">`;
        html += `<span class="metadata-label">Trace ID</span>`;
        html += `<span class="metadata-value">${result.trace_id.substring(0, 8)}</span>`;
        html += `</div>`;
    }
    html += '</div>';
    
    html += '</div>';
    
    document.getElementById('results').innerHTML = html;
}

/**
 * Display error message
 */
function showError(message) {
    const html = `
        <div class="error">
            <span class="error-icon">⚠️</span>
            <div>
                <strong>Error:</strong> ${escapeHtml(message)}
            </div>
        </div>
    `;
    document.getElementById('results').innerHTML = html;
}

// ============================================
// FEEDBACK SECTION
// ============================================

/**
 * Show feedback section after query results
 */
function showFeedbackSection() {
    const feedbackSection = document.getElementById('feedback-section');
    if (feedbackSection) {
        feedbackSection.style.display = 'block';
        // Reset feedback form
        resetFeedbackForm();
    }
}

/**
 * Hide feedback section
 */
function hideFeedbackSection() {
    const feedbackSection = document.getElementById('feedback-section');
    if (feedbackSection) {
        feedbackSection.style.display = 'none';
    }
}

/**
 * Reset feedback form to default state
 */
function resetFeedbackForm() {
    document.getElementById('rating-stars')?.querySelectorAll('.star-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById('feedback-relevance').value = '';
    document.getElementById('feedback-accuracy').value = '';
    document.getElementById('feedback-completeness').value = '';
    document.getElementById('feedback-comments').value = '';
    document.getElementById('feedback-corrections').value = '';
}

/**
 * Set rating from star buttons
 */
function setRating(rating) {
    const stars = document.getElementById('rating-stars');
    if (!stars) return;
    
    stars.querySelectorAll('.star-btn').forEach(btn => {
        const btnRating = parseInt(btn.getAttribute('data-rating'));
        if (btnRating <= rating) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

/**
 * Submit feedback for the query response
 */
async function submitFeedback() {
    const ratingStars = document.getElementById('rating-stars');
    let rating = null;
    if (ratingStars) {
        const activeStars = Array.from(ratingStars.querySelectorAll('.star-btn.active'));
        if (activeStars.length > 0) {
            rating = Math.max(
                ...activeStars.map(btn => parseInt(btn.getAttribute('data-rating'), 10)).filter(n => !Number.isNaN(n))
            );
        }
    }

    const feedback = {
        rating,
        relevance: document.getElementById('feedback-relevance').value,
        accuracy: document.getElementById('feedback-accuracy').value,
        completeness: document.getElementById('feedback-completeness').value,
        comments: document.getElementById('feedback-comments').value,
        corrections: document.getElementById('feedback-corrections').value,
        timestamp: new Date().toISOString(),
        query: lastResult?.query || null,
        answer: lastResult?.answer || null,
        trace_id: lastResult?.trace_id || null,
        model: lastResult?.model || null,
        source_count: typeof lastResult?.source_count === 'number' ? lastResult.source_count : null,
        confidence: typeof lastResult?.confidence === 'number' ? lastResult.confidence : null
    };

    try {
        const response = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(feedback)
        });

        if (!response.ok) {
            const error = await response.json();
            alert('Error submitting feedback: ' + error.error);
            return;
        }

        alert('✓ Feedback submitted successfully!');
        resetFeedbackForm();
        hideFeedbackSection();

    } catch (error) {
        alert('Error submitting feedback: ' + error.message);
    }
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

/**
 * Escape HTML special characters
 */
function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

// ============================================
// EVENT LISTENERS
// ============================================

/**
 * Initialize application on DOM load
 */
document.addEventListener('DOMContentLoaded', () => {
    loadStatus();
    loadSamples();
    
    // Keyboard shortcut: Ctrl+Enter to submit
    const queryTextarea = document.getElementById('query');
    if (queryTextarea) {
        queryTextarea.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') {
                e.preventDefault();
                submitQuery();
            }
        });
    }
});
