/**
 * mobile-nav.js
 * -----------------------------------------------------------------------------
 * Robust mobile and tablet sidebar drawer navigation controller for
 * Jupyter Book (Sphinx Book Theme / PyData Sphinx Theme).
 *
 * Resolves upstream theme bug where .primary-toggle click listeners were only
 * attached to the hidden header button and dialog transitions broke on phones.
 *
 * Author: Štěpán Skalka (CTU in Prague)
 * -----------------------------------------------------------------------------
 */

(function () {
  'use strict';

  function initMobileNav() {
    const primarySidebar = document.getElementById('pst-primary-sidebar');
    const secondarySidebar = document.querySelector('.bd-sidebar-secondary');
    if (!primarySidebar) return;

    // 1. Create or get backdrop element
    let backdrop = document.getElementById('pst-mobile-backdrop');
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.id = 'pst-mobile-backdrop';
      backdrop.className = 'pst-mobile-backdrop';
      document.body.appendChild(backdrop);
    }

    // 2. Add clean close button inside primary sidebar if not present
    if (!primarySidebar.querySelector('.pst-mobile-close-btn')) {
      const closeBtn = document.createElement('button');
      closeBtn.className = 'pst-mobile-close-btn';
      closeBtn.setAttribute('aria-label', 'Close sidebar');
      closeBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
      closeBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeAll();
      });
      primarySidebar.insertBefore(closeBtn, primarySidebar.firstChild);
    }

    // 3. Add clean close button inside secondary sidebar if not present
    if (secondarySidebar && !secondarySidebar.querySelector('.pst-mobile-close-btn')) {
      const closeSecBtn = document.createElement('button');
      closeSecBtn.className = 'pst-mobile-close-btn';
      closeSecBtn.setAttribute('aria-label', 'Close page contents');
      closeSecBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
      closeSecBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeAll();
      });
      secondarySidebar.insertBefore(closeSecBtn, secondarySidebar.firstChild);
    }

    function isMobile() {
      return window.innerWidth < 992;
    }

    function openPrimary() {
      if (secondarySidebar) secondarySidebar.classList.remove('mobile-show');
      primarySidebar.classList.add('mobile-show');
      backdrop.classList.add('show');
      document.body.classList.add('pst-mobile-sidebar-open');
    }

    function openSecondary() {
      primarySidebar.classList.remove('mobile-show');
      if (secondarySidebar) secondarySidebar.classList.add('mobile-show');
      backdrop.classList.add('show');
      document.body.classList.add('pst-mobile-sidebar-open');
    }

    function closeAll() {
      primarySidebar.classList.remove('mobile-show');
      if (secondarySidebar) secondarySidebar.classList.remove('mobile-show');
      backdrop.classList.remove('show');
      document.body.classList.remove('pst-mobile-sidebar-open');
    }

    function togglePrimary() {
      if (isMobile()) {
        if (primarySidebar.classList.contains('mobile-show')) {
          closeAll();
        } else {
          openPrimary();
        }
      } else {
        // Desktop collapse/expand
        primarySidebar.classList.toggle('pst-sidebar-hidden');
      }
    }

    function toggleSecondary() {
      if (window.innerWidth < 1200) {
        if (secondarySidebar && secondarySidebar.classList.contains('mobile-show')) {
          closeAll();
        } else {
          openSecondary();
        }
      } else if (secondarySidebar) {
        secondarySidebar.classList.toggle('d-none');
      }
    }

    // 4. Attach click handlers to ALL primary-toggle buttons (in capture phase)
    const primaryToggles = document.querySelectorAll('.primary-toggle, button[aria-label="Site navigation"], button[title*="primary sidebar"]');
    primaryToggles.forEach(function (btn) {
      btn.addEventListener(
        'click',
        function (e) {
          e.preventDefault();
          e.stopPropagation();
          e.stopImmediatePropagation();
          togglePrimary();
        },
        true // capture phase: intercepts before buggy theme scripts
      );
    });

    // 5. Attach click handlers to ALL secondary-toggle buttons (in capture phase)
    const secondaryToggles = document.querySelectorAll('.secondary-toggle, button[aria-label="On this page"], button[title*="secondary sidebar"]');
    secondaryToggles.forEach(function (btn) {
      btn.addEventListener(
        'click',
        function (e) {
          e.preventDefault();
          e.stopPropagation();
          e.stopImmediatePropagation();
          toggleSecondary();
        },
        true
      );
    });

    // 6. Close when backdrop is tapped
    backdrop.addEventListener('click', function (e) {
      e.preventDefault();
      closeAll();
    });

    // 7. Close when any navigation link inside sidebar is tapped
    const navLinks = primarySidebar.querySelectorAll('a.reference');
    navLinks.forEach(function (link) {
      link.addEventListener('click', function () {
        if (isMobile()) {
          closeAll();
        }
      });
    });

    if (secondarySidebar) {
      const tocLinks = secondarySidebar.querySelectorAll('a.nav-link');
      tocLinks.forEach(function (link) {
        link.addEventListener('click', function () {
          if (window.innerWidth < 1200) {
            closeAll();
          }
        });
      });
    }

    // 8. Close on Escape key
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        closeAll();
      }
    });

    // 9. Reset state on window resize across breakpoint
    window.addEventListener('resize', function () {
      if (!isMobile() && primarySidebar.classList.contains('mobile-show')) {
        closeAll();
      }
    });

    console.log('[MobileNav] Custom mobile sidebar drawer initialized successfully.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMobileNav);
  } else {
    initMobileNav();
  }
})();
