/**
 * custom.js
 * -----------------------------------------------------------------------------
 * Custom enhancements for Sartre 2 Jupyter Book:
 * 1. Immediate 2-state Dark/Light mode toggle (fixes 3-state PyData bug)
 * 2. VS Code Dark+ semantic syntax highlighting (ROOT, C++, Python, Runcard)
 * 3. Smooth scrolling for internal anchor links and chapter jumps
 * 4. Animated expand/collapse for subchapters and TOC entries
 * -----------------------------------------------------------------------------
 */

(function () {
  'use strict';

  // =========================================================================
  // 1. Theme Mode: Enforce Dark Default & Immediate 2-State Switcher
  // =========================================================================
  function initThemeToggle() {
    const savedMode = localStorage.getItem('mode') || localStorage.getItem('theme');
    
    // Default to dark mode if not explicitly chosen
    if (!savedMode || savedMode === 'auto') {
      document.documentElement.dataset.mode = 'dark';
      document.documentElement.dataset.theme = 'dark';
      localStorage.setItem('mode', 'dark');
      localStorage.setItem('theme', 'dark');
    }

    function toggleTheme(e) {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
      }

      const currentTheme = document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

      document.documentElement.dataset.mode = newTheme;
      document.documentElement.dataset.theme = newTheme;
      localStorage.setItem('mode', newTheme);
      localStorage.setItem('theme', newTheme);

      // Update dropdown menus if present
      document.querySelectorAll('.dropdown-menu').forEach(function (el) {
        if (newTheme === 'dark') {
          el.classList.add('dropdown-menu-dark');
        } else {
          el.classList.remove('dropdown-menu-dark');
        }
      });

      console.log('[ThemeToggle] Directly toggled to:', newTheme);
    }

    // Intercept all theme-switch buttons in capture phase
    const switchBtns = document.querySelectorAll('.theme-switch-button');
    switchBtns.forEach(function (btn) {
      btn.addEventListener('click', toggleTheme, true);
    });
  }

  // =========================================================================
  // 2. Smooth Scrolling for Internal Links & TOC
  // =========================================================================
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
      anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (!href || href === '#') return;

        const target = document.querySelector(href);
        if (target) {
          e.preventDefault();
          const targetY = target.getBoundingClientRect().top + window.pageYOffset - 20;
          window.scrollTo({
            top: targetY,
            behavior: 'smooth'
          });
          // Update URL hash without jumping
          if (history.pushState) {
            history.pushState(null, null, href);
          }
        }
      });
    });
  }

  // =========================================================================
  // 3. Smooth Expanding Animation for Subchapters / Subsections
  // =========================================================================
  function initNavAnimations() {
    // Add smooth animated transitions to collapsible sidebar sub-lists
    const subLists = document.querySelectorAll('.bd-sidenav ul, .section-nav ul');
    subLists.forEach(function (ul) {
      ul.style.transition = 'max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s ease';
    });

    // Animate details / dropdown cards
    document.querySelectorAll('details.sd-dropdown, details.dropdown').forEach(function (details) {
      details.addEventListener('toggle', function () {
        if (this.open) {
          this.style.opacity = '0';
          this.style.transform = 'translateY(-4px)';
          requestAnimationFrame(() => {
            this.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
            this.style.opacity = '1';
            this.style.transform = 'translateY(0)';
          });
        }
      });
    });
  }

  // =========================================================================
  // 4. VS Code Dark+ Semantic Syntax Highlighting
  // =========================================================================
  function enhanceVSCodeSyntax() {
    // Known C++ / ROOT types and custom classes
    const cppTypes = new Set([
      'Event', 'TRandom3', 'EventGeneratorSettings', 'Sartre', 'TLorentzVector',
      'TTree', 'TFile', 'TH1D', 'Settings', 'TwoBodyVectorMesonDecay',
      'ParticleBranch', 'string', 'vector', 'ROOT'
    ]);

    // Known Python scientific libraries / modules
    const pyModules = new Set([
      'np', 'plt', 'pd', 'ak', 'uproot', 'vector', 'scipy', 'os', 'sys'
    ]);

    // Apply to all code blocks
    document.querySelectorAll('.highlight pre').forEach(function (pre) {
      // 1. Process custom types and module names
      pre.querySelectorAll('.n').forEach(function (span) {
        const text = span.textContent.trim();

        if (cppTypes.has(text) || pyModules.has(text)) {
          span.classList.add('vscode-type');
          return;
        }

        // Check if this identifier is immediately followed by a call '('
        const nextNode = span.nextSibling;
        if (nextNode) {
          const nextText = nextNode.textContent || '';
          if (nextText.trim().startsWith('(')) {
            span.classList.add('vscode-fn');
            return;
          }
        }
      });

      // 2. Process function calls following a dot or arrow (e.g. plt.subplots, sartre.init, v.Px)
      pre.querySelectorAll('.n').forEach(function (span) {
        if (span.classList.contains('vscode-type') || span.classList.contains('vscode-fn')) return;
        const prevNode = span.previousSibling;
        if (prevNode && (prevNode.textContent.endsWith('.') || prevNode.textContent.endsWith('->') || prevNode.textContent.endsWith('::'))) {
          const nextNode = span.nextSibling;
          if (nextNode && nextNode.textContent.trim().startsWith('(')) {
            span.classList.add('vscode-fn');
          }
        }
      });

      // 3. Process keyword arguments in Python (e.g., `figsize=`, `bins=`, `color=`)
      pre.querySelectorAll('.n').forEach(function (span) {
        if (span.classList.contains('vscode-type') || span.classList.contains('vscode-fn')) return;
        const nextNode = span.nextSibling;
        if (nextNode) {
          const nextText = nextNode.textContent || '';
          if (nextText.trim().startsWith('=')) {
            span.classList.add('vscode-param');
          }
        }
      });
    });

    // 4. Refine INI / Runcard syntax (eliminate radioactive green & yellow)
    document.querySelectorAll('.highlight-ini pre, .highlight-cfg pre').forEach(function (pre) {
      // Color keys soft light-blue
      pre.querySelectorAll('.na').forEach(function (span) {
        span.classList.add('vscode-ini-key');
      });

      // Distinguish boolean vs numbers vs strings in values
      pre.querySelectorAll('.s, .o, .mi, .mf').forEach(function (span) {
        const val = span.textContent.trim();
        if (val === 'true' || val === 'false') {
          span.classList.remove('s');
          span.classList.add('vscode-ini-bool');
        } else if (/^-?\d+(\.\d+)?$/.test(val)) {
          span.classList.remove('s');
          span.classList.add('vscode-ini-number');
        } else if (span.classList.contains('s')) {
          span.classList.add('vscode-ini-value');
        }
      });
    });
  }

  // =========================================================================
  // Initialization
  // =========================================================================
  function initAll() {
    initThemeToggle();
    initSmoothScroll();
    initNavAnimations();
    enhanceVSCodeSyntax();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
