(() => {
  const menuButton = document.querySelector('.menu-button');
  const nav = document.querySelector('.site-nav');

  const closeMenu = () => {
    if (!menuButton || !nav) return;
    nav.classList.remove('is-open');
    menuButton.classList.remove('is-open');
    menuButton.setAttribute('aria-expanded', 'false');
  };

  if (menuButton && nav) {
    menuButton.addEventListener('click', () => {
      const opened = nav.classList.toggle('is-open');
      menuButton.classList.toggle('is-open', opened);
      menuButton.setAttribute('aria-expanded', String(opened));
    });
  }

  // In-page links: scroll to the section ourselves so they also work when the page is shown
  // inside a viewer (srcdoc/blob/iframe) where a bare "#id" would resolve against another URL.
  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener('click', (event) => {
      const id = decodeURIComponent(link.getAttribute('href').slice(1));
      const target = id ? document.getElementById(id) : null;
      closeMenu();
      if (!target) return;
      event.preventDefault();
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
      if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
      target.focus({ preventScroll: true });
    });
  });

  // Other links (https:, tel:) keep their default browser behaviour; just close the mobile menu.
  nav?.querySelectorAll('a:not([href^="#"])').forEach((link) => link.addEventListener('click', closeMenu));
})();
