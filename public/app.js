const healthLink = document.querySelector('a[href="/healthz"]');

healthLink?.addEventListener('click', () => {
  healthLink.textContent = 'Opening health check…';
});
