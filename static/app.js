/* ═══════════════════════════════════════════════════════════════
   ASTRA Mission Control Platform — app.js v2
   Shared utilities + page-specific logic
   ═══════════════════════════════════════════════════════════════ */

// ── Star Field ─────────────────────────────────────────────────────────────
(function initStarfield() {
  const canvas = document.getElementById('starfield');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  let stars = [];

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
    stars = Array.from({ length: 250 }, () => ({
      x:     Math.random() * canvas.width,
      y:     Math.random() * canvas.height,
      r:     Math.random() * 1.3 + 0.2,
      o:     Math.random() * 0.55 + 0.08,
      speed: Math.random() * 0.018 + 0.004,
      phase: Math.random() * Math.PI * 2,
    }));
  }

  function draw(t) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const s of stars) {
      const opacity = s.o * (0.65 + 0.35 * Math.sin(t * s.speed + s.phase));
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(200,220,255,${opacity})`;
      ctx.fill();
    }
    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  resize();
  requestAnimationFrame(draw);
})();


// ── Auth: Tab Toggle ────────────────────────────────────────────────────────
function showTab(name) {
  const loginForm    = document.getElementById('formLogin');
  const registerForm = document.getElementById('formRegister');
  const loginTab     = document.getElementById('tabLogin');
  const registerTab  = document.getElementById('tabRegister');
  if (!loginForm) return;

  if (name === 'login') {
    loginForm.classList.remove('hidden');
    registerForm.classList.add('hidden');
    loginTab.classList.add('active');
    registerTab.classList.remove('active');
  } else {
    loginForm.classList.add('hidden');
    registerForm.classList.remove('hidden');
    loginTab.classList.remove('active');
    registerTab.classList.add('active');
  }
}

function togglePw(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
  } else {
    input.type = 'password';
    btn.textContent = '👁';
  }
}


// ── Sidebar Collapse ────────────────────────────────────────────────────────
(function initSidebar() {
  const sidebar = document.getElementById('sidebar');
  const toggle  = document.getElementById('sidebarToggle');
  if (!sidebar || !toggle) return;

  const saved = localStorage.getItem('sidebarCollapsed');
  if (saved === 'true') sidebar.classList.add('collapsed');

  toggle.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
  });
})();


// ── Live Clock ──────────────────────────────────────────────────────────────
(function initClock() {
  const el = document.getElementById('topbarTime');
  if (!el) return;
  function tick() {
    el.textContent = new Date().toUTCString().slice(0, -4) + ' UTC';
  }
  tick();
  setInterval(tick, 1000);
})();


// ── Credentials Modal ────────────────────────────────────────────────────────
function openCredsModal() {
  const modal = document.getElementById('credsModal');
  if (modal) { modal.style.display = 'flex'; }
}

function closeCredsModal() {
  const modal = document.getElementById('credsModal');
  if (modal) { modal.style.display = 'none'; }
}

async function saveCredsModal() {
  const stUser  = document.getElementById('stUsername').value.trim();
  const stPass  = document.getElementById('stPassword').value;
  const errEl   = document.getElementById('credsError');
  const btn     = document.getElementById('credsSubmitBtn');
  const spinner = document.getElementById('credsSpinner');

  if (!stUser || !stPass) {
    errEl.textContent = 'Both username and password are required.';
    errEl.classList.remove('hidden');
    return;
  }

  errEl.classList.add('hidden');
  btn.disabled = true;
  spinner.classList.remove('hidden');

  try {
    const res  = await fetch('/api/spacetrack-creds', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ st_username: stUser, st_password: stPass }),
    });
    const data = await res.json();

    if (!res.ok) {
      errEl.textContent = data.error || 'Verification failed.';
      errEl.classList.remove('hidden');
      return;
    }

    showToast('Space-Track credentials saved! 🎉', 'success');
    closeCredsModal();
    // Refresh the page to update header status
    setTimeout(() => window.location.reload(), 800);
  } catch (e) {
    errEl.textContent = 'Network error: ' + e.message;
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    spinner.classList.add('hidden');
  }
}

// Close modal on overlay click
document.addEventListener('DOMContentLoaded', () => {
  const overlay = document.getElementById('credsModal');
  if (!overlay) return;
  overlay.addEventListener('click', (e) => {
    // Only close if clicking the backdrop (not the box itself)
    if (e.target === overlay) closeCredsModal();
  });
  // Enter key in creds inputs
  ['stUsername', 'stPassword'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') saveCredsModal(); });
  });
});


// ── Toast Notification System ────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const icons = { success: '✓', error: '✕', warning: '⚠', info: 'ℹ' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'all 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}


// ── Shared UI Utilities ──────────────────────────────────────────────────────
function show(el)           { if (el) el.classList.remove('hidden'); }
function hide(el)           { if (el) el.classList.add('hidden');    }
function showError(el, msg) { if (!el) return; el.textContent = '⚠ ' + msg; show(el); }

function chip(label, value) {
  return `${label}: <span class="chip">${value}</span>`;
}

function fmtNum(v, d = 4) {
  if (v === null || v === undefined) return '—';
  return Number(v).toFixed(d);
}

function fmtSci(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toExponential(3);
}

function fmtDate(iso) {
  if (!iso) return '—';
  return iso.replace('T', ' ').replace('Z', '');
}

function riskChip(level) {
  const cls = {
    CRITICAL: 'risk-critical', HIGH: 'risk-high',
    MEDIUM:   'risk-medium',   LOW:  'risk-low',
    UNKNOWN:  'risk-unknown',
  }[level] || 'risk-unknown';
  return `<span class="risk-chip ${cls}">${level}</span>`;
}

function elevBar(deg) {
  const pct = Math.min(100, Math.max(0, (deg / 90) * 100));
  const color = deg > 60 ? 'var(--teal)' : deg > 30 ? 'var(--cyan)' : 'var(--amber)';
  return `<div class="elev-bar-wrap">
    <span>${deg.toFixed(1)}°</span>
    <div class="elev-bar"><div class="elev-bar-fill" style="width:${pct}%;background:${color}"></div></div>
  </div>`;
}
