import re
from legal_references import parse_legal_request

DOI_REGEX = re.compile(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', re.IGNORECASE)
ISBN_REGEX = re.compile(r'(?:ISBN(?:-1[03])?:?\s*)?(?=[0-9X]{10}$|(?=(?:[0-9]{3}[- ]){3})[0-9- ]{17}$)[0-9]{1,5}[- ]?[0-9]+[- ]?[0-9]+[- ]?[0-9X]', re.IGNORECASE)
URL_REGEX = re.compile(r'https?://[^\s)]+', re.IGNORECASE)

CORPORATE_ENTITIES = {
    'BRASIL', 'SÃO PAULO', 'RIO DE JANEIRO', 'MINAS GERAIS', 'BAHIA', 'PARANÁ', 
    'RIO GRANDE DO SUL', 'PERNAMBUCO', 'CEARÁ', 'SANTA CATARINA', 'GOIÁS', 'MARANHÃO', 
    'AMAZONAS', 'ESPÍRITO SANTO', 'PARAÍBA', 'MATO GROSSO', 'RIO GRANDE DO NORTE', 
    'ALAGOAS', 'PIAUÍ', 'DISTRITO FEDERAL', 'SERGIPE', 'RONDÔNIA', 'TOCANTINS', 
    'ACRE', 'AMAPÁ', 'RORAIMA', 'IFRN', 'UFRN', 'USP', 'UNICAMP', 'UNESP', 'UFF', 'UFRJ',
    'EMBRAPA', 'MINISTÉRIO DA EDUCAÇÃO', 'MINISTÉRIO DA SAÚDE', 'INPI', 'IBGE'
}

KNOWN_LEGISLATION_URLS = {
    "11.892": "https://planalto.gov.br/ccivil_03/_ato2007-2010/2008/lei/l11892.htm",
    "11892": "https://planalto.gov.br/ccivil_03/_ato2007-2010/2008/lei/l11892.htm",
    "9.394": "https://www.planalto.gov.br/ccivil_03/leis/l9394.htm",
    "9394": "https://www.planalto.gov.br/ccivil_03/leis/l9394.htm"
}


def extract_isbn(text: str) -> str:
    """Extrai ISBN-10 ou ISBN-13 preservando o identificador completo."""
    if not text:
        return ""
    clean_text = text.strip()
    if len(clean_text) <= 30:
        candidates = re.findall(r'(?:ISBN(?:-1[03])?:?\s*)?([0-9Xx][0-9Xx\s-]{8,20}[0-9Xx])', clean_text, flags=re.I)
    else:
        candidates = re.findall(r'\bISBN(?:-1[03])?:?\s*([0-9Xx][0-9Xx\s-]{8,20}[0-9Xx])', clean_text, flags=re.I)
        
    for candidate in candidates:
        clean = re.sub(r'[^0-9Xx]', '', candidate).upper()
        if len(clean) in (10, 13) and clean[:-1].isdigit():
            return clean
    return ""


def parse_authors(authors_str: str) -> list:
    """Extrai lista de autores individuais ou entidade corporativa com papéis (org., ed., comp., coord.)."""
    if not authors_str:
        return []
    
    abbreviated = bool(re.search(r'\bet\s+al\.?', authors_str, re.I))
    clean_str = re.sub(r'\s+et\s+al\.?', '', authors_str, flags=re.I).strip()
    if not re.search(r'\b[A-Za-z]\.$', clean_str):
        clean_str = clean_str.rstrip('.')
    
    role = ""
    role_match = re.search(r'\s*\((org|ed|comp|coord|organizador|organizadores|editor|editores|orgs|eds|coords|comps)s?\.?\)', clean_str, re.I)
    if role_match:
        raw_r = role_match.group(1).lower().rstrip('.')
        if 'org' in raw_r:
            role = 'org.'
        elif 'ed' in raw_r:
            role = 'ed.'
        elif 'coord' in raw_r:
            role = 'coord.'
        elif 'comp' in raw_r:
            role = 'comp.'
        else:
            role = f"{raw_r}."
        clean_str = clean_str[:role_match.start()].strip()
        
    if clean_str.upper() in CORPORATE_ENTITIES or (clean_str.isupper() and len(clean_str) >= 5 and ';' not in clean_str and ',' not in clean_str):
        return [{'given': '', 'family': clean_str, 'is_corporate': True, 'role': role}]
    
    parts = [p.strip() for p in clean_str.split(';') if p.strip()]
    authors = []
    for p in parts:
        if ',' in p:
            fam, giv = p.split(',', 1)
            fam_clean = fam.strip()
            giv_clean = giv.strip()
            if re.search(r'\b[A-Za-z]$', giv_clean):
                giv_clean += '.'
            authors.append({'family': fam_clean, 'given': giv_clean, 'role': role})
        else:
            authors.append({'family': p.strip(), 'given': '', 'role': role})
    if abbreviated and authors:
        authors[0]['et_al'] = True
    return authors


def split_author_and_title(text: str) -> tuple:
    """
    Separa de forma precisa autores e título de um trecho (ex: antes de 'In:' ou dentro de 'In:').
    Respeita iniciais de autores com ponto (ex: 'TAVARES, A. R. Vestígios...') para não quebrar
    iniciais como título, e reconhece marcadores de responsabilidade como (org.), (ed.), etc.
    Retorna (authors_raw, title_raw).
    """
    clean = text.strip()
    if not clean:
        return "", ""
    et_al = re.search(r'\bet\s+al\.\s+', clean, re.I)
    if et_al:
        return clean[:et_al.end()].strip(), clean[et_al.end():].strip().rstrip('.')
        
    if clean.startswith(('___', '---', '–––', '—')):
        m = re.match(r'^[_–—-]+\.?\s*', clean)
        title_only = clean[m.end():].strip().rstrip('.') if m else clean.rstrip('.')
        return "", title_only

    # 1. Verifica se há marcador explícito de responsabilidade: (org.), (ed.), (coord.), etc.
    role_match = re.search(
        r'\s*(\((?:org|ed|coord|comp|organizador|organizadores|editor|editores|orgs|eds|coords|comps)s?\.?\))\s*\.?\s*',
        clean,
        re.I
    )
    if role_match:
        authors_raw = clean[:role_match.end()].strip().rstrip('.')
        title_raw = clean[role_match.end():].strip().rstrip('.')
        return authors_raw, title_raw

    # 2. Busca o ponto que encerra a lista de autores.
    # Iniciais têm ponto e espaço (ex: 'A. R.'). Um ponto só encerra os autores
    # se o trecho posterior NÃO começar com inicial (ex: 'R. ') nem ';'
    dot_matches = list(re.finditer(r'\.\s*', clean))
    for m in dot_matches:
        cand_title = clean[m.end():].strip()
        
        if re.match(r'^[A-Z]\.[\s;,]', cand_title):
            continue
        if re.match(r'^(?:da|de|do|das|dos)\.\s+', cand_title, re.I):
            continue
        if cand_title.startswith(';'):
            continue
        if re.search(r';\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ\s-]+,', cand_title):
            continue
            
        if re.search(r'\b[A-Za-z]$', clean[:m.start()].strip()):
            cand_author = clean[:m.start()+1].strip()
        else:
            cand_author = clean[:m.start()].strip()
            
        if ',' in cand_author or cand_author.upper() in CORPORATE_ENTITIES:
            if cand_title:
                return cand_author, cand_title.rstrip('.')

    if '. ' in clean:
        parts = clean.split('. ', 1)
        return parts[0].strip(), parts[1].strip().rstrip('.')

    return "", clean.rstrip('.')


def detect_reference_type(line: str, after_in: str = "") -> str:
    """
    Identifica de forma determinística e hierárquica o tipo da referência
    segundo a ABNT NBR 6023:2018, sem colisões ou interferências mútuas.
    """
    legal_request = parse_legal_request(line)
    if legal_request:
        return legal_request['item_type']
    # 1. LEGISLAÇÃO
    if re.search(r'^(?:BRASIL|[A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{2,})\.\s*(?:Lei|Decreto|Portaria|Resolução|Medida Provisória|Constituição)', line, re.I) or \
       re.search(r'^(?:Lei|Decreto|Portaria|Resolução|Medida Provisória|Constituição)\s+nº?[\s\d]', line, re.I) or \
       re.search(r'\b(?:Lei|Decreto|Portaria|Resolução)\s+nº?\s*[\d\.-]+,?\s+de\s+\d+\s+de\s+[a-z]+\s+de\s+\d{4}\b', line, re.I):
        return 'legislation'

    # 2. PATENTE
    if re.search(r'\b(?:BR\s*\d{2}|Depósito:|Concessão:)\b', line, re.I) or re.search(r'\bINPI\b', line):
        return 'patent'

    # 3. CAPÍTULO OU ANAIS (In:)
    if after_in:
        event_keywords = ['SIMPÓSIO', 'CONGRESSO', 'ENCONTRO', 'JORNADA', 'SEMINÁRIO', 'CONFERÊNCIA', 'COLÓQUIO', 'WORKSHOP', 'Anais', 'Proceedings']
        if any(k.lower() in after_in.lower() for k in event_keywords):
            return 'proceedings'
        return 'chapter'

    # 4. TRABALHOS ACADÊMICOS (Tese, Dissertação, TCC, Monografia)
    academic_keywords = re.search(
        r'\b(?:'
        r'Tese\s*\([^\)]+\)|Tese\s+de\s+[^\.\–—-]+|Tese\b|'
        r'Dissertaç[ãa]o\s*\([^\)]+\)|Dissertaç[ãa]o\s+de\s+[^\.\–—-]+|Dissertaç[ãa]o\b|'
        r'Trabalho\s+de\s+Conclus[ãa]o\s+de\s+Curso\s*\([^\)]+\)|Trabalho\s+de\s+Conclus[ãa]o\s+de\s+Curso\s+de\s+[^\.\–—-]+|Trabalho\s+de\s+Conclus[ãa]o\s+de\s+Curso\b|'
        r'Monografia\s*\([^\)]+\)|Monografia\s+de\s+[^\.\–—-]+|Monografia\b|'
        r'TCC\s*\([^\)]+\)|TCC\b|'
        r'Livre-Docência|Relatório\s+de\s+Pós-Doutorado\s*\([^\)]+\)|Relatório\s+de\s+Pós-Doutorado\b'
        r')',
        line,
        re.I
    )
    if academic_keywords:
        return 'thesis'

    # 5. DOCUMENTO INSTITUCIONAL / DSPACE
    if "memoria.ifrn.edu.br" in line or "handle/" in line or "repositorio." in line:
        return 'legal'

    # 6. ARTIGO DE JORNAL / IMPRENSA
    newspaper_names = ['Folha de S.Paulo', 'Folha de S. Paulo', 'O Globo', 'Estado de S. Paulo', 'Estado de S.Paulo', 'Jornal do Brasil', 'Gazeta do Povo', 'Correio Braziliense']
    if any(n.lower() in line.lower() for n in newspaper_names) or (re.search(r'\b(?:Caderno|Seção)\b', line, re.I) and re.search(r'\b\d{1,2}\s+[a-zç]+\.?\s*\d{4}\b', line, re.I)):
        return 'newspaperArticle'

    # Indicadores de periódico vs. livro
    has_vol = bool(re.search(r'\bv\.\s*\d+', line, re.I))
    has_num = bool(re.search(r'\bn\.\s*\d+', line, re.I))
    has_periodical_months = bool(re.search(r'\b(jan\.|fev\.|mar\.|abr\.|maio|jun\.|jul\.|ago\.|set\.|out\.|nov\.|dez\.)/(jan\.|fev\.|mar\.|abr\.|maio|jun\.|jul\.|ago\.|set\.|out\.|nov\.|dez\.)', line, re.I))
    has_doi = bool(re.search(r'\bDOI:', line, re.I))
    has_pages = bool(re.search(r'\bp\.\s*[\d\s–-]+', line, re.I))

    # Verifica se tem 'Cidade: Editora, Ano' (editora de livro/monografia)
    line_no_urls = re.sub(r'https?://[^\s)]+', '', line)
    has_book_publisher = bool(re.search(r'[A-Za-zÁÉÍÓÚÂÊÔÃÕÇ\s]+:\s*[A-Za-zÁÉÍÓÚÂÊÔÃÕÇ0-9\s]+,\s*\d{4}', line_no_urls))

    # 7. WEBSITE / PÁGINA DA INTERNET
    # Se contém Portal, Site, Blog, ou "Disponível em:" sem ter editora de livro e sem volume/número de periódico
    if re.search(r'\b(?:Portal|Site|Blog)\b', line, re.I) or "disponível em:" in line.lower() or "acesso em:" in line.lower():
        if not has_book_publisher and not has_vol and not has_num:
            return 'website'

    # 8. ARTIGO DE PERIÓDICO CIENTÍFICO (JOURNAL)
    if has_vol or has_num or has_periodical_months:
        return 'journalArticle'

    # 9. LIVRO INTEIRO (MONOGRAFIA)
    has_publisher_colon = bool(re.search(r'\b[A-ZÁÉÍÓÚÂÊÔÃÕÇa-zá-ú\s-]+:\s*[^,]+,\s*\d{4}', line_no_urls)) or \
                           bool(re.search(r'\b[A-ZÁÉÍÓÚÂÊÔÃÕÇa-zá-ú\s-]+:\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇa-zá-ú\s\.]+$', line_no_urls))
    has_edition = bool(re.search(r'\b\d+\.\s*ed\.?', line, re.I))
    has_isbn = bool(extract_isbn(line))
    has_page_count = bool(re.search(r'\b\d+\s*(?:p|f|pág|páginas|folhas)\.?\s*$', line_no_urls, re.I))

    if has_publisher_colon or has_edition or has_isbn or has_page_count:
        return 'book'

    # Se tiver páginas ou DOI e não for livro: periódico
    if has_pages or has_doi:
        return 'journalArticle'

    # 10. Fallback final para website se tiver URL, senão book
    if "http" in line or "www." in line:
        return 'website'

    return 'book'


def _parse_legislation(line: str, url: str, access_date: str) -> dict:
    jurisdiction_match = re.match(r'^([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]{2,})\.', line)
    jurisdiction = jurisdiction_match.group(1).strip() if jurisdiction_match else ''
    
    law_title_match = re.search(r'((?:Lei|Decreto|Portaria|Resolução|Medida Provisória|Constituição)\s+nº?\s*[\d\.-]+,?\s*de\s+\d+\s+de\s+[a-z]+\s+de\s+\d{4})', line, re.I)
    law_title = law_title_match.group(1).strip() if law_title_match else "Lei"
    
    rest = line[line.find(law_title) + len(law_title):].strip().lstrip('.').strip() if law_title in line else line
    pub_match = re.search(r'([\w\s]+,\s*[A-Z]{2}):\s*([^,]+),\s*(\d{4})', rest, re.UNICODE)
    if pub_match:
        ementa = rest[:pub_match.start()].strip().rstrip('.')
        city = pub_match.group(1).strip()
        publisher = pub_match.group(2).strip()
        year = pub_match.group(3).strip()
    else:
        y_match = re.search(r'\b(19\d\d|20\d\d)\b', rest)
        year = y_match.group(1) if y_match else ""
        ementa = rest.rstrip('.').strip()
        city = ""
        publisher = ""
    if not year:
        match = re.search(r'\b\d{4}\b', law_title)
        year = match.group(0) if match else ''

    legis_url = url
                
    return {
        'item_type': 'legislation',
        'jurisdiction': jurisdiction,
        'title': law_title,
        'ementa': ementa,
        'city': city,
        'publisher': publisher,
        'year': year,
        'url': legis_url,
        'access_date': access_date,
        'authors': [{'given': '', 'family': jurisdiction, 'is_corporate': True}]
    }


def _parse_patent(line: str, url: str, access_date: str) -> dict:
    m = re.search(r'^([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s,;.-]+?)\.\s*(.*?)\.\s*(BR[\d\s]+)\.\s*(Depósito:[^\.]+\.)\s*(Concessão:[^\.]+)?', line, re.I)
    if m:
        return {
            'item_type': 'patent',
            'authors': parse_authors(m.group(1)),
            'title': m.group(2).strip(),
            'patent_no': m.group(3).strip(),
            'deposit_info': m.group(4).strip(),
            'concession_info': m.group(5).strip() if m.group(5) else '',
            'url': url,
            'access_date': access_date
        }
    pat_match = re.search(r'\b(BR\s*[\d\s]+[A-Z0-9]*)', line, re.I)
    patent_no = pat_match.group(1).strip() if pat_match else ""
    dep_match = re.search(r'(Depósito:[^\.]+)', line, re.I)
    deposit_info = dep_match.group(1).strip() + "." if dep_match else ""
    conc_match = re.search(r'(Concessão:[^\.]+)', line, re.I)
    concession_info = conc_match.group(1).strip() + "." if conc_match else ""
    
    before_pat = line[:pat_match.start()].strip().rstrip('.') if pat_match else line
    aut_raw, tit_raw = split_author_and_title(before_pat)
    return {
        'item_type': 'patent',
        'authors': parse_authors(aut_raw),
        'title': tit_raw,
        'patent_no': patent_no,
        'deposit_info': deposit_info,
        'concession_info': concession_info,
        'url': url,
        'access_date': access_date
    }


def _parse_thesis(line: str, url: str, access_date: str) -> dict:
    academic_keywords = re.search(
        r'\b('
        r'Tese\s*\([^\)]+\)|Tese\s+de\s+[^\.\–—-]+|Tese\b|'
        r'Dissertaç[ãa]o\s*\([^\)]+\)|Dissertaç[ãa]o\s+de\s+[^\.\–—-]+|Dissertaç[ãa]o\b|'
        r'Trabalho\s+de\s+Conclus[ãa]o\s+de\s+Curso\s*\([^\)]+\)|Trabalho\s+de\s+Conclus[ãa]o\s+de\s+Curso\s+de\s+[^\.\–—-]+|Trabalho\s+de\s+Conclus[ãa]o\s+de\s+Curso\b|'
        r'Monografia\s*\([^\)]+\)|Monografia\s+de\s+[^\.\–—-]+|Monografia\b|'
        r'TCC\s*\([^\)]+\)|TCC\b|'
        r'Relatório\s+de\s+Pós-Doutorado\s*\([^\)]+\)|Relatório\s+de\s+Pós-Doutorado\b'
        r')',
        line,
        re.I
    )
    deg_match = academic_keywords
    degree_type_raw = deg_match.group(0).strip().rstrip('.').rstrip('–').rstrip('-').rstrip('—').strip() if deg_match else ""
    
    dt_lower = degree_type_raw.lower()
    if '(' in degree_type_raw:
        degree_type = degree_type_raw
    elif dt_lower == 'tese de doutorado':
        degree_type = 'Tese (Doutorado)'
    elif dt_lower.startswith(('tese de livre', 'tese (livre')):
        degree_type = 'Tese (Livre-Docência)'
    elif dt_lower == 'dissertação de mestrado':
        degree_type = 'Dissertação (Mestrado)'
    elif dt_lower == 'monografia de especialização':
        degree_type = 'Monografia (Especialização)'
    elif dt_lower in ('trabalho de conclusão de curso', 'trabalho de conclusao de curso', 'tcc'):
        degree_type = 'Trabalho de Conclusão de Curso'
    else:
        degree_type = degree_type_raw

    before_deg = line[:deg_match.start()].strip().rstrip('.') if deg_match else line
    authors_raw, rest_before = split_author_and_title(before_deg)
    
    leaves = ""
    l_match = re.search(r'\b(\d+\s*(?:f|p|fls|folhas|p[áa]ginas)\.?)\s*$', rest_before, re.I)
    if l_match:
        leaves = l_match.group(1).strip()
        if not leaves.endswith('.'):
            leaves += '.'
        rest_before = rest_before[:l_match.start()].strip().rstrip('.')
        
    degree_year = ""
    y_dep_match = re.search(r'\b(19\d\d|20\d\d)\.?\s*$', rest_before)
    if y_dep_match:
        degree_year = y_dep_match.group(1).strip().rstrip('.')
        rest_before = rest_before[:y_dep_match.start()].strip().rstrip('.')
        
    title = rest_before.strip().rstrip('.')
        
    after_deg = line[deg_match.end():].strip() if deg_match else ""
    after_deg = re.sub(r'^[\s–—\.-]+|^\s*apresentad[ao]\s+[aà]o?\s+', '', after_deg, flags=re.I).strip()
    after_deg = re.sub(r'^\([^\)]*\)\s*[–—\.-]*\s*', '', after_deg).strip()
    
    year = ""
    y_match = re.search(r'\b(19\d\d|20\d\d)\b(?=[^\d]*$)', after_deg)
    if y_match:
        year = y_match.group(1)
        after_deg = after_deg[:y_match.start()].strip().rstrip(',').rstrip('.').strip()
    else:
        year = degree_year
        
    if not degree_year:
        degree_year = year
        
    after_deg = re.sub(r':\s*\[?s\.\s*n\.?\]?', '', after_deg, flags=re.I).strip()
    after_deg = re.sub(r':\s*[^,]+$', '', after_deg).strip()
    after_deg = after_deg.rstrip(',').rstrip('.').strip()
    
    inst_parts = [p.strip() for p in after_deg.split(',') if p.strip()]
    if len(inst_parts) >= 2:
        city = inst_parts[-1]
        institution = ', '.join(inst_parts[:-1])
    elif len(inst_parts) == 1:
        institution = inst_parts[0]
        city = ""
    else:
        institution = ""
        city = ""
        
    return {
        'item_type': 'thesis',
        'authors': parse_authors(authors_raw),
        'title': title,
        'degree_year': degree_year,
        'leaves': leaves,
        'degree_type': degree_type,
        'institution': institution,
        'city': city,
        'year': year,
        'url': url,
        'access_date': access_date
    }


def _parse_proceedings(line: str, before_in: str, after_in: str, doi: str, isbn: str, url: str, access_date: str) -> dict:
    c_authors_raw, c_title = split_author_and_title(before_in)
    authors = parse_authors(c_authors_raw) if c_authors_raw else []
    
    pag_match = re.search(r'\bp\.\s*([\d\s–-]+)', after_in, re.I)
    page = pag_match.group(1).strip() if pag_match else ''
    
    ev_match = re.search(r'^([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s,.-]+?),\s*(\d+\.),?\s*(\d{4}),?\s*([A-ZÁÉÍÓÚa-z\s,-]+)\.\s*(Anais[^\.]*)\.\s*([^:]+):\s*([^,]+),\s*(\d{4})', after_in, re.I)
    if ev_match:
        return {
            'item_type': 'proceedings',
            'authors': authors,
            'title': c_title,
            'event_name': ev_match.group(1).strip(),
            'event_number': ev_match.group(2).strip(),
            'event_year': ev_match.group(3).strip(),
            'event_city': ev_match.group(4).strip(),
            'proceedings_title': ev_match.group(5).strip(),
            'city': ev_match.group(6).strip(),
            'publisher': ev_match.group(7).strip(),
            'year': ev_match.group(8).strip(),
            'page': page,
            'doi': doi,
            'isbn': isbn,
            'url': url,
            'access_date': access_date
        }
    
    y_match = re.search(r'\b(19\d\d|20\d\d)\b', after_in)
    event_year = y_match.group(1) if y_match else ''
    
    num_match = re.search(r'\b(\d+\.|\d+º|[IVXLCDM]+\.)\s*', after_in)
    event_number = num_match.group(1).strip() if num_match else ''
    
    proc_match = re.search(r'\b(Anais[^\.]*|Proceedings[^\.]*|Resumos[^\.]*|Atas[^\.]*)', after_in, re.I)
    proceedings_title = proc_match.group(1).strip() if proc_match else 'Anais [...]'
    
    city = ''
    publisher = ''
    pub_match = re.search(r'([^:]+):\s*([^,]+),\s*(\d{4})', after_in)
    if pub_match:
        city = pub_match.group(1).split('.')[-1].strip()
        publisher = pub_match.group(2).strip()
        year = pub_match.group(3).strip()
    else:
        year = event_year
        
    event_name_raw = after_in.split('.')[0].strip()
    if ',' in event_name_raw:
        event_name = event_name_raw.split(',')[0].strip()
    else:
        event_name = event_name_raw
        
    return {
        'item_type': 'proceedings',
        'authors': authors,
        'title': c_title,
        'event_name': event_name,
        'event_number': event_number,
        'event_year': event_year,
        'event_city': '',
        'proceedings_title': proceedings_title,
        'city': city,
        'publisher': publisher,
        'year': year,
        'page': page,
        'doi': doi,
        'isbn': isbn,
        'url': url,
        'access_date': access_date
    }


def _parse_chapter(line: str, before_in: str, after_in: str, doi: str, isbn: str, url: str, access_date: str) -> dict:
    c_authors_raw, c_title = split_author_and_title(before_in)
    c_authors = parse_authors(c_authors_raw) if c_authors_raw else []
    
    pag_match = re.search(r'\bp\.\s*([\d\s–-]+)', after_in, re.I)
    page = pag_match.group(1).strip() if pag_match else ''
    
    ed_match = re.search(r'(\d+\.\s*ed\.?)', after_in, re.I)
    edition = ed_match.group(1).strip() if ed_match else ''
    if edition and not edition.endswith('.'):
        edition += '.'
    
    year_match = re.search(r'\b(19\d\d|20\d\d)\b(?=[^\d]*$)', after_in)
    year = year_match.group(1) if year_match else ''

    publisher = ''
    city = ''
    b_before_city = after_in
    
    last_colon = after_in.rfind(':')
    if last_colon != -1:
        pub_match = re.search(r'([^:]+),\s*(\d{4})', after_in[last_colon+1:])
        if pub_match:
            publisher = pub_match.group(1).strip()
            year = pub_match.group(2).strip()
            
            b_before_colon = after_in[:last_colon].strip()
            city_dot = b_before_colon.rfind('.')
            if city_dot != -1:
                city = b_before_colon[city_dot+1:].strip()
                b_before_city = b_before_colon[:city_dot].strip()
            else:
                city = b_before_colon
                b_before_city = b_before_colon
                
            if edition and city.startswith(edition):
                city = city[len(edition):].strip()
            if edition:
                b_before_city = re.sub(r'\s*\d+\.\s*ed\.?\s*$', '', b_before_city, flags=re.I).strip().rstrip('.')
                city = re.sub(r'^\s*\d+\.\s*ed\.?\s*', '', city, flags=re.I).strip()
                
    b_authors_raw, b_title = split_author_and_title(b_before_city)
    b_authors = parse_authors(b_authors_raw) if b_authors_raw else []
    
    return {
        'item_type': 'chapter',
        'authors': c_authors,
        'title': c_title,
        'book_authors': b_authors,
        'book_title': b_title,
        'edition': edition,
        'city': city,
        'publisher': publisher,
        'year': year,
        'page': page,
        'doi': doi,
        'isbn': isbn,
        'url': url,
        'access_date': access_date
    }


def _parse_journal(line: str, doi: str, isbn: str, url: str, access_date: str) -> dict:
    authors_raw, remainder = split_author_and_title(line)
    title_raw, _, rest = remainder.partition('. ')

    year_match = re.search(r'\b(19\d\d|20\d\d)\b', rest)
    year = year_match.group(1) if year_match else ''
    
    vol_match = re.search(r'\bv\.\s*(\d+)', rest, re.I)
    vol = vol_match.group(1) if vol_match else ''
    
    num_match = re.search(r'\bn\.\s*(\d+)', rest, re.I)
    num = num_match.group(1) if num_match else ''
    
    pag_match = re.search(r'\bpp?\.\s*([\d\s–-]+)', rest, re.I)
    pag = pag_match.group(1).strip() if pag_match else ''
    if not pag:
        elocation = re.search(r'\b(e\d{4,})\b', rest, re.I)
        pag = elocation.group(1) if elocation else ''
    
    month_match = re.search(r'\b(jan\.|fev\.|mar\.|abr\.|maio|jun\.|jul\.|ago\.|set\.|out\.|nov\.|dez\.)(?:/(jan\.|fev\.|mar\.|abr\.|maio|jun\.|jul\.|ago\.|set\.|out\.|nov\.|dez\.))?', rest, re.I)
    month_str = month_match.group(0) if month_match else ''
    
    boundaries = [match.start() for match in (vol_match, num_match, pag_match, year_match) if match]
    journal_part = rest[:min(boundaries)] if boundaries else rest
    journal_part = re.sub(r'\s*\[online\]\s*', '', journal_part, flags=re.I).strip().rstrip(' ,. ')
        
    j_parts = journal_part.split(',')
    if len(j_parts) >= 2:
        cand_city = j_parts[-1].strip().rstrip('.')
        if cand_city and not cand_city.isdigit() and not re.match(r'^\d+$', cand_city) and not cand_city.lower().startswith(('n.', 'v.', 'p.')):
            city = cand_city
            journal = ','.join(j_parts[:-1]).strip().rstrip('.')
        else:
            journal = journal_part.strip().rstrip('.')
            city = ''
    else:
        journal = journal_part.strip().rstrip('.')
        city = ''
        
    return {
        'item_type': 'journalArticle',
        'authors': parse_authors(authors_raw),
        'title': title_raw.strip().rstrip('.'),
        'journal': journal,
        'city': city,
        'volume': vol,
        'issue': num,
        'page': pag,
        'month_str': month_str,
        'year': year,
        'doi': doi,
        'isbn': isbn,
        'url': url,
        'access_date': access_date
    }


def _parse_book(line: str, isbn: str, doi: str, url: str, access_date: str) -> dict:
    clean_line = line.strip().rstrip('.')
    
    page_count = ""
    p_match = re.search(r'\b(\d+\s*(?:p|f|pág|páginas|folhas)\.?)\s*$', clean_line, re.I)
    if p_match:
        page_count = p_match.group(1).strip()
        clean_line = clean_line[:p_match.start()].strip().rstrip('.')

    authors_raw, rest = split_author_and_title(clean_line)
    if not authors_raw and '. ' in clean_line:
        parts = clean_line.split('. ', 1)
        authors_raw, rest = parts[0], parts[1]
    elif not authors_raw:
        rest = clean_line

    ed_match = re.search(r'(\d+\.\s*ed\.?)\s*', rest, re.I)
    edition = ''
    if ed_match:
        edition = ed_match.group(1).strip()
        if not edition.endswith('.'):
            edition += '.'
        rest = rest[:ed_match.start()] + rest[ed_match.end():]
        rest = rest.strip()

    city = ""
    publisher = ""
    year = ""
    title_raw = rest
    
    last_colon = rest.rfind(':')
    if last_colon != -1:
        before_colon = rest[:last_colon].strip()
        after_colon = rest[last_colon+1:].strip()
        
        city_dot = before_colon.rfind('.')
        if city_dot != -1:
            city = before_colon[city_dot+1:].strip()
            title_raw = before_colon[:city_dot].strip()
        else:
            city = before_colon
            title_raw = before_colon
            
        m_pub = re.search(r'^([^,]+),\s*(\d{4})', after_colon)
        if m_pub:
            publisher = m_pub.group(1).strip()
            year = m_pub.group(2).strip()
        else:
            m_pub_year = re.search(r'^(\d{4})', after_colon)
            if m_pub_year:
                year = m_pub_year.group(1).strip()
            else:
                publisher = after_colon.rstrip('.').strip()
    else:
        y_match = re.search(r'[\.,]\s*(\d{4})\s*$', rest)
        if y_match:
            year = y_match.group(1)
            title_raw = rest[:y_match.start()].strip()

    authors = parse_authors(authors_raw)
    item_type = 'legal' if authors and authors[0].get('is_corporate') else 'book'
    return {
        'item_type': item_type,
        'authors': authors,
        'title': title_raw.strip().rstrip('.'),
        'edition': edition,
        'city': city,
        'publisher': publisher,
        'year': year,
        'page': page_count,
        'isbn': isbn,
        'doi': doi,
        'url': url,
        'access_date': access_date
    }


def _parse_newspaper(line: str, url: str, access_date: str) -> dict:
    m = re.search(r'^([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s,;.-]+?)\.\s*(.*?)\.\s*([A-ZÁÉÍÓÚa-z\s\.-]+?),\s*([A-ZÁÉÍÓÚa-z\s,-]+),\s*(\d+\s+[a-z]+\.\s*\d{4})\.\s*(Caderno[^\,]+|Seção[^\,]+)?,?\s*(?:p\.\s*([A-Z0-9-]+))?', line, re.I)
    if m:
        return {
            'item_type': 'newspaperArticle',
            'authors': parse_authors(m.group(1)),
            'title': m.group(2).strip().rstrip('.'),
            'newspaper': m.group(3).strip(),
            'city': m.group(4).strip(),
            'date_str': m.group(5).strip(),
            'section': m.group(6).strip() if m.group(6) else '',
            'page': m.group(7).strip() if m.group(7) else '',
            'url': url,
            'access_date': access_date
        }
    parts = line.split('. ')
    aut_raw = parts[0] if len(parts) >= 1 else ''
    tit_raw = parts[1] if len(parts) >= 2 else ''
    rest = '. '.join(parts[2:]) if len(parts) >= 3 else ''
    dt_match = re.search(r'(\d{1,2}\s+[a-zç]+\.?\s*\d{4})', rest)
    dt_str = dt_match.group(1) if dt_match else ''
    y_match = re.search(r'\b(19\d\d|20\d\d)\b', rest)
    year = y_match.group(1) if y_match else ''
    
    return {
        'item_type': 'newspaperArticle',
        'authors': parse_authors(aut_raw),
        'title': tit_raw.strip().rstrip('.'),
        'newspaper': rest.split(',')[0].strip() if rest else 'Jornal',
        'city': '',
        'date_str': dt_str,
        'year': year,
        'section': '',
        'page': '',
        'url': url,
        'access_date': access_date
    }


def _parse_website(line: str, url: str, access_date: str) -> dict:
    web_match = re.search(r'^([A-ZÁÉÍÓÚÂÊÔÃÕÇ\s,;.-]+?)\.\s*(.*?)\.\s*([A-ZÁÉÍÓÚa-z\s\.-]+?)(?:,\s*([A-ZÁÉÍÓÚa-z\s,-]+))?,\s*((?:\d{1,2}\s+[a-zç]+\.?\s*)?\d{4})', line, re.I)
    if web_match:
        aut_raw = web_match.group(1).strip()
        tit_raw = web_match.group(2).strip()
        site_raw = web_match.group(3).strip()
        possible_city = web_match.group(4).strip() if web_match.group(4) else ""
        date_raw = web_match.group(5).strip()
        
        city = possible_city
        date_str = date_raw
        year_match = re.search(r'\b(19\d\d|20\d\d)\b', date_raw)
        year = year_match.group(1) if year_match else ""
        
        return {
            'item_type': 'website',
            'authors': parse_authors(aut_raw),
            'title': tit_raw.strip().rstrip('.'),
            'site_name': site_raw,
            'city': city,
            'date_str': date_str,
            'year': year,
            'url': url,
            'access_date': access_date
        }

    aut_raw, tit_raw = split_author_and_title(line)
    site_name = ""
    site_match = re.search(r'\b(Portal|Site|Blog)\s+[\w\s]+', line, re.I)
    if site_match:
        site_name = site_match.group(0).split(',')[0].strip()
        
    y_match = re.search(r'\b(19\d\d|20\d\d)\b', line)
    year = y_match.group(1) if y_match else ""
    
    return {
        'item_type': 'website',
        'authors': parse_authors(aut_raw),
        'title': tit_raw.strip().rstrip('.'),
        'site_name': site_name,
        'city': '',
        'date_str': '',
        'year': year,
        'url': url,
        'access_date': access_date
    }


def parse_raw_citation_text(text: str) -> dict:
    """
    Analisa uma citação em texto bruto e identifica com precisão os 10 modelos ABNT NBR 6023:2018:
    1. Legislação (Leis, Decretos)
    2. Anais de Simpósios/Eventos (In: Evento)
    3. Capítulos de Livros (In: Autor)
    4. Teses, Dissertações e TCCs
    5. Patentes
    6. Artigos de Jornal / Revista
    7. Documentos Institucionais / DSpace
    8. Livros Inteiros (com autor, org., ed., etc.)
    9. Artigos de Periódicos Científicos
    10. Websites / Documentos Eletrônicos
    """
    raw_line = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'\2', text.strip())
    raw_line = raw_line.replace('\\_', '_')
    if not raw_line:
        return {}
        
    doi_match = DOI_REGEX.search(raw_line)
    doi = doi_match.group(0).rstrip('.') if doi_match else ''
    
    isbn = extract_isbn(raw_line)
    
    urls = [m.group(0).rstrip('.>,;') for m in URL_REGEX.finditer(raw_line)]
    url = next((u for u in urls if not re.match(r'https?://(?:dx\.)?doi.org/', u, re.I)), '')

    acc_match = re.search(r'Acesso em:\s*(\d{1,2}\s+[a-z]+\.?\s*\d{4})', raw_line, re.I)
    access_date = acc_match.group(1).strip() if acc_match else ''

    line = re.sub(r'Dispon[ií]vel em:.*', '', raw_line, flags=re.I).strip()
    line = re.sub(r'Acesso em:.*', '', line, flags=re.I).strip().rstrip('.')
    line = re.sub(r'\s+DOI:.*$', '', line, flags=re.I).strip().rstrip('.')

    detected = identify_input_type(raw_line)
    if detected.get("type") in ("doi", "isbn") or (detected.get("type") == "url" and ("doi.org" in raw_line or "10." in raw_line)):
        return {'doi': doi, 'isbn': isbn, 'url': url, 'access_date': access_date}

    line_no_id = re.sub(r'https?://[^\s)]+|10\.\d{4,9}/[-._;()/:A-Z0-9]+', '', line).strip()
    if not line_no_id or line == isbn or line == doi:
        return {'doi': doi, 'isbn': isbn, 'url': url, 'access_date': access_date}

    before_in = ""
    after_in = ""
    if " In: " in line or " in: " in line or line.startswith("In:"):
        split_token = " In: " if " In: " in line else (" in: " if " in: " in line else "In:")
        parts = line.split(split_token, 1)
        before_in = parts[0].strip()
        after_in = parts[1].strip()

    item_type = detect_reference_type(line, after_in=after_in)

    if item_type in {'legislation', 'bill'}:
        request = parse_legal_request(line)
        if request:
            meta = {'url': url, 'access_date': access_date}
            # Keep supplied ementa/publication information only when the full
            # signature date was recognized by the existing citation parser.
            if item_type == 'legislation' and re.search(r'de\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}', line, re.I):
                supplied = _parse_legislation(line, url, access_date)
                if supplied['title'] != 'Lei':
                    meta.update(supplied)
            meta.update(request)
            if request.get('jurisdiction'):
                meta['authors'] = [{'family': request['jurisdiction'], 'given': '', 'is_corporate': True}]
            return meta
        return _parse_legislation(line, url, access_date)
    elif item_type == 'patent':
        return _parse_patent(line, url, access_date)
    elif item_type == 'thesis':
        return _parse_thesis(line, url, access_date)
    elif item_type == 'proceedings':
        return _parse_proceedings(line, before_in, after_in, doi, isbn, url, access_date)
    elif item_type == 'chapter':
        return _parse_chapter(line, before_in, after_in, doi, isbn, url, access_date)
    elif item_type == 'newspaperArticle':
        return _parse_newspaper(line, url, access_date)
    elif item_type == 'journalArticle':
        return _parse_journal(line, doi, isbn, url, access_date)
    elif item_type == 'website':
        return _parse_website(line, url, access_date)
    elif item_type in ('book', 'legal'):
        return _parse_book(line, isbn, doi, url, access_date)
    else:
        return _parse_book(line, isbn, doi, url, access_date)


def identify_input_type(raw_input: str) -> dict:
    """
    Identifica se a entrada é um DOI puro, ISBN puro, URL pura ou texto livre de citação.
    Retorna um dicionário com o tipo e a chave extraída.
    """
    clean_input = raw_input.strip()
    
    # Se tem estrutura óbvia de citação completa (autores em caixa alta, vários pontos, etc.)
    has_citation_structure = (";" in clean_input or len(clean_input.split('. ')) >= 2) and len(clean_input) > 40
    
    doi_match = DOI_REGEX.search(clean_input)
    if doi_match and not has_citation_structure and (len(clean_input) < 120 or "doi.org" in clean_input):
        doi = doi_match.group(0).rstrip('.')
        return {"type": "doi", "query": doi}
    
    isbn_clean = extract_isbn(clean_input)
    if not has_citation_structure and len(clean_input) <= 35:
        if (len(isbn_clean) == 10 or len(isbn_clean) == 13) and (isbn_clean[:-1].isdigit()):
            return {"type": "isbn", "query": isbn_clean}
    
    url_match = URL_REGEX.search(clean_input)
    if url_match and not has_citation_structure and len(clean_input) < 150 and not "." in clean_input.split("http")[0]:
        return {"type": "url", "query": url_match.group(0)}
    
    return {"type": "text", "query": clean_input}
