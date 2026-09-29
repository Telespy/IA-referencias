/**
 * Brain Format — Frontend Application Logic
 * Manipulação de UI, chamadas assíncronas para a API FastAPI e exportações
 */

// ==========================================
// Gerenciamento de Tema (Dark / Light)
// ==========================================
const themeToggle = document.getElementById('themeToggle');
const htmlEl = document.documentElement;

function initTheme() {
  const savedTheme = localStorage.getItem('brain_format_theme') || 'dark';
  htmlEl.setAttribute('data-theme', savedTheme);
}

themeToggle.addEventListener('click', () => {
  const currentTheme = htmlEl.getAttribute('data-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  htmlEl.setAttribute('data-theme', newTheme);
  localStorage.setItem('brain_format_theme', newTheme);
});

initTheme();

// ==========================================
// Exemplos Demonstrativos
// ==========================================
const SAMPLE_REFERENCES = `WOODWARD, Kathryn. Identidade e diferença: uma introdução teórica e conceitual. In: SILVA, Tomaz Tadeu da (org.). Identidade e diferença: a perspectiva dos estudos culturais. Petrópolis: Vozes, 2000. p. 7-72.
CARNEIRO, Aparecida Sueli. A construção do outro como não-ser como fundamento do ser. 2005. Tese (Doutorado) – Universidade de São Paulo, São Paulo, 2005.
SAVIANI, Dermeval. O choque teórico da politecnia. Trabalho, Educação e Saúde, Rio de Janeiro, v. 1, n. 1, p. 131-152, 2003.
BRASIL. Lei nº 11.892, de 29 de dezembro de 2008. Institui a Rede Federal de Educação Profissional. Brasília, DF: Presidência da República, 2008.
BAUMAN, Zygmunt. Modernidade líquida. Rio de Janeiro: Jorge Zahar Ed.`;

const referenceInput = document.getElementById('referenceInput');
const lineCount = document.getElementById('lineCount');
const btnExample = document.getElementById('btnExample');
const btnClear = document.getElementById('btnClear');
const btnFormat = document.getElementById('btnFormat');

const loadingState = document.getElementById('loadingState');
const errorBanner = document.getElementById('errorBanner');
const errorMessage = document.getElementById('errorMessage');
const resultsSection = document.getElementById('resultsSection');
const resultsCount = document.getElementById('resultsCount');

// Botões de Download
const btnDownloadComp = document.getElementById('btnDownloadComp');
const btnDownloadABNT = document.getElementById('btnDownloadABNT');
const btnDownloadAPA = document.getElementById('btnDownloadAPA');

// Botões de Cópia Global
const btnCopyAllABNT = document.getElementById('btnCopyAllABNT');
const btnCopyAllAPA = document.getElementById('btnCopyAllAPA');

// Listas de Cartões
const compList = document.getElementById('compList');
const abntList = document.getElementById('abntList');
const apaList = document.getElementById('apaList');

// Badges das Abas
const badgeComp = document.getElementById('badgeComp');
const badgeABNT = document.getElementById('badgeABNT');
const badgeAPA = document.getElementById('badgeAPA');

// Variáveis de Estado
let currentData = null;

// ==========================================
// Contagem de Linhas
// ==========================================
function updateLineCounter() {
  const text = referenceInput.value;
  const lines = text.split('\n').filter(l => l.trim().length > 0);
  lineCount.textContent = `${lines.length} ${lines.length === 1 ? 'referência' : 'referências'}`;
}

referenceInput.addEventListener('input', updateLineCounter);

// Carregar Exemplos
btnExample.addEventListener('click', () => {
  referenceInput.value = SAMPLE_REFERENCES;
  updateLineCounter();
  referenceInput.focus();
});

// Limpar Campo
btnClear.addEventListener('click', () => {
  referenceInput.value = '';
  updateLineCounter();
  resultsSection.classList.add('hidden');
  errorBanner.classList.add('hidden');
  referenceInput.focus();
});

// Atalho Ctrl + Enter para formatar
referenceInput.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault();
    btnFormat.click();
  }
});

// ==========================================
// Alternância de Abas
// ==========================================
const tabButtons = document.querySelectorAll('.tab-btn');
const tabPanes = document.querySelectorAll('.tab-pane');

tabButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    tabButtons.forEach(b => b.classList.remove('active'));
    tabPanes.forEach(p => p.classList.remove('active'));

    btn.classList.add('active');
    const targetId = btn.getAttribute('data-tab');
    document.getElementById(targetId).classList.add('active');
  });
});

// ==========================================
// Renderizador Seguro de Markdown Básico
// ==========================================
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function correctionValue(value) {
  if (value === null) return 'ausente na fonte consultada';
  if (Array.isArray(value) && value.every(author => author && typeof author === 'object')) {
    return value.map(author => [author.family, author.given].filter(Boolean).join(', ')).join('; ');
  }
  return String(value ?? '');
}

function issueMessage(issue) {
  return [issue.message, issue.resolution].filter(Boolean).join(' ');
}

function renderMarkdown(md) {
  if (!md) return '';
  // Escapa caracteres HTML
  let html = escapeHtml(md);

  // Converte [texto](link)
  html = html.replace(/\[([^\[\]\n]*)\]\((https?:\/\/[^\s<>]*?)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color: var(--primary); text-decoration: underline;">$1</a>');

  // Converte negrito **texto**
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // Converte itálico *texto*
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

  return html;
}

// ==========================================
// Toasts de Notificação
// ==========================================
function showToast(message) {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5">
      <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
    <span>${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3000);
}

// ==========================================
// Cópia para Área de Transferência
// ==========================================
async function copyToClipboard(text, successMsg = 'Copiado para a área de transferência!') {
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMsg);
  } catch (err) {
    // Fallback para navegadores sem permissão de clipboard direta
    const textArea = document.createElement('textarea');
    textArea.value = text;
    document.body.appendChild(textArea);
    textArea.select();
    document.execCommand('copy');
    textArea.remove();
    showToast(successMsg);
  }
}

// ==========================================
// Download de Arquivos Markdown (.md)
// ==========================================
function downloadMarkdownFile(filename, content) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  showToast(`Download de ${filename} concluído!`);
}

// ==========================================
// Envio e Processamento via API
// ==========================================
btnFormat.addEventListener('click', async () => {
  const text = referenceInput.value.trim();
  if (!text) {
    errorBanner.classList.remove('hidden');
    errorMessage.textContent = 'Por favor, insira pelo menos uma referência para formatar.';
    return;
  }

  errorBanner.classList.add('hidden');
  loadingState.classList.remove('hidden');
  resultsSection.classList.add('hidden');
  btnFormat.disabled = true;

  try {
    const response = await fetch('/api/format', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text })
    });

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || errData.error || `Erro HTTP ${response.status}`);
    }

    const data = await response.json();
    currentData = data;
    renderResults(data);
  } catch (err) {
    errorBanner.classList.remove('hidden');
    errorMessage.textContent = err.message || 'Falha ao conectar ao servidor de formatação.';
  } finally {
    loadingState.classList.add('hidden');
    btnFormat.disabled = false;
  }
});

// ==========================================
// Renderização Dinâmica dos Resultados
// ==========================================
function renderResults(data) {
  const results = data.results || [];
  resultsCount.textContent = `${results.length} ${results.length === 1 ? 'referência processada' : 'referências processadas'}`;

  badgeComp.textContent = results.length;
  badgeABNT.textContent = results.length;
  badgeAPA.textContent = results.length;

  compList.innerHTML = '';
  abntList.innerHTML = '';
  apaList.innerHTML = '';

  results.forEach((r, idx) => {
    const num = idx + 1;

    // --- 1. Aba Comparativo Lado a Lado ---
    const compCard = document.createElement('div');
    compCard.className = 'card-item';

    const statusText = r.approved ? 'Conferida nas fontes' : 'Revisão necessária';
    const candidates = (r.candidates || []).map(c => [
      c.title, correctionValue(c.authors || []), c.year,
      c.doi ? `DOI: ${c.doi}` : '', c.isbn ? `ISBN: ${c.isbn}` : '',
      c.catalog_url ? `Catálogo de edições: ${c.catalog_url}` : ''
    ].filter(Boolean).join(' | '));
    const reportText = (style) => [
      `[${statusText.toUpperCase()}]`, r[style],
      ...(r.issues || []).map(i => `Aviso${i.resolved ? ' (resolvido)' : ''}: ${issueMessage(i)}`),
      ...(r.sources || []).map(s => `Fonte: ${s.name} ${s.url}`),
      ...candidates.map(c => `Candidato: ${c}`)
    ].join('\n');
    let missingHtml = `<div class="missing-box"><strong>${statusText}</strong>`;
    missingHtml += `<ul class="missing-list">${(r.issues || []).map(i =>
      `<li>${escapeHtml(issueMessage(i))}${i.resolved ? ' (resolvido)' : ''}</li>`).join('')}</ul>`;
    if (r.corrections?.length) {
      missingHtml += `<ul class="missing-list">${r.corrections.map(c =>
        `<li>Alteração em ${escapeHtml(c.field)}: ${escapeHtml(correctionValue(c.before))} → ${escapeHtml(correctionValue(c.after))}</li>`).join('')}</ul>`;
    }
    missingHtml += (r.sources || []).map(s => `<div>Fonte: ${escapeHtml(s.name)} ${escapeHtml(s.url)}</div>`).join('');
    if (candidates.length) {
      missingHtml += `<ul class="missing-list">${candidates.map(c => `<li>Candidato: ${escapeHtml(c)}</li>`).join('')}</ul>`;
    }
    missingHtml += '</div>';
    if (r.missing_fields && r.missing_fields.length > 0) {
      missingHtml += `
        <div class="missing-box">
          <div class="missing-title">
            <span>⚠️</span>
            <span>Elementos não encontrados para compor esta referência:</span>
          </div>
          <ul class="missing-list">
            ${r.missing_fields.map(f => `<li>${escapeHtml(f)}</li>`).join('')}
          </ul>
        </div>
      `;
    }

    compCard.innerHTML = `
      <div class="card-header">
        <span class="card-index">#${num}</span>
        <span class="badge-type">🏷️ ${escapeHtml(r.item_type_label)}</span>
      </div>

      <!-- Versão Original (Antes da Correção) -->
      <div class="box-original">
        <div class="box-original-title">
          <span>📝</span>
          <span>Versão Original (Antes da Correção):</span>
        </div>
        <div class="box-original-text">${escapeHtml(r.raw)}</div>
      </div>

      <!-- Comparativo Colunas ABNT vs APA -->
      <div class="comp-grid">
        <div class="norm-box norm-box-abnt">
          <div class="norm-box-header">
            <span class="norm-box-label">ABNT (NBR 6023)</span>
            <button class="btn btn-sm btn-outline copy-btn" data-copy="${encodeURIComponent(reportText('abnt'))}">
              Copiar ABNT
            </button>
          </div>
          <div class="norm-box-content">${renderMarkdown(r.abnt)}</div>
        </div>

        <div class="norm-box norm-box-apa">
          <div class="norm-box-header">
            <span class="norm-box-label">APA (7ª Edição)</span>
            <button class="btn btn-sm btn-outline copy-btn" data-copy="${encodeURIComponent(reportText('apa'))}">
              Copiar APA
            </button>
          </div>
          <div class="norm-box-content">${renderMarkdown(r.apa)}</div>
        </div>
      </div>

      ${missingHtml}
    `;
    compList.appendChild(compCard);

    // --- 2. Aba ABNT ---
    const abntCard = document.createElement('div');
    abntCard.className = 'card-item';
    abntCard.innerHTML = `
      <div class="card-header">
        <span class="badge-type">🏷️ ${escapeHtml(r.item_type_label)}</span>
        <button class="btn btn-sm btn-outline copy-btn" data-copy="${encodeURIComponent(reportText('abnt'))}">
          Copiar ABNT
        </button>
      </div>
      <div class="norm-box-content" style="font-size: 0.96rem;">${renderMarkdown(r.abnt)}</div>
      
      <button class="expander-toggle">
        <span>📝</span>
        <span>Ver referência antes da correção</span>
      </button>
      <div class="expander-content hidden">${escapeHtml(r.raw)}</div>

      ${missingHtml}
    `;
    abntList.appendChild(abntCard);

    // --- 3. Aba APA ---
    const apaCard = document.createElement('div');
    apaCard.className = 'card-item';
    apaCard.innerHTML = `
      <div class="card-header">
        <span class="badge-type">🏷️ ${escapeHtml(r.item_type_label)}</span>
        <button class="btn btn-sm btn-outline copy-btn" data-copy="${encodeURIComponent(reportText('apa'))}">
          Copiar APA
        </button>
      </div>
      <div class="norm-box-content" style="font-size: 0.96rem;">${renderMarkdown(r.apa)}</div>
      
      <button class="expander-toggle">
        <span>📝</span>
        <span>Ver referência antes da correção</span>
      </button>
      <div class="expander-content hidden">${escapeHtml(r.raw)}</div>

      ${missingHtml}
    `;
    apaList.appendChild(apaCard);
  });

  // Ativa listeners de cópia individual
  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const textToCopy = decodeURIComponent(btn.getAttribute('data-copy'));
      copyToClipboard(textToCopy);
    });
  });

  // Ativa listeners de alternância dos sanfonados (expander)
  document.querySelectorAll('.expander-toggle').forEach(toggle => {
    toggle.addEventListener('click', () => {
      const content = toggle.nextElementSibling;
      content.classList.toggle('hidden');
    });
  });

  resultsSection.classList.remove('hidden');
  resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ==========================================
// Ações Globais de Cópia e Download
// ==========================================
btnCopyAllABNT.addEventListener('click', () => {
  if (currentData && currentData.abnt_full) {
    copyToClipboard(currentData.abnt_full, 'Lista ABNT completa copiada!');
  }
});

btnCopyAllAPA.addEventListener('click', () => {
  if (currentData && currentData.apa_full) {
    copyToClipboard(currentData.apa_full, 'Lista APA completa copiada!');
  }
});

btnDownloadComp.addEventListener('click', () => {
  if (currentData && currentData.comp_full) {
    downloadMarkdownFile('referencias_comparativo.md', currentData.comp_full);
  }
});

btnDownloadABNT.addEventListener('click', () => {
  if (currentData && currentData.abnt_full) {
    downloadMarkdownFile('referencias_ABNT.md', currentData.abnt_full);
  }
});

btnDownloadAPA.addEventListener('click', () => {
  if (currentData && currentData.apa_full) {
    downloadMarkdownFile('referencias_APA.md', currentData.apa_full);
  }
});

// ==========================================
// Healthcheck Inicial
// ==========================================
async function checkApiHealth() {
  try {
    const res = await fetch('/api/health');
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    if (res.ok) {
      statusDot.style.background = '#10b981';
      statusDot.style.boxShadow = '0 0 8px #10b981';
      statusText.textContent = 'Online';
    } else {
      statusDot.style.background = '#f59e0b';
      statusText.textContent = 'Alerta';
    }
  } catch (e) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    if (statusDot && statusText) {
      statusDot.style.background = '#ef4444';
      statusText.textContent = 'Offline';
    }
  }
}

checkApiHealth();
