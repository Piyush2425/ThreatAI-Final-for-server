/**
 * Theme Manager Module
 * Handles dark/light theme switching and persistence
 */

const THEME_KEY = 'threat-ai-theme';
const ICON_MOON =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path></svg>';
const ICON_SUN =
  '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="M4.93 4.93l1.41 1.41"></path><path d="M17.66 17.66l1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="M6.34 17.66l-1.41 1.41"></path><path d="M19.07 4.93l-1.41 1.41"></path></svg>';

export class ThemeManager {
  private currentTheme: 'light' | 'dark';

  constructor() {
    this.currentTheme = this.getStoredTheme();
  }

  /**
   * Initialize theme on app startup
   */
  init(): void {
    this.applyTheme(this.currentTheme);
    this.attachToggleListener();
  }

  /**
   * Get stored theme preference
   */
  private getStoredTheme(): 'light' | 'dark' {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === 'dark' || stored === 'light') {
      return stored;
    }

    // Check system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }

    return 'light';
  }

  /**
   * Apply theme to document
   */
  private applyTheme(theme: 'light' | 'dark'): void {
    this.currentTheme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    this.updateToggleIcon();
  }

  /**
   * Update theme toggle button icon
   */
  private updateToggleIcon(): void {
    const icon = document.getElementById('theme-icon');
    const toggleBtn = document.getElementById('theme-toggle');

    if (icon) {
      icon.innerHTML = this.currentTheme === 'dark' ? ICON_SUN : ICON_MOON;
    }

    if (toggleBtn) {
      const nextTheme = this.currentTheme === 'dark' ? 'light' : 'dark';
      toggleBtn.setAttribute('title', `Switch to ${nextTheme} mode`);
      toggleBtn.setAttribute('aria-label', `Switch to ${nextTheme} mode`);
    }
  }

  /**
   * Attach click handler to theme toggle button
   */
  private attachToggleListener(): void {
    const toggleBtn = document.getElementById('theme-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => this.toggle());
    }
  }

  /**
   * Toggle between light and dark theme
   */
  toggle(): void {
    const nextTheme = this.currentTheme === 'dark' ? 'light' : 'dark';
    this.applyTheme(nextTheme);
  }

  /**
   * Explicitly set theme from settings UI.
   */
  setTheme(theme: 'light' | 'dark'): void {
    this.applyTheme(theme);
  }

  /**
   * Get current theme
   */
  getTheme(): 'light' | 'dark' {
    return this.currentTheme;
  }
}
