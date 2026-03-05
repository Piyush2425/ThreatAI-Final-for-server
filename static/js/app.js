/**
 * THREAT-AI Application JavaScript
 * Main functionality for threat intelligence queries and UI interactions
 */

// ============================================
// GLOBAL STATE
// ============================================

let lastResult = null;
let historyCache = [];
const THEME_KEY = 'threat-ai-theme';

function syncThemeToggle(theme) {
    const icon = document.getElementById('theme-icon');
    const label = document.getElementById('theme-label');
    if (!icon || !label) return;
    const isDark = theme === 'dark';
    icon.textContent = isDark ? '☀️' : '🌙';
    label.textContent = isDark ? 'Light' : 'Dark';
}

function applyTheme(theme) {
    const nextTheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', nextTheme);
    localStorage.setItem(THEME_KEY, nextTheme);
    syncThemeToggle(nextTheme);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    applyTheme(current === 'dark' ? 'light' : 'dark');
}

function initTheme() {
    const stored = localStorage.getItem(THEME_KEY);
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initial = stored || (prefersDark ? 'dark' : 'light');
    applyTheme(initial);
}

/**
 * Escape HTML special characters to prevent injection
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function extractSummary(answer) {
    if (!answer) return 'No summary available.';
    const cleaned = answer
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/\*([^*]+)\*/g, '$1')
        .replace(/\s+/g, ' ')
        .trim();
    const sentences = cleaned.match(/[^.!?]+[.!?]+/g);
    if (sentences && sentences.length) {
        return sentences.slice(0, 2).join(' ').trim();
    }
    return cleaned.slice(0, 220);
}

function findLastKnownActivity(answer) {
    if (!answer) return '';
    const match = answer.match(/Last Known Activity\s*:\s*([^\n]+)/i);
    if (match && match[1]) return match[1].trim();
    const fallback = answer.match(/Last (?:Updated|Seen|Card Change)\s*:\s*([^\n]+)/i);
    return fallback && fallback[1] ? fallback[1].trim() : '';
}

function findFirstSeen(answer) {
    if (!answer) return '';
    const match = answer.match(/First Seen\s*:\s*([^\n]+)/i);
    return match && match[1] ? match[1].trim() : '';
}

function extractYears(text) {
    if (!text) return [];
    const matches = text.match(/\b(19\d{2}|20\d{2})\b/g) || [];
    return matches.map((y) => parseInt(y, 10)).filter((y) => !Number.isNaN(y));
}

function computePeakYear(evidence, answer) {
    const yearCounts = new Map();
    if (Array.isArray(evidence)) {
        evidence.forEach((item) => {
            extractYears(item.text).forEach((year) => {
                yearCounts.set(year, (yearCounts.get(year) || 0) + 1);
            });
        });
    }
    extractYears(answer).forEach((year) => {
        yearCounts.set(year, (yearCounts.get(year) || 0) + 1);
    });
    if (!yearCounts.size) return '';
    let bestYear = null;
    let bestCount = -1;
    yearCounts.forEach((count, year) => {
        if (count > bestCount || (count === bestCount && year > bestYear)) {
            bestYear = year;
            bestCount = count;
        }
    });
    return bestYear ? String(bestYear) : '';
}

function buildTimelineHtml(result) {
    const firstSeen = findFirstSeen(result.answer) || 'Unknown';
    const lastKnown = findLastKnownActivity(result.answer) || 'Unknown';
    const peakYear = computePeakYear(result.evidence || [], result.answer || '') || 'Unknown';
    return `
        <div class="timeline-card">
            <div class="section-title">Timeline</div>
            <div class="timeline-track">
                <div class="timeline-node">
                    <div class="timeline-label">First Seen</div>
                    <div class="timeline-value">${escapeHtml(firstSeen)}</div>
                </div>
                <div class="timeline-node">
                    <div class="timeline-label">Peak Activity</div>
                    <div class="timeline-value">${escapeHtml(peakYear)}</div>
                </div>
                <div class="timeline-node">
                    <div class="timeline-label">Last Known</div>
                    <div class="timeline-value">${escapeHtml(lastKnown)}</div>
                </div>
            </div>
        </div>
    `;
}

function buildEvidenceTableHtml(evidence) {
    if (!Array.isArray(evidence) || evidence.length === 0) return '';
    const maxRows = 12;
    const rows = evidence.slice(0, maxRows).map((item, idx) => {
        const links = Array.isArray(item.links) ? item.links.filter((l) => typeof l === 'string') : [];
        const link = links.length ? links[0] : '';
        const linkHtml = link
            ? `<a href="${encodeURI(link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link)}</a>`
            : 'N/A';
        return `
            <tr>
                <td>${idx + 1}</td>
                <td>${escapeHtml(item.actor || 'Unknown')}</td>
                <td>${escapeHtml(item.source || 'Unknown')}</td>
                <td>${typeof item.score === 'number' ? item.score.toFixed(3) : '0.000'}</td>
                <td class="evidence-link-cell">${linkHtml}</td>
            </tr>
        `;
    }).join('');

    const note = evidence.length > maxRows
        ? `<div class="evidence-note">Showing ${maxRows} of ${evidence.length} sources.</div>`
        : '';

    return `
        <div class="report-section">
            <div class="section-title">Appendix: Evidence Table</div>
            <div class="evidence-table-wrapper">
                <table class="evidence-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Actor</th>
                            <th>Source</th>
                            <th>Score</th>
                            <th>Link</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows}
                    </tbody>
                </table>
            </div>
            ${note}
        </div>
    `;
}

function buildDetailedAnalysisHtml(answer) {
    if (!answer) {
        return {
            tocHtml: '',
            contentHtml: '<div class="analysis-body">No analysis available.</div>'
        };
    }

    const headingRegex = /^\s*\*\*([^*]+)\*\*\s*$/gm;
    const matches = [];
    let match;

    while ((match = headingRegex.exec(answer)) !== null) {
        matches.push({
            title: match[1].trim(),
            start: match.index,
            end: headingRegex.lastIndex
        });
    }

    if (matches.length === 0) {
        const body = escapeHtml(answer).replace(/\n/g, '<br>');
        return {
            tocHtml: '',
            contentHtml: `<div class="analysis-section"><div class="analysis-body">${body}</div></div>`
        };
    }

    const sections = [];
    let preamble = answer.slice(0, matches[0].start).trim();
    if (preamble) {
        sections.push({ title: 'Overview', content: preamble });
    }

    for (let i = 0; i < matches.length; i += 1) {
        const current = matches[i];
        const nextStart = i + 1 < matches.length ? matches[i + 1].start : answer.length;
        const content = answer.slice(current.end, nextStart).trim();
        sections.push({ title: current.title, content });
    }

    const usedIds = new Map();
    const makeId = (title) => {
        const base = title
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '') || 'section';
        const count = (usedIds.get(base) || 0) + 1;
        usedIds.set(base, count);
        return count === 1 ? base : `${base}-${count}`;
    };

    const tocLinks = [];
    const bodyParts = [];

    sections.forEach((section, index) => {
        const id = makeId(section.title);
        const title = escapeHtml(section.title);
        const content = section.content
            ? escapeHtml(section.content).replace(/\n/g, '<br>')
            : '<span class="analysis-muted">No details provided.</span>';

        tocLinks.push(`<a href="#${id}" class="analysis-toc-link">${title}</a>`);
        bodyParts.push(
            `<div class="analysis-section" id="${id}">` +
                `<div class="analysis-heading"><a href="#${id}">${title}</a></div>` +
                `<div class="analysis-body">${content}</div>` +
            `</div>`
        );

        if (index < sections.length - 1) {
            bodyParts.push('<div class="analysis-divider"></div>');
        }
    });

    const tocHtml = `
        <div class="analysis-toc">
            <div class="analysis-toc-title">On this report</div>
            <div class="analysis-toc-links">${tocLinks.join('')}</div>
        </div>
    `;

    return {
        tocHtml,
        contentHtml: bodyParts.join('')
    };
}

function formatEvidenceLinks(links) {
    if (!Array.isArray(links) || links.length === 0) return '';
    const safeLinks = links
        .filter((l) => typeof l === 'string' && l.startsWith('http'))
        .slice(0, 3);
    if (safeLinks.length === 0) return '';
    const html = safeLinks
        .map((l) => {
            const url = encodeURI(l);
            const label = escapeHtml(l);
            return `<a class="evidence-link" href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`;
        })
        .join('');
    return `<div class="evidence-links">${html}</div>`;
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
    const summary = extractSummary(result.answer);
    const lastActivity = findLastKnownActivity(result.answer);
    const timestamp = result.timestamp ? new Date(result.timestamp).toLocaleString() : 'N/A';
    const responseMode = result.response_mode ? escapeHtml(result.response_mode) : 'adaptive';
    const intent = result.intent ? escapeHtml(result.intent) : 'general';
    const analysis = buildDetailedAnalysisHtml(result.answer || '');
    const primaryActors = Array.isArray(result.primary_actors)
        ? result.primary_actors.filter(Boolean)
        : [];
    const displayTitle = primaryActors.length
        ? `Threat Actor: ${primaryActors.join(', ')}`
        : result.query;
    const displaySub = primaryActors.length ? escapeHtml(result.query) : '';
    
    // Hide center container and show results area
    const centerContainer = document.getElementById('center-container');
    const resultsArea = document.getElementById('results-area');
    
    if (centerContainer) centerContainer.style.display = 'none';
    if (resultsArea) resultsArea.style.display = 'block';
    
    let html = '<div class="result-card report-grid">';
    html += '<div class="report-main">';
    
    // Header
    html += '<div class="result-header">';
    html += '<div class="result-query">';
    html += `<div class="result-query-title">${escapeHtml(displayTitle)}</div>`;
    if (displaySub) {
        html += `<div class="result-query-sub">${displaySub}</div>`;
    }
    html += '</div>';
    html += `<div class="confidence-badge">`;
    html += `<span>Confidence</span>`;
    html += `<div class="confidence-bar"><div class="confidence-fill" style="width: ${confidencePercent}%"></div></div>`;
    html += `<span>${confidencePercent}%</span>`;
    html += `</div>`;
    html += '</div>';

    // Executive Summary
    html += '<div class="summary-card">';
    html += '<div class="summary-header">';
    html += '<span>Executive Summary</span>';
    html += '<span class="summary-chip">Evidence-based</span>';
    html += '</div>';
    html += `<div class="summary-text">${escapeHtml(summary)}</div>`;
    html += '<div class="result-badges">';
    html += `<span class="badge badge-mode">${responseMode}</span>`;
    html += `<span class="badge badge-sources">${result.source_count || 0} sources</span>`;
    html += '</div>';
    html += '</div>';

    // Timeline visual
    html += buildTimelineHtml(result);

    // Answer
    html += '<div class="report-section">';
    html += '<div class="section-title">Detailed Analysis</div>';
    html += analysis.tocHtml;
    html += `<div class="result-answer">${analysis.contentHtml}</div>`;
    html += '</div>';

    // Quick actions
    html += '<div class="result-actions">';
    html += '<button class="action-btn-sm" onclick="copyAnswer()" title="Copy answer to clipboard">📋 Copy Answer</button>';
    html += '</div>';
    
    // Evidence
    if (result.evidence && result.evidence.length > 0) {
        html += '<div class="evidence-section">';
        html += '<details class="evidence-details">';
        html += '<summary class="evidence-summary">';
        html += '<span>📚 Evidence Sources</span>';
        html += `<span class="evidence-count">${result.evidence.length}</span>`;
        html += '<span class="evidence-toggle">Show</span>';
        html += '</summary>';
        html += '<div class="evidence-list">';
        
        result.evidence.forEach((e, i) => {
            html += '<div class="evidence-item">';
            html += '<div class="evidence-meta">';
            html += `<span class="evidence-source">[${i+1}] ${escapeHtml(e.actor || 'Unknown')} • ${escapeHtml(e.source)}</span>`;
            html += `<span class="evidence-score">Score: ${e.score.toFixed(3)}</span>`;
            html += '</div>';
            html += `${formatEvidenceLinks(e.links)}`;
            html += `<div class="evidence-text">${escapeHtml(e.text)}</div>`;
            html += '</div>';
        });
        
        html += '</div></details></div>';
    }

    html += buildEvidenceTableHtml(result.evidence || []);
    
    html += '</div>';

    // Key Facts rail
    html += '<aside class="report-rail">';
    html += '<div class="rail-card">';
    html += '<div class="rail-title">Key Facts</div>';
    html += '<div class="rail-list">';
    if (primaryActors.length) {
        html += `<div class="rail-item"><span class="rail-label">Primary Actor</span><span class="rail-value">${escapeHtml(primaryActors.join(', '))}</span></div>`;
    }
    html += `<div class="rail-item"><span class="rail-label">Confidence</span><span class="rail-value">${confidencePercent}%</span></div>`;
    html += `<div class="rail-item"><span class="rail-label">Sources</span><span class="rail-value">${result.source_count || 0}</span></div>`;
    html += `<div class="rail-item"><span class="rail-label">Mode</span><span class="rail-value">${responseMode}</span></div>`;
    html += `<div class="rail-item"><span class="rail-label">Intent</span><span class="rail-value">${intent}</span></div>`;
    html += `<div class="rail-item"><span class="rail-label">Model</span><span class="rail-value">${escapeHtml(result.model || 'N/A')}</span></div>`;
    html += `<div class="rail-item"><span class="rail-label">Timestamp</span><span class="rail-value">${timestamp}</span></div>`;
    if (lastActivity) {
        html += `<div class="rail-item"><span class="rail-label">Last Known Activity</span><span class="rail-value">${escapeHtml(lastActivity)}</span></div>`;
    }
    if (result.trace_id) {
        html += `<div class="rail-item"><span class="rail-label">Trace ID</span><span class="rail-value">${escapeHtml(result.trace_id.substring(0, 8))}</span></div>`;
    }
    html += '</div>';
    html += '</div>';
    html += '</aside>';

    html += '</div>';
    
    document.getElementById('results').innerHTML = html;
    
    // Add export buttons after results
    addExportButtons();
}

/**
 * Copy latest answer to clipboard
 */
function copyAnswer() {
    if (!lastResult || !lastResult.answer) return;
    const text = lastResult.answer;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch(() => {});
    } else {
        const temp = document.createElement('textarea');
        temp.value = text;
        document.body.appendChild(temp);
        temp.select();
        try { document.execCommand('copy'); } catch (e) {}
        document.body.removeChild(temp);
    }
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
    initTheme();
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


