/**
 * THREAT-AI Application JavaScript
 * Main functionality for threat intelligence queries and UI interactions
 */

// ============================================
// GLOBAL STATE
// ============================================

let lastResult = null;
let historyCache = [];

/**
 * Escape HTML special characters to prevent injection
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

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
                const queryInput = document.getElementById('query');
                if (queryInput) {
                    queryInput.value = sample;
                    queryInput.focus();
                }
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
    
    // Hide center container and show results area
    const centerContainer = document.getElementById('center-container');
    const resultsArea = document.getElementById('results-area');
    
    if (centerContainer) centerContainer.style.display = 'none';
    if (resultsArea) resultsArea.style.display = 'block';
    
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
    
    // Add export buttons after results
    addExportButtons();
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
// EXPORT FUNCTIONALITY
// ============================================

/**
 * Add export buttons below results
 */
function addExportButtons() {
    const resultsContainer = document.getElementById('results');
    if (!resultsContainer) return;
    
    const exportDiv = document.createElement('div');
    exportDiv.id = 'export-buttons';
    exportDiv.className = 'export-buttons';
    exportDiv.innerHTML = `
        <button onclick="exportPDF()" class="export-btn export-btn-pdf" title="Download as PDF">
            📄 Export as PDF
        </button>
        <button onclick="exportCSV()" class="export-btn export-btn-csv" title="Download as CSV">
            📊 Export as CSV
        </button>
    `;
    resultsContainer.appendChild(exportDiv);
}

/**
 * Export results as PDF
 */
async function exportPDF() {
    if (!lastResult) {
        alert('No results to export');
        return;
    }
    
    try {
        const response = await fetch('/api/export/pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ result: lastResult })
        });
        
        if (!response.ok) {
            const error = await response.json();
            alert('Error exporting PDF: ' + error.error);
            return;
        }
        
        const blob = await response.blob();
        downloadFile(blob, 'threat-intelligence-report.pdf', 'application/pdf');
        
    } catch (error) {
        alert('Error exporting PDF: ' + error.message);
    }
}

/**
 * Export results as CSV
 */
async function exportCSV() {
    if (!lastResult) {
        alert('No results to export');
        return;
    }
    
    try {
        const response = await fetch('/api/export/csv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ result: lastResult })
        });
        
        if (!response.ok) {
            const error = await response.json();
            alert('Error exporting CSV: ' + error.error);
            return;
        }
        
        const blob = await response.blob();
        downloadFile(blob, 'threat-intelligence-report.csv', 'text/csv');
        
    } catch (error) {
        alert('Error exporting CSV: ' + error.message);
    }
}

/**
 * Helper function to download file
 */
function downloadFile(blob, filename, mimeType) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
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
    const ratingStars = document.getElementById('rating-stars');
    if (ratingStars) {
        ratingStars.querySelectorAll('.star-btn').forEach(btn => {
            btn.classList.remove('active');
        });
    }
    
    const relevance = document.getElementById('feedback-relevance');
    if (relevance) relevance.value = '';
    
    const accuracy = document.getElementById('feedback-accuracy');
    if (accuracy) accuracy.value = '';
    
    const comments = document.getElementById('feedback-comments');
    if (comments) comments.value = '';
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
    loadQueryHistory();
    
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
    
    // History search
    const historySearch = document.getElementById('history-search');
    if (historySearch) {
        historySearch.addEventListener('input', debounce((e) => {
            const term = e.target.value.trim();
            if (term) {
                searchHistory(term);
            } else {
                loadQueryHistory();
            }
        }, 300));
    }
});

// ============================================
// QUERY HISTORY FUNCTIONS
// ============================================

/**
 * Load query history from backend
 */
async function loadQueryHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        
        historyCache = data.queries;
        displayHistory(historyCache);
        updateHistoryStats(data.stats);
        
    } catch (error) {
        console.error('Error loading history:', error);
    }
}

/**
 * Display query history in sidebar
 */
function displayHistory(queries) {
    const historyList = document.getElementById('history-list');
    if (!historyList) return;
    
    if (queries.length === 0) {
        historyList.innerHTML = '<div class="empty-history">No queries yet</div>';
        return;
    }
    
    historyList.innerHTML = queries.map(q => `
        <div class="history-item" onclick="loadQueryFromHistory('${q.query_id}', '${escapeHtml(q.query).replace(/'/g, "\\'")}')">
            <div style="font-weight: 600; margin-bottom: 2px;">${escapeHtml(q.query.substring(0, 40))}</div>
            <div style="font-size: 11px; opacity: 0.7;">
                ${new Date(q.timestamp).toLocaleDateString()}
            </div>
        </div>
    `).join('');
}

/**
 * Update history statistics
 */
function updateHistoryStats(stats) {
    const statsDiv = document.getElementById('history-stats');
    if (statsDiv) {
        statsDiv.innerHTML = `
            <p>Total: ${stats.total_queries}</p>
            <p>Size: ${stats.storage_size_kb} KB</p>
        `;
    }
}

/**
 * Search query history
 */
async function searchHistory(term) {
    try {
        const response = await fetch(`/api/history/search?q=${encodeURIComponent(term)}`);
        const data = await response.json();
        displayHistory(data.queries);
    } catch (error) {
        console.error('Error searching history:', error);
    }
}

/**
 * Load query from history
 */
function loadQueryFromHistory(queryId, query) {
    const queryInput = document.getElementById('query');
    if (queryInput) {
        queryInput.value = query;
        queryInput.focus();
    }
}

/**
 * New query - clear form
 */
function newQuery() {
    // Clear query input
    const queryInput = document.getElementById('query');
    if (queryInput) {
        queryInput.value = '';
    }
    
    // Hide results area and show center container
    const resultsArea = document.getElementById('results-area');
    const centerContainer = document.getElementById('center-container');
    
    if (resultsArea) resultsArea.style.display = 'none';
    if (centerContainer) centerContainer.style.display = 'flex';
    
    // Hide feedback
    hideFeedbackSection();
    
    // Focus query input
    if (queryInput) queryInput.focus();
}

/**
 * Clear all history
 */
async function clearHistory() {
    if (!confirm('Are you sure you want to clear all query history?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/history/clear', {
            method: 'POST'
        });
        
        if (response.ok) {
            historyCache = [];
            displayHistory([]);
            updateHistoryStats({ total_queries: 0, storage_size_kb: 0 });
        }
    } catch (error) {
        console.error('Error clearing history:', error);
        alert('Error clearing history: ' + error.message);
    }
}

/**
 * Debounce helper function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ============================================
// UI INTERACTION FUNCTIONS
// ============================================

/**
 * Toggle quick examples display
 */
function toggleSamples() {
    const examples = document.getElementById('quick-examples');
    if (examples.style.display === 'none') {
        examples.style.display = 'block';
    } else {
        examples.style.display = 'none';
    }
}

/**
 * Toggle history panel in sidebar
 */
function toggleHistory() {
    const historyPanel = document.getElementById('history-panel');
    const navBtns = document.querySelectorAll('.nav-btn');
    
    if (historyPanel.style.display === 'none') {
        historyPanel.style.display = 'block';
        // Mark history button as active
        navBtns.forEach(btn => {
            if (btn.textContent.includes('History')) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
        loadQueryHistory();
    } else {
        historyPanel.style.display = 'none';
        navBtns[0].classList.add('active');
    }
}

/**
 * Show discover view (placeholder)
 */
function showDiscover() {
    alert('Discover feature coming soon!');
}

/**
 * Show settings view (placeholder)
 */
function showSettings() {
    alert('Settings feature coming soon!');
}

/**
 * Show export options
 */
function showExportOptions() {
    if (!lastResult) {
        alert('No results to export. Please run a query first.');
        return;
    }
    const choice = confirm('Export as PDF? (Cancel for CSV)');
    if (choice) {
        exportPDF();
    } else {
        exportCSV();
    }
}

/**
 * Attach file (placeholder)
 */
function attachFile() {
    alert('File attachment feature coming soon!');
}


