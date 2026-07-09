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
