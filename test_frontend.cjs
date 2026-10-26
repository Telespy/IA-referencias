const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element() {
  return {
    innerHTML: '', textContent: '', value: '', style: {}, children: [], dataset: {},
    className: '', checked: false,
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {}, setAttribute() {}, getAttribute() { return ''; },
    appendChild(child) { this.children.push(child); return child; }, remove() {},
    scrollIntoView() {}, focus() {}, select() {},
    querySelector() { return element(); },
  };
}
const docEl = element();
const body = element();
const radio = element(); radio.value = 'lines'; radio.checked = true;
const context = vm.createContext({
  URL,
  Blob,
  navigator: { clipboard: { writeText: async () => {} } },
  document: {
    documentElement: docEl, body,
    getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    querySelector(selector) { if (selector.includes('input[name="inputMode"]')) return radio; return element(); },
    querySelectorAll() { return []; },
    createElement: element,
    execCommand() { return true; },
  },
  localStorage: { getItem() { return null; }, setItem() {} },
  fetch: async () => ({ ok: true, json: async () => ({status:'healthy'}) }),
  setTimeout() {},
  encodeURIComponent, decodeURIComponent,
});

vm.runInContext(fs.readFileSync('public/app.js', 'utf8'), context);

const attack = '<img src=x onerror="alert(1)">';
context.testResult = {
  raw: attack,
  item_type: 'book',
  item_type_label: attack,
  abnt: attack,
  apa: attack,
  status: 'needs_review',
  approved: false,
  identity_verified: false,
  issues: [{ message: attack, severity:'warning', resolution: attack + ' Resolucao comprovada' }],
  missing_fields: [attack],
  sources: [{name: attack, url:'https://example.org/source'}],
  provenance: {title:{source:attack,verified:false}},
  corrections: [{ field: 'authors', before: [{ family: attack, given: 'Maria' }], after: [{ family: 'Autor', given: 'Maria' }] }],
  candidates: [],
};

vm.runInContext('renderResults({results:[testResult], summary:{verified:0,needs_review:1,error:0}})', context);
for (const id of ['compList', 'abntList', 'apaList']) {
  const container = elements.get(id);
  assert(container.children.length === 1, id + ' should render one result');
  const markup = container.children[0].innerHTML;
  assert(!markup.includes('<img'), id + ' must escape user input');
  assert(markup.includes('&lt;img'), id + ' must show escaped original');
  assert(markup.includes('Revisão necessária'), id + ' must preserve review status');
}

assert.equal(vm.runInContext("correctionValue([{family:'Holanda',given:'Marcelo Alcantara'}])", context), 'Holanda, Marcelo Alcantara');
const rendered = vm.runInContext("renderMarkdown('[clique](javascript:alert(1))')", context);
assert(!rendered.includes('href="javascript:'));
const renderedHttp = vm.runInContext("renderMarkdown('[fonte](https://example.org/a)')", context);
assert(renderedHttp.includes('target="_blank"'));
console.log('Frontend: rendering, escaping, review status and safe links OK');
