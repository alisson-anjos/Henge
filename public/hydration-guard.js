// Some browser extensions annotate SSR elements before React hydrates.
// Remove only the observed extension markers; preserve all application attributes.
(() => {
  const injected = name => name === 'bis_skin_checked' || name === 'bis_register' || /^__processed_[a-f0-9-]+__$/i.test(name);
  const clean = node => {
    if (!(node instanceof Element)) return;
    for (const name of node.getAttributeNames()) {
      if (injected(name)) node.removeAttribute(name);
    }
  };
  const subtree = node => {
    clean(node);
    if (node.querySelectorAll) node.querySelectorAll('*').forEach(clean);
  };
  const observer = new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes') {
        if (injected(record.attributeName)) clean(record.target);
      } else record.addedNodes.forEach(subtree);
    }
  });
  observer.observe(document.documentElement, {subtree:true, childList:true, attributes:true});
  subtree(document.documentElement);
  // Only guard the initial hydration period, not normal studio interactions.
  const deadline = setTimeout(() => observer.disconnect(), 30000);
  window.addEventListener('pagehide', () => {observer.disconnect();clearTimeout(deadline);}, {once:true});
})();

