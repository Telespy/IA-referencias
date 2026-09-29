const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const elements = new Map();
function element() {
  return {
    innerHTML: '', textContent: '', value: '', style: {}, children: [],
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener() {}, setAttribute() {}, getAttribute() { return ''; },
    appendChild(child) { this.children.push(child); }, remove() {},
    scrollIntoView() {}, focus() {},
  };
}
const context = vm.createContext({
  document: {
    documentElement: element(),
    getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
    querySelector() { return element(); }, querySelectorAll() { return []; },
    createElement: element,
  },
  localStorage: { getItem() {}, setItem() {} },
  fetch: async () => ({ ok: true }), setTimeout() {}, encodeURIComponent, decodeURIComponent,
});
vm.runInContext(fs.readFileSync('public/app.js', 'utf8'), context);
const attack = '<img src=x onerror="alert(1)">';
context.testResult = {
  raw: attack, item_type_label: attack, abnt: attack, apa: attack, approved: false,
  issues: [{ message: attack, resolved: true, resolution: attack + ' Resolucao comprovada' }], missing_fields: [attack], sources: [],
  corrections: [{ field: 'authors', before: [{ family: attack, given: 'Maria' }], after: [{ family: 'Autor', given: 'Maria' }] }],
  candidates: [{title: attack, authors: [{family: attack}], doi: '10.1234/test', catalog_url: attack}],
};
vm.runInContext('renderResults({results: [testResult]})', context);
for (const id of ['compList', 'abntList', 'apaList']) {
  const markup = elements.get(id).children[0].innerHTML;
  assert(!markup.includes('<img'), id + ' must escape user input');
  assert(markup.includes('&lt;img'), id + ' must display the original safely');
  assert(markup.includes('Revisão necessária'), id + ' must preserve review status');
  assert(markup.includes('Aviso'), id + ' copied report must include warnings');
  assert(markup.includes('Resolucao comprovada'), id + ' must retain the conflict resolution');
  assert(markup.includes('Candidato'), id + ' must retain title candidates in display or copied report');
}
assert.equal(vm.runInContext("correctionValue([{family:'Holanda',given:'Marcelo Alcantara'}])", context), 'Holanda, Marcelo Alcantara');
context.attackLink = '[click](https://example.org/" onmouseover="alert(1))';
const rendered = vm.runInContext('renderMarkdown(attackLink)', context);
assert(!rendered.includes('" onmouseover="'));
const text = vm.runInContext("renderMarkdown('[S. l.], 2020. DOI: [https://doi.org/10.1/a](https://doi.org/10.1/a).')", context);
assert(text.startsWith('[S. l.], 2020. DOI: <a'));
console.log('Frontend: escaping and review status OK');
