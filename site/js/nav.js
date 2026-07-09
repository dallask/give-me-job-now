// give-me-job static site — vanilla-JS mobile nav toggle. No framework, no build step.
// Loaded unmodified by every page (index.html, docs.html, about.html, contact.html).
document.addEventListener('DOMContentLoaded', function () {
  var toggle = document.getElementById('nav-toggle');
  var menu = document.getElementById('nav-menu');

  if (!toggle || !menu) {
    return;
  }

  function closeMenu() {
    menu.classList.add('hidden');
    toggle.setAttribute('aria-expanded', 'false');
  }

  function openMenu() {
    menu.classList.remove('hidden');
    toggle.setAttribute('aria-expanded', 'true');
  }

  toggle.addEventListener('click', function () {
    var isHidden = menu.classList.contains('hidden');
    if (isHidden) {
      openMenu();
    } else {
      closeMenu();
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

  function collapseDocsPanel() {
    docsToggle.setAttribute('aria-expanded', 'false');
    docsPanel.classList.add('hidden');
    if (chevron) {
      chevron.classList.remove('rotate-180');
    }
  }

  function expandDocsPanel() {
    docsToggle.setAttribute('aria-expanded', 'true');
    docsPanel.classList.remove('hidden');
    if (chevron) {
      chevron.classList.add('rotate-180');
    }
  }

  docsToggle.addEventListener('click', function () {
    var isHidden = docsPanel.classList.contains('hidden');
    if (isHidden) {
      expandDocsPanel();
    } else {
      collapseDocsPanel();
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
      backToTop.classList.remove('opacity-0', 'pointer-events-none');
      backToTop.classList.add('opacity-100', 'pointer-events-auto');
    } else {
      backToTop.classList.add('opacity-0', 'pointer-events-none');
      backToTop.classList.remove('opacity-100', 'pointer-events-auto');
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
        'absolute top-2 right-2 inline-flex items-center justify-center rounded-md border border-gray-700 bg-gray-800 p-1.5 text-gray-300 hover:bg-gray-700 hover:text-gray-100 transition-colors';
      button.setAttribute('aria-label', 'Copy code to clipboard');
      button.innerHTML = CLIPBOARD_ICON;

      var resetTimer = null;

      button.addEventListener('click', function () {
        navigator.clipboard.writeText(codeEl.textContent)
          .then(function () {
            button.innerHTML = CHECK_ICON;
            if (resetTimer) {
              clearTimeout(resetTimer);
            }
            resetTimer = setTimeout(function () {
              button.innerHTML = CLIPBOARD_ICON;
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
