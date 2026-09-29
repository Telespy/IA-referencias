"""Exercise the running API with real citations and explicit synthetic fixtures."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


CASES = [
    {'name': 'Titulo: artigo sem DOI na entrada', 'online': True, 'type': 'journalArticle',
     'text': 'Titulo: ELMO 1.0: a helmet interface for CPAP and high-flow oxygen delivery',
     'fields': {'doi': '10.36416/1806-3756/e20200590'}, 'identity': True},
    {'name': 'Titulo: livro sem escolher edicao', 'online': True,
     'text': 'Dom Casmurro', 'issues_any': ['BOOK_EDITION_REQUIRED', 'AMBIGUOUS_TITLE'], 'candidates': True, 'review': True},
    {'name': 'Lei federal: cadastro oficial', 'online': True, 'type': 'legislation',
     'text': 'Lei federal 11892/2008', 'fields': {'legal_number': '11892', 'legal_year': '2008',
     'legal_date': '29/12/2008', 'publication_date': '30 dez. 2008'},
     'issues': ['LEGAL_PUBLICATION_DETAILS'], 'identity': True, 'review': True},
    {'name': 'Lei complementar federal', 'online': True, 'type': 'legislation',
     'text': 'Lei complementar federal 101/2000', 'fields': {'legal_type': 'LCP', 'legal_number': '101'}, 'identity': True},
    {'name': 'PL: Camara dos Deputados', 'online': True, 'type': 'bill',
     'text': 'Camara dos Deputados. PL 2630/2020', 'fields': {'legislative_house': 'C\u00e2mara dos Deputados'},
     'issues': ['BILL_NOT_LAW'], 'identity': True, 'approved': True},
    {'name': 'PL: Senado Federal', 'online': True, 'type': 'bill',
     'text': 'Senado Federal. PL 2338/2023', 'fields': {'legislative_house': 'Senado Federal'},
     'issues': ['BILL_NOT_LAW'], 'identity': True, 'approved': True},
    {'name': 'Lei sem jurisdicao', 'online': True, 'type': 'legislation',
     'text': 'Lei 11892/2008', 'issues': ['LEGAL_JURISDICTION_REQUIRED'], 'review': True},
    {'name': 'PL sem casa', 'online': True, 'type': 'bill',
     'text': 'PL 2630/2020', 'issues': ['LEGISLATIVE_HOUSE_REQUIRED'], 'review': True},
    {'name': 'ELMO: DOI isolado com complementacao', 'online': True, 'type': 'journalArticle',
     'text': '10.36416/1806-3756/e20200590',
     'fields': {'volume': '47', 'issue': '3', 'page': 'e20200590', 'start_month': 5, 'end_month': 6,
                'city': '[Bras\u00edlia, DF]'},
     'provenance': {'volume': 'PMC (XML do artigo)', 'end_month': 'PMC (XML do artigo)', 'city': 'NLM Catalog'},
     'abnt_contains': ['HOLANDA, Marcelo Alcantara', 'May/June 2021', 'Acesso em:'],
     'generated_access': True, 'identity': True, 'approved': True},
    {'name': 'ELMO: DOI incorreto', 'online': True, 'type': 'journalArticle',
     'text': 'HOLANDA, M. A. et al. Elmo-CPAP 1.0: a helmet interface for CPAP and high-flow oxygen delivery. Jornal Brasileiro de Pneumologia, v. 47, n. 3, e20200590, 2021. DOI: https://doi.org/10.1590/S1807-59322021000000001. Acesso em: 22 ago. 2026.',
     'fields': {'doi': '10.36416/1806-3756/e20200590', 'volume': '47', 'issue': '3',
                'start_month': 5, 'end_month': 6, 'access_date': '22 ago. 2026'}, 'identity': True},
    {'name': 'Segundo artigo: DOI e XML independentes', 'online': True, 'type': 'journalArticle',
     'text': '10.36416/1806-3756/e20200282',
     'fields': {'year': '2020', 'volume': '46', 'issue': '4', 'page': 'e20200282', 'start_month': 7, 'end_month': 8},
     'identity': True},
    {'name': 'Canen e Oliveira: artigo com abreviacoes', 'online': True, 'type': 'journalArticle',
     'text': 'CANEN, Ana; OLIVEIRA, Angela M. A. de. Multiculturalismo e curriculo em acao: um estudo de caso. Rev. Bras. Educ. [online]. 2002, n.21, pp.61-74. ISSN 1413-2478.',
     'fields': {'year': '2002', 'issue': '21', 'page': '61-74'}, 'identity': True},
    {'name': 'Carneiro: tese com URL ficticia', 'online': True, 'type': 'thesis',
     'text': 'CARNEIRO, Aparecida Sueli. A construcao do outro como nao-ser como fundamento do ser. 2005. Tese (Doutorado) - Universidade de Sao Paulo, Sao Paulo, 2005. Disponivel em: xxxx. Acesso em: 11 set. 2026.',
     'fields': {'year': '2005'}, 'issues': ['INVALID_URL'], 'review': True},
    {'name': 'Livro: ISBN 9780451524935', 'online': True, 'type': 'book',
     'text': '9780451524935', 'fields': {'isbn': '9780451524935'}, 'identity': True},
    {'name': 'Capitulo (dados sinteticos, offline)', 'online': False, 'type': 'chapter',
     'text': 'ALMEIDA, Carlos. Tecnologia na sala de aula. In: SILVA, Maria (org.). Educacao contemporanea. 2. ed. Sao Paulo: Teste, 2019. p. 45-60.',
     'fields': {'year': '2019', 'page': '45-60'}, 'review': True},
    {'name': 'Congresso (dados sinteticos, offline)', 'online': False, 'type': 'proceedings',
     'text': 'SOUZA, Joao. Metodologias ativas. In: CONGRESSO BRASILEIRO DE EDUCACAO, 3., 2019, Natal. Anais [...]. Natal: Teste, 2019. p. 10-25.',
     'fields': {'page': '10-25'}, 'review': True},
    {'name': 'Lei sem ementa e fonte oficial', 'online': False, 'type': 'legislation',
     'text': 'BRASIL. Lei n\u00ba 11.892, de 29 de dezembro de 2008.',
     'issues': ['LEGAL_REVIEW'], 'review': True},
    {'name': 'Site (dados sinteticos, offline)', 'online': False, 'type': 'website',
     'text': 'AUTOR, Maria. Pagina de teste. Portal Exemplo, 2024. Disponivel em: https://example.org/teste. Acesso em: 12 set. 2026.',
     'issues': ['URL_UNVERIFIED'], 'review': True},
    {'name': 'Podcast: preservar tipo nao coberto', 'online': False, 'type': 'unknown',
     'text': 'AUTOR. Podcast sobre referencias. 2023.', 'issues': ['UNSUPPORTED_TYPE'], 'review': True},
    {'name': 'DOI nao encontrado', 'online': True,
     'text': '10.9999/brain-format-nonexistent-fixture', 'issues': ['DOI_UNVERIFIED'], 'review': True},
    {'name': 'ISBN com digito invalido', 'online': True,
     'text': '9788535208031', 'issues': ['INVALID_ISBN'], 'review': True},
    {'name': 'Data de acesso futura', 'online': False,
     'text': 'AUTOR, Maria. Pagina de teste. Portal Exemplo, 2024. Disponivel em: https://example.org/teste. Acesso em: 12 set. 2099.',
     'issues': ['FUTURE_ACCESS_DATE'], 'review': True},
]


def run(base_url, output):
    records = []
    for online in (False, True):
        cases = [case for case in CASES if case['online'] == online]
        payload = {'text': '\n'.join(case['text'] for case in cases), 'online': online}
        request = Request(base_url.rstrip('/') + '/api/format',
                          data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=240) as response:
            data = json.load(response)
        if data['total'] != len(cases):
            raise RuntimeError('A API alterou a quantidade de referencias.')
        for case, result in zip(cases, data['results']):
            failures = []
            if result['raw'] != case['text'] or result['status'] == 'error':
                failures.append('Entrada ou processamento')
            if case.get('type') and result['item_type'] != case['type']:
                failures.append('Tipo esperado: ' + case['type'])
            for field, expected in case.get('fields', {}).items():
                if result['meta'].get(field) != expected:
                    failures.append(f'{field}: esperado {expected!r}, recebido {result["meta"].get(field)!r}')
            for field, expected in case.get('provenance', {}).items():
                if result['provenance'].get(field, {}).get('source') != expected:
                    failures.append('Origem incorreta para ' + field)
            for fragment in case.get('abnt_contains', []):
                if fragment not in result['abnt']:
                    failures.append('Trecho ausente: ' + fragment)
            if case.get('generated_access') and not result['provenance'].get('access_date', {}).get('generated'):
                failures.append('Data de acesso automatica nao identificada')
            if case.get('approved') and not result['approved']:
                failures.append('Campos completos e fontes concordantes esperados; conferir avisos da API')
            codes = {issue['code'] for issue in result['issues']}
            failures.extend('Aviso ausente: ' + code for code in case.get('issues', []) if code not in codes)
            if case.get('issues_any') and not codes.intersection(case['issues_any']):
                failures.append('Pedido de confirmacao da obra/edicao ausente')
            if case.get('candidates') and not result.get('candidates'):
                failures.append('Nenhum candidato retornado pela busca por titulo')
            if case.get('identity') and not result['identity_verified']:
                failures.append('Obra nao confirmada online; verificar tambem disponibilidade da fonte')
            if case.get('review') and (result['approved'] or result['status'] != 'needs_review'):
                failures.append('Pendencia indevidamente aprovada')
            records.append({'case': case['name'], 'online': online, 'passed': not failures,
                            'failures': failures, 'result': result})
            print(('OK' if not failures else 'FALHOU') + ': ' + case['name'], flush=True)
            for failure in failures:
                print('  ' + failure, flush=True)
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'api': base_url,
              'passed': sum(r['passed'] for r in records), 'total': len(records), 'cases': records}
    output.mkdir(parents=True, exist_ok=True)
    (output / 'reference-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Teste de correcao de referencias', '', f'Data UTC: {report["checked_at"]}',
             f'Resultado: {report["passed"]}/{report["total"]} cenarios aprovados nos criterios do teste.',
             'Um teste aprovado nao significa que a referencia esteja completa ou certificada pela ABNT.', '']
    for record in records:
        result = record['result']
        lines.extend(['## ' + record['case'], '',
                      f'Teste: {"OK" if record["passed"] else "FALHOU"}; resultado: {result["status"]}.', '',
                      'Entrada: ' + result['raw'], '', result['abnt'], ''])
        lines.extend('- ' + issue['message'] for issue in result['issues'])
        lines.extend('- Fonte: ' + source['name'] + ' ' + source['url'] for source in result['sources'])
        lines.extend('- Falha do teste: ' + failure for failure in record['failures'])
        lines.append('')
    (output / 'reference-verification.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Relatorio: {output / "reference-verification.md"}')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://localhost:8000')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent.parent / 'artifacts')
    args = parser.parse_args()
    raise SystemExit(0 if run(args.url, args.output) else 1)
