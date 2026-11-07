document.addEventListener('DOMContentLoaded', () => {
  // Code Tab Switching
  const tabs = document.querySelectorAll('.code-tab-btn');
  const panels = document.querySelectorAll('.code-panel-item');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.style.display = 'none');

      tab.classList.add('active');
      const targetId = tab.dataset.target;
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) {
        targetPanel.style.display = 'block';
      }
    });
  });

  // Copy Code to Clipboard
  const copyButtons = document.querySelectorAll('.code-copy-btn');
  copyButtons.forEach(btn => {
    btn.addEventListener('click', async () => {
      const panel = btn.closest('.code-content-panel');
      const codeEl = panel.querySelector('code') || panel.querySelector('pre');
      if (!codeEl) return;

      const text = codeEl.innerText.trim();
      try {
        await navigator.clipboard.writeText(text);
        const originalText = btn.textContent;
        btn.textContent = 'COPIED ✓';
        btn.style.background = '#E60000';
        btn.style.color = '#FFFFFF';
        setTimeout(() => {
          btn.textContent = originalText;
          btn.style.background = '';
          btn.style.color = '';
        }, 2000);
      } catch (err) {
        console.error('Failed to copy code: ', err);
      }
    });
  });

  // Navigation Scroll Spy
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-links a');

  window.addEventListener('scroll', () => {
    let current = '';
    const scrollY = window.pageYOffset;

    sections.forEach(section => {
      const sectionTop = section.offsetTop - 120;
      const sectionHeight = section.offsetHeight;
      if (scrollY >= sectionTop && scrollY < sectionTop + sectionHeight) {
        current = section.getAttribute('id');
      }
    });

    navLinks.forEach(link => {
      link.classList.remove('active');
      if (link.getAttribute('href') === `#${current}`) {
        link.classList.add('active');
      }
    });
  });
});
