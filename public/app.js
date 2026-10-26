const $ = id => document.getElementById(id);
const referenceInput = $('referenceInput');
const lineCount = $('lineCount');
const btnFormat = $('btnFormat');
const resultsSection = $('resultsSection');
const loadingState = $('loadingState');
const errorBanner = $('errorBanner');
const errorMessage = $('errorMessage');
const compList = $('compList');
const abntList = $('abntList');
const apaList = $('apaList');
let currentData = null;

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function safeUrl(url) {
  try {
    const u = new URL(url);
    return ['http:','https:'].includes(u.protocol) ? u.href : '';
  } catch { return ''; }
}

function renderMarkdown(md) {
  if (!md) return '';
  let html = escapeHtml(md);
  html = html.replace(/\[([^\[\]\n]*)\]\((https?:\/\/[^\s<>"']+)\)/g, (_, label, url) => {
    const safe = safeUrl(url);
    return safe ? '<a href="' + escapeHtml(safe) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>' : label;
  });
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  return html;
}

function correctionValue(value) {
  if (value === null) return 'ausente na fonte consultada';
  if (Array.isArray(value) && value.every(a => a && typeof a === 'object')) {
    return value.map(a => [a.family, a.given].filter(Boolean).join(', ')).join('; ');
  }
  return String(value ?? '');
}

function issueMessage(issue) {
  return [issue?.message, issue?.resolution].filter(Boolean).join(' ');
}

function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  $('toastContainer').appendChild(toast);
  setTimeout(() => toast.remove(), 2400);
}

async function copyToClipboard(text, message='Copiado para a área de transferência') {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
  }
  showToast(message);
}

function downloadFile(filename, content) {
  const blob = new Blob([content], {type:'text/markdown;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

function currentMode() {
  return document.querySelector('input[name="inputMode"]:checked')?.value || 'lines';
}

const BATCH_SIZE = 50;
const docFile = $('docFile');
const docInfo = $('docInfo');
const batchPicker = $('batchPicker');
const batchSelect = $('batchSelect');

function referenceItems() {
  const text = referenceInput.value.trim();
  if (!text) return [];
  return currentMode() === 'blocks'
    ? text.split(/\n\s*\n/).map(x => x.trim()).filter(Boolean)
    : text.split(/\n/).map(x => x.trim()).filter(Boolean);
}

function countReferences() {
  return referenceItems().length;
}

function updateBatchPicker(n) {
  const batches = Math.ceil(n / BATCH_SIZE);
  batchPicker.classList.toggle('hidden', batches <= 1);
  if (batches <= 1) return;
  const selected = batchSelect.value;
  batchSelect.innerHTML = Array.from({length: batches}, (_, k) => {
    const first = k * BATCH_SIZE + 1, last = Math.min(n, (k + 1) * BATCH_SIZE);
    return '<option value="' + k + '">Lote ' + (k + 1) + ': itens ' + first + '–' + last + '</option>';
  }).join('');
  if (selected && Number(selected) < batches) batchSelect.value = selected;
}

function updateCounter() {
  const n = countReferences();
  lineCount.textContent = n + ' ' + (n === 1 ? 'referência' : 'referências');
  updateBatchPicker(n);
}

function syncModeUI() {
  document.querySelectorAll('.mode-option').forEach(label => {
    label.classList.toggle('active', label.querySelector('input')?.checked);
  });
  updateCounter();
}

document.querySelectorAll('input[name="inputMode"]').forEach(el => el.addEventListener('change', syncModeUI));
referenceInput.addEventListener('input', updateCounter);

const SAMPLE = `AFP. Indústria da música está ameaçada por bandas geradas por IA: 'desafio incomparável'. O Globo, 30 jul. 2025. Disponível em: https://oglobo.globo.com/cultura/musica/noticia/2025/07/30/industria-da-musica-esta-ameacada-por-bandas-geradas-por-ia-desafio-incomparavel.ghtml. Acesso em: 16 ago. 2026.
WIPO. O que é propriedade intelectual? WIPO, 2021.
SAVIANI, Dermeval. O choque teórico da politecnia. Trabalho, Educação e Saúde, Rio de Janeiro, v. 1, n. 1, p. 131-152, 2003.`;

$('btnExample').addEventListener('click', () => { referenceInput.value = SAMPLE; updateCounter(); referenceInput.focus(); });
$('btnClear').addEventListener('click', () => { referenceInput.value=''; updateCounter(); resultsSection.classList.add('hidden'); errorBanner.classList.add('hidden'); referenceInput.focus(); });
referenceInput.addEventListener('keydown', e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); btnFormat.click(); } });

const htmlEl = document.documentElement;
function initTheme() { htmlEl.dataset.theme = localStorage.getItem('ref_theme') || 'light'; }
$('themeToggle').addEventListener('click', () => {
  htmlEl.dataset.theme = htmlEl.dataset.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('ref_theme', htmlEl.dataset.theme);
});
initTheme();

document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => {
  document.querySelectorAll('.tab-btn').forEach(x => x.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(x => x.classList.remove('active'));
  btn.classList.add('active'); $(btn.dataset.tab).classList.add('active');
}));

async function checkHealth() {
  const el = $('apiStatus');
  try {
    const r = await fetch('/api/health', {cache:'no-store'});
    if (!r.ok) throw new Error();
    el.className='api-status online'; el.querySelector('.status-text').textContent='Servidor online';
  } catch {
    el.className='api-status offline'; el.querySelector('.status-text').textContent='Servidor offline';
  }
}
checkHealth();

docFile.addEventListener('change', async () => {
  const file = docFile.files[0];
  if (!file) return;
  errorBanner.classList.add('hidden'); docInfo.textContent = 'Lendo ' + file.name + '…';
  const form = new FormData();
  form.append('file', file);
  try {
    const response = await fetch('/api/extract', {method:'POST', body:form});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Falha ao ler o documento.');
    referenceInput.value = data.referencias.map(x => x.texto).join('\n\n');
    document.querySelector('input[name="inputMode"][value="blocks"]').checked = true;
    syncModeUI();
    const c = data.citacoes;
    docInfo.textContent = data.total + ' entradas · ' + c.total + ' citações no texto · ' +
      c.sem_referencia.length + ' sem entrada · ' + c.referencias_sem_citacao.length + ' entradas sem citação. ' +
      (data.avisos || []).join(' ');
  } catch(err) {
    docInfo.textContent = '';
    errorMessage.textContent = err.message || 'Falha ao ler o documento.'; errorBanner.classList.remove('hidden');
  } finally { docFile.value = ''; }
});

btnFormat.addEventListener('click', async () => {
  const items = referenceItems();
  if (!items.length) { errorMessage.textContent='Insira pelo menos uma referência.'; errorBanner.classList.remove('hidden'); return; }
  let text = referenceInput.value.trim(), format = currentMode();
  if (items.length > BATCH_SIZE) {
    const batch = Number(batchSelect.value) || 0;
    text = items.slice(batch * BATCH_SIZE, (batch + 1) * BATCH_SIZE).join('\n\n');
    format = 'blocks';
  }
  errorBanner.classList.add('hidden'); resultsSection.classList.add('hidden'); loadingState.classList.remove('hidden'); btnFormat.disabled=true;
  try {
    const response = await fetch('/api/format', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text, online:$('onlineToggle').checked, input_format:format})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Falha ao processar o lote.');
    currentData=data; renderResults(data); resultsSection.classList.remove('hidden'); resultsSection.scrollIntoView({behavior:'smooth',block:'start'});
  } catch(err) {
    errorMessage.textContent=err.message || 'Falha ao conectar ao servidor.'; errorBanner.classList.remove('hidden');
  } finally { loadingState.classList.add('hidden'); btnFormat.disabled=false; }
});

function statusLabel(r) {
  return r.status === 'verified' ? 'Verificada' : r.status === 'error' ? 'Erro' : 'Revisão necessária';
}

function sourceHtml(s) {
  const url = safeUrl(s?.url || '');
  return '<div class="source-row"><strong>' + escapeHtml(s?.name || 'Fonte') + '</strong>' +
    (url ? ' · <a href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(url) + '</a>' : '') + '</div>';
}

function provenanceHtml(prov) {
  const entries = Object.entries(prov || {});
  if (!entries.length) return '<div class="source-row">Nenhuma proveniência registrada.</div>';
  return '<table class="provenance-table"><thead><tr><th>Campo</th><th>Origem</th><th>Verificado</th><th>Confiança</th></tr></thead><tbody>' +
    entries.map(([field,p]) => '<tr><td>' + escapeHtml(field) + '</td><td>' + escapeHtml(p?.source || 'entrada') + '</td><td>' + (p?.verified ? 'sim' : 'não') + '</td><td class="confidence">' + (typeof p?.confidence === 'number' ? Math.round(p.confidence*100)+'%' : '—') + '</td></tr>').join('') +
    '</tbody></table>';
}

function reportText(r, style) {
  const lines = ['[' + statusLabel(r).toUpperCase() + ']', r[style] || r.raw];
  (r.issues || []).forEach(i => lines.push('Aviso: ' + issueMessage(i)));
  (r.sources || []).forEach(s => lines.push('Fonte: ' + s.name + (s.url ? ' ' + s.url : '')));
  return lines.join('\n');
}

function detailsHtml(r) {
  const issues = r.issues || [];
  const corrections = r.corrections || [];
  const missing = r.missing_fields || [];
  const sourceBlock = (r.sources || []).map(sourceHtml).join('') || '<div class="source-row">Nenhuma fonte externa registrada.</div>';
  const listItems = [
    ...missing.map(x => 'Pendente: ' + x),
    ...issues.filter(x => x.severity !== 'info').map(issueMessage),
    ...corrections.map(c => 'Correção em ' + c.field + ': ' + correctionValue(c.before) + ' → ' + correctionValue(c.after))
  ];
  return '<div class="detail-grid">' +
    '<div class="detail-box"><h4>Revisão e correções</h4>' + (listItems.length ? '<ul class="detail-list">' + listItems.map(x => '<li>' + escapeHtml(x) + '</li>').join('') + '</ul>' : '<div class="source-row">Nenhuma pendência bloqueante.</div>') + '</div>' +
    '<div class="detail-box"><h4>Fontes consultadas</h4>' + sourceBlock + '</div>' +
    '</div><div class="detail-box" style="margin-top:10px"><h4>Proveniência por campo</h4>' + provenanceHtml(r.provenance) + '</div>';
}

function makeDetailedCard(r, idx) {
  const el=document.createElement('article'); el.className='reference-card';
  el.innerHTML='<div class="reference-head"><div class="ref-identity"><span class="index">#'+(idx+1)+'</span><span class="type-pill">'+escapeHtml(r.item_type_label || r.item_type)+'</span></div><span class="status-pill '+escapeHtml(r.status)+'">'+escapeHtml(statusLabel(r))+'</span></div>' +
    '<div class="reference-body"><div class="original-box"><span class="box-label">Entrada original</span><div class="original-text">'+escapeHtml(r.raw)+'</div></div>' +
    '<div class="norm-grid"><div class="norm-card abnt"><div class="norm-head"><strong>ABNT</strong><button class="button mini secondary copy-btn" data-copy="'+encodeURIComponent(reportText(r,'abnt'))+'">Copiar</button></div><div class="norm-text">'+renderMarkdown(r.abnt)+'</div></div>' +
    '<div class="norm-card apa"><div class="norm-head"><strong>APA</strong><button class="button mini secondary copy-btn" data-copy="'+encodeURIComponent(reportText(r,'apa'))+'">Copiar</button></div><div class="norm-text">'+renderMarkdown(r.apa)+'</div></div></div>' +
    detailsHtml(r) + '</div>';
  return el;
}

function makeSimpleCard(r, style) {
  const el=document.createElement('article'); el.className='simple-card';
  el.innerHTML='<div class="simple-head"><div><span class="type-pill">'+escapeHtml(r.item_type_label || r.item_type)+'</span> <span class="status-pill '+escapeHtml(r.status)+'">'+escapeHtml(statusLabel(r))+'</span></div><button class="button mini secondary copy-btn" data-copy="'+encodeURIComponent(reportText(r,style))+'">Copiar</button></div>' +
    '<div class="simple-text">'+renderMarkdown(r[style])+'</div><button class="expander-toggle" type="button">Ver original</button><div class="expander-content hidden">'+escapeHtml(r.raw)+'</div>';
  return el;
}

function bindDynamic() {
  document.querySelectorAll('.copy-btn').forEach(btn => btn.addEventListener('click', () => copyToClipboard(decodeURIComponent(btn.dataset.copy || ''))));
  document.querySelectorAll('.expander-toggle').forEach(btn => btn.addEventListener('click', () => btn.nextElementSibling?.classList.toggle('hidden')));
}

function renderResults(data) {
  const results=data.results || [];
  $('resultsCount').textContent=results.length+' '+(results.length===1?'referência processada':'referências processadas');
  const summary=data.summary || {};
  $('sumVerified').textContent=summary.verified || 0; $('sumReview').textContent=summary.needs_review || 0; $('sumError').textContent=summary.error || 0;
  $('badgeComp').textContent=results.length; $('badgeABNT').textContent=results.length; $('badgeAPA').textContent=results.length;
  compList.innerHTML=''; abntList.innerHTML=''; apaList.innerHTML='';
  results.forEach((r,i) => { compList.appendChild(makeDetailedCard(r,i)); abntList.appendChild(makeSimpleCard(r,'abnt')); apaList.appendChild(makeSimpleCard(r,'apa')); });
  bindDynamic();
  resultsSection.classList.remove('hidden');
}

$('btnCopyAllABNT').addEventListener('click', () => currentData && copyToClipboard(currentData.results.map(r=>r.abnt).join('\n\n'),'Lista ABNT copiada'));
$('btnCopyAllAPA').addEventListener('click', () => currentData && copyToClipboard(currentData.results.map(r=>r.apa).join('\n\n'),'Lista APA copiada'));
$('btnDownloadABNT').addEventListener('click', () => currentData && downloadFile('referencias_ABNT.md', currentData.abnt_full || ''));
$('btnDownloadAPA').addEventListener('click', () => currentData && downloadFile('referencias_APA.md', currentData.apa_full || ''));
$('btnDownloadComp').addEventListener('click', () => currentData && downloadFile('relatorio_referencias.md', currentData.comp_full || ''));

syncModeUI();
