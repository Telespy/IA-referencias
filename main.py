import sys
from pathlib import Path

from correction import correct_reference, reference_report
from article_enrichment import enrich_article
from legal_references import fetch_legal_reference
from case_law import fetch_stf_case
from title_lookup import fetch_title_candidates
from reference_validation import verify_work_identity
from sources import fetch_crossref_doi, fetch_crossref_search, fetch_google_books, fetch_by_url


def process_reference_line(raw_line: str, online: bool = True) -> dict:
    return correct_reference(
        raw_line, online=online, fetch_doi=fetch_crossref_doi,
        fetch_book=fetch_google_books, search=fetch_crossref_search, fetch_url=fetch_by_url,
        enrich=enrich_article, fetch_title=fetch_title_candidates, fetch_legal=fetch_legal_reference,
        fetch_case=fetch_stf_case,
    )


def run_formatter(input_filepath: str = 'referencias_entrada.txt'):
    path = Path(input_filepath)
    if not path.is_file():
        print(f'Arquivo de entrada nao encontrado: {path}')
        return
    results = [process_reference_line(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    for style in ('abnt', 'apa'):
        report = '\n\n'.join(reference_report(r, i, style) for i, r in enumerate(results, 1))
        Path(f'referencias_{style.upper()}.md').write_text(report + '\n', encoding='utf-8')
    combined = '\n\n'.join(
        f'Original: {r["raw"]}\n' + reference_report(r, i) + f'\nAPA: {r["apa"]}'
        for i, r in enumerate(results, 1)
    )
    Path('referencias_completas.md').write_text(combined + '\n', encoding='utf-8')
    print(f'{len(results)} referencias processadas; {sum(not r["approved"] for r in results)} precisam de revisao.')


if __name__ == '__main__':
    run_formatter(sys.argv[1] if len(sys.argv) > 1 else 'referencias_entrada.txt')
