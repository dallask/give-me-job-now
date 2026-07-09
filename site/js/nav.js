// give-me-job static site — vanilla-JS mobile nav toggle. No framework, no build step.
// Loaded unmodified by every page (index.html, docs.html, about.html, contact.html).
// Shared transition duration (ms) for the menu-open/collapse class pairing below —
// must match the CSS `transition: max-height 250ms ease, ...` duration in style.css.
var MENU_TRANSITION_MS = 250;

document.addEventListener('DOMContentLoaded', function () {
  var toggle = document.getElementById('nav-toggle');
  var menu = document.getElementById('nav-menu');

  if (!toggle || !menu) {
    return;
  }

  var closeTimer = null;

  function closeMenu() {
    if (closeTimer) {
      clearTimeout(closeTimer);
    }
    menu.classList.remove('menu-open');
    toggle.setAttribute('aria-expanded', 'false');
    closeTimer = setTimeout(function () {
      menu.classList.add('hidden');
    }, MENU_TRANSITION_MS);
  }

  function openMenu() {
    if (closeTimer) {
      clearTimeout(closeTimer);
      closeTimer = null;
    }
    menu.classList.remove('hidden');
    // Force layout so the browser registers the collapsed state before we flip to
    // menu-open, otherwise the transition can be skipped (both class changes in one frame).
    void menu.offsetHeight;
    menu.classList.add('menu-open');
    toggle.setAttribute('aria-expanded', 'true');
  }

  toggle.addEventListener('click', function () {
    var isOpen = menu.classList.contains('menu-open');
    if (isOpen) {
      closeMenu();
    } else {
      openMenu();
    }
  });

  // Close the mobile menu after navigating so the next page doesn't load with it open.
  var links = menu.querySelectorAll('a');
  for (var i = 0; i < links.length; i++) {
    links[i].addEventListener('click', closeMenu);
  }
});

// Docs sidebar mobile toggle (docs.html only) — guarded no-op on pages without these elements.
document.addEventListener('DOMContentLoaded', function () {
  var docsToggle = document.getElementById('docs-mobile-toggle');
  var docsPanel = document.getElementById('docs-mobile-panel');

  if (!docsToggle || !docsPanel) {
    return;
  }

  var chevron = docsToggle.querySelector('svg');
  var docsCloseTimer = null;

  function collapseDocsPanel() {
    if (docsCloseTimer) {
      clearTimeout(docsCloseTimer);
    }
    docsToggle.setAttribute('aria-expanded', 'false');
    docsPanel.classList.remove('menu-open');
    if (chevron) {
      chevron.classList.remove('rotate-180');
    }
    docsCloseTimer = setTimeout(function () {
      docsPanel.classList.add('hidden');
    }, MENU_TRANSITION_MS);
  }

  function expandDocsPanel() {
    if (docsCloseTimer) {
      clearTimeout(docsCloseTimer);
      docsCloseTimer = null;
    }
    docsToggle.setAttribute('aria-expanded', 'true');
    docsPanel.classList.remove('hidden');
    // Force layout so the transition plays from the collapsed state.
    void docsPanel.offsetHeight;
    docsPanel.classList.add('menu-open');
    if (chevron) {
      chevron.classList.add('rotate-180');
    }
  }

  docsToggle.addEventListener('click', function () {
    var isOpen = docsPanel.classList.contains('menu-open');
    if (isOpen) {
      collapseDocsPanel();
    } else {
      expandDocsPanel();
    }
  });

  // Collapse (but don't preventDefault) on link click so the native #section anchor jump proceeds.
  var docsLinks = docsPanel.querySelectorAll('a');
  for (var j = 0; j < docsLinks.length; j++) {
    docsLinks[j].addEventListener('click', collapseDocsPanel);
  }
});

// Site-wide back-to-top button — unconditional, runs identically on all 4 pages.
document.addEventListener('DOMContentLoaded', function () {
  var backToTop = document.getElementById('back-to-top');

  if (!backToTop) {
    return;
  }

  var ticking = false;

  function updateBackToTop() {
    if (window.scrollY > window.innerHeight) {
      backToTop.classList.remove('opacity-0', 'pointer-events-none', 'translate-y-2');
      backToTop.classList.add('opacity-100', 'pointer-events-auto', 'translate-y-0');
    } else {
      backToTop.classList.add('opacity-0', 'pointer-events-none', 'translate-y-2');
      backToTop.classList.remove('opacity-100', 'pointer-events-auto', 'translate-y-0');
    }
  }

  window.addEventListener('scroll', function () {
    if (!ticking) {
      window.requestAnimationFrame(function () {
        updateBackToTop();
        ticking = false;
      });
      ticking = true;
    }
  });

  // Correct initial state in case the page loads already scrolled (deep-link/back-navigation).
  updateBackToTop();

  backToTop.addEventListener('click', function () {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
});

// Copy-to-clipboard buttons for fenced code blocks — guarded no-op on pages with
// zero <pre><code> blocks (contact.html, index.html, about.html).
document.addEventListener('DOMContentLoaded', function () {
  var codeBlocks = document.querySelectorAll('pre code');

  if (!codeBlocks || codeBlocks.length === 0) {
    return;
  }

  var CLIPBOARD_ICON =
    '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
  var CHECK_ICON =
    '<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';

  for (var i = 0; i < codeBlocks.length; i++) {
    (function (codeEl) {
      var preEl = codeEl.parentElement;
      if (!preEl) {
        return;
      }

      var wrapper = preEl.parentElement;
      if (!wrapper || !wrapper.classList.contains('relative')) {
        return;
      }

      var button = document.createElement('button');
      button.type = 'button';
      button.className =
        'absolute top-2 right-2 inline-flex items-center justify-center rounded-md border border-gray-700 bg-gray-800 p-1.5 text-gray-300 hover:bg-gray-700 hover:text-gray-100 transition-colors icon-swap-fade';
      button.setAttribute('aria-label', 'Copy code to clipboard');
      button.setAttribute('title', 'Copy to clipboard');
      button.setAttribute('data-tooltip', 'Copy to clipboard');
      button.innerHTML = CLIPBOARD_ICON;

      var resetTimer = null;
      var ICON_SWAP_FADE_MS = 150;

      // Swap the button's innerHTML inside a brief opacity fade-out/fade-in so the
      // icon<->checkmark change reads as a soft cross-fade instead of an instant pop.
      function swapIconWithFade(nextIconHtml) {
        button.style.opacity = '0';
        setTimeout(function () {
          button.innerHTML = nextIconHtml;
          button.style.opacity = '1';
        }, ICON_SWAP_FADE_MS);
      }

      button.addEventListener('click', function () {
        navigator.clipboard.writeText(codeEl.textContent)
          .then(function () {
            swapIconWithFade(CHECK_ICON);
            if (resetTimer) {
              clearTimeout(resetTimer);
            }
            resetTimer = setTimeout(function () {
              swapIconWithFade(CLIPBOARD_ICON);
            }, 1500);
          })
          .catch(function () {
            // Clipboard permission denied or unavailable — leave the default icon, no throw.
          });
      });

      wrapper.appendChild(button);
    })(codeBlocks[i]);
  }
});

// Shared scroll-state listener: drives BOTH the header hide/show AND (on docs.html only)
// the mobile sidebar-strip's top offset from ONE computed direction+position state, so the
// two toggles never fire from independently-drifting listeners.
document.addEventListener('DOMContentLoaded', function () {
  var header = document.querySelector('header');

  if (!header) {
    return;
  }

  // docs.html-only elements — safely undefined (no-op) on index/about/contact.html.
  var docsStripWrapper = document.querySelector('#docs-mobile-nav .sticky');
  var docsToggle = document.getElementById('docs-mobile-toggle');

  var SCROLL_DELTA_THRESHOLD = 8;
  var HEADER_ALWAYS_VISIBLE_THRESHOLD = 64;

  var lastScrollY = window.scrollY;
  var headerHidden = false;
  var ticking = false;

  function applyVisibility(hidden) {
    if (hidden === headerHidden) {
      return;
    }
    headerHidden = hidden;

    if (hidden) {
      header.classList.add('-translate-y-full');
    } else {
      header.classList.remove('-translate-y-full');
    }

    // Docs mobile sidebar-strip offset stays in lockstep with the same decision.
    if (docsStripWrapper) {
      if (hidden) {
        docsStripWrapper.classList.add('docs-strip-header-hidden');
      } else {
        docsStripWrapper.classList.remove('docs-strip-header-hidden');
      }
    }
    if (docsToggle) {
      if (hidden) {
        docsToggle.classList.add('docs-strip-header-hidden');
      } else {
        docsToggle.classList.remove('docs-strip-header-hidden');
      }
    }
  }

  function updateScrollState() {
    var currentScrollY = window.scrollY;
    var delta = currentScrollY - lastScrollY;

    if (currentScrollY <= HEADER_ALWAYS_VISIBLE_THRESHOLD) {
      applyVisibility(false);
      lastScrollY = currentScrollY;
      return;
    }

    if (Math.abs(delta) < SCROLL_DELTA_THRESHOLD) {
      // Ignore jitter — do not reassign lastScrollY so tiny back-and-forth wiggles
      // cannot slowly drift the reference point away from the true position.
      return;
    }

    if (delta > 0) {
      applyVisibility(true);
    } else {
      applyVisibility(false);
    }

    lastScrollY = currentScrollY;
  }

  window.addEventListener('scroll', function () {
    if (!ticking) {
      window.requestAnimationFrame(function () {
        updateScrollState();
        ticking = false;
      });
      ticking = true;
    }
  });

  // Correct initial state in case the page loads already scrolled (deep-link/back-navigation).
  updateScrollState();
});

// docs.html scroll-spy: IntersectionObserver-driven active-section tracking for both the
// desktop always-visible sidebar list and the mobile collapsed-strip label.
document.addEventListener('DOMContentLoaded', function () {
  var docsToggle = document.getElementById('docs-mobile-toggle');
  var docsPanel = document.getElementById('docs-mobile-panel');

  // docs.html-only feature — no-op on index/about/contact.html.
  if (!docsToggle || !docsPanel) {
    return;
  }

  if (typeof IntersectionObserver === 'undefined') {
    return;
  }

  var sections = document.querySelectorAll('section[id]');
  if (!sections || sections.length === 0) {
    return;
  }

  var desktopSidebar = document.querySelector('nav.docs-sidebar');
  var mobileCurrentLabel = document.getElementById('docs-mobile-current');

  // id -> { desktopLink, mobileLink, label }
  var sectionMap = {};

  for (var i = 0; i < sections.length; i++) {
    var id = sections[i].id;
    if (!id) {
      continue;
    }

    var desktopLink = desktopSidebar ? desktopSidebar.querySelector('a[href="#' + id + '"]') : null;
    var mobileLink = docsPanel.querySelector('a[href="#' + id + '"]');
    var label = (desktopLink && desktopLink.textContent) || (mobileLink && mobileLink.textContent) || id;

    sectionMap[id] = {
      desktopLink: desktopLink,
      mobileLink: mobileLink,
      label: label
    };
  }

  var currentActiveId = null;

  function setActive(id) {
    if (!id || id === currentActiveId || !sectionMap[id]) {
      return;
    }
    currentActiveId = id;

    // Clear any prior active state from every desktop sidebar link.
    if (desktopSidebar) {
      var allDesktopLinks = desktopSidebar.querySelectorAll('a');
      for (var d = 0; d < allDesktopLinks.length; d++) {
        allDesktopLinks[d].classList.remove('menu-active');
      }
    }

    var entry = sectionMap[id];
    if (entry.desktopLink) {
      entry.desktopLink.classList.add('menu-active');
    }

    // Scroll-spy only updates the label text — it must not force the mobile panel open.
    if (mobileCurrentLabel) {
      mobileCurrentLabel.textContent = entry.label;
    }
  }

  function pickActiveFromRects() {
    var bestId = null;
    var bestTop = null;
    var fallbackId = null;
    var fallbackTop = null;

    for (var id in sectionMap) {
      if (!Object.prototype.hasOwnProperty.call(sectionMap, id)) {
        continue;
      }
      var section = document.getElementById(id);
      if (!section) {
        continue;
      }
      var rect = section.getBoundingClientRect();

      if (rect.top >= 0) {
        if (bestTop === null || rect.top < bestTop) {
          bestTop = rect.top;
          bestId = id;
        }
      } else {
        // Track the least-negative (topmost-above-viewport) section as a fallback.
        if (fallbackTop === null || rect.top > fallbackTop) {
          fallbackTop = rect.top;
          fallbackId = id;
        }
      }
    }

    return bestId || fallbackId;
  }

  var observer = new IntersectionObserver(function () {
    var activeId = pickActiveFromRects();
    setActive(activeId);
  }, {
    root: null,
    rootMargin: '-64px 0px -70% 0px',
    threshold: 0
  });

  for (var s = 0; s < sections.length; s++) {
    observer.observe(sections[s]);
  }

  // Trigger the initial state manually in case the page loads already scrolled to a
  // mid-page anchor, rather than waiting for the first intersection-change callback.
  setActive(pickActiveFromRects());
});

// Tooltipster init — defensively guarded so a slow/failed CDN load degrades to plain
// title-less icons instead of throwing and breaking the other guarded blocks above.
document.addEventListener('DOMContentLoaded', function () {
  if (typeof jQuery === 'undefined' || typeof jQuery.fn.tooltipster === 'undefined') {
    return;
  }

  jQuery('[data-tooltip]').tooltipster({
    theme: 'tooltipster-sidetip',
    animation: 'fade',
    delay: 100,
    side: 'top'
  });
});
