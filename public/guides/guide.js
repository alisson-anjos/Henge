const dialog = document.querySelector('#image-viewer');
for (const link of document.querySelectorAll('a.zoom')) {
  link.addEventListener('click', event => {
    if (!dialog?.showModal || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    const image = link.querySelector('img');
    dialog.querySelector('img').src = link.href;
    dialog.querySelector('img').alt = image.alt;
    dialog.querySelector('figcaption').textContent = image.alt;
    dialog.showModal();
  });
}
dialog?.querySelector('.close-viewer').addEventListener('click', () => dialog.close());
dialog?.addEventListener('click', event => {if (event.target === dialog) dialog.close();});
for (const button of document.querySelectorAll('[data-copy]')) {
  button.addEventListener('click', async () => {
    const text = document.getElementById(button.dataset.copy)?.textContent || '';
    try {
      await navigator.clipboard.writeText(text);
      document.getElementById('copy-status').textContent = 'Exemplo copiado.';
      button.textContent = 'Copiado ✓';
      setTimeout(() => {button.textContent = 'Copiar exemplo';}, 2000);
    } catch {
      const range = document.createRange();range.selectNodeContents(document.getElementById(button.dataset.copy));
      const selection = window.getSelection();selection.removeAllRanges();selection.addRange(range);
      document.getElementById('copy-status').textContent = 'Selecione e copie o texto com Ctrl+C.';
    }
  });
}
document.querySelector('[data-print]')?.addEventListener('click', () => window.print());
if ('IntersectionObserver' in window) {
  const links = [...document.querySelectorAll('aside nav a')];
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) if (entry.isIntersecting) {
      for (const link of links) {if (link.hash === '#' + entry.target.id) link.setAttribute('aria-current', 'location');else link.removeAttribute('aria-current');}
    }
  }, {rootMargin: '-10% 0px -65% 0px'});
  for (const section of document.querySelectorAll('main section[id]')) observer.observe(section);
}
