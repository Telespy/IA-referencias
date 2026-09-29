import re
from datetime import datetime
from config import format_date_abnt, format_date_apa, is_english_publication
from publication_places import normalize_place

PROPER_NOUNS = {
    "brasil", "brasília", "rio", "janeiro", "são", "paulo", "natal", "niterói",
    "holos", "apodi", "consepex", "isaac", "asimov"
}

# Siglas, acrônimos e numerais romanos: devem permanecer 100% em maiúsculas
# (ex: "pesquisas da USP", "sequência de DNA", "protocolo IEEE"), nunca em Title Case.
ACRONYMS = {
    "ifrn", "ufrn", "usp", "unicamp", "unesp", "uff", "ufrj",
    "xxi", "xx", "xix", "xviii", "xvii", "xvi", "xv", "xiv", "xiii", "xii", "xi",
    "dna", "rna", "covid-19", "covid", "ieee", "usa", "uk", "doi",
    "abnt", "tcc", "hiv", "aids", "gpu", "gpus", "cpu", "cpus", "ai", "ml", "pnas", "elmo", "cpap"
}

SPECIAL_TERMS = {
    "numpy": "NumPy",
    "scielo": "SciELO",
    "crossref": "Crossref",
}

NAME_PARTICLES = {"da", "de", "del", "der", "di", "do", "dos", "das", "la", "le", "van", "von"}

def format_sentence_case(title: str, is_subtitle: bool = False) -> str:
    """
    Formata títulos de obras em Sentence Case:
    Apenas a primeira palavra do título principal é iniciada em maiúscula.
    O subtítulo após dois pontos (:) permanece em minúscula conforme a ABNT NBR 6023,
    salvo siglas, numerais romanos e nomes próprios.
    Remove pontos finais residuais no título.
    """
    if not title:
        return ""
    
    title_clean = title.strip().rstrip('.')
    
    # Se contiver ':' e não estivermos já processando um subtítulo isolado:
    if ":" in title_clean and not is_subtitle:
        parts = title_clean.split(":", 1)
        main_part = format_sentence_case(parts[0].strip(), is_subtitle=False)
        sub_part = format_sentence_case(parts[1].strip(), is_subtitle=True)
        return f"{main_part}: {sub_part}"
    
    # Se o título estiver em CAIXA ALTA (totalmente, ou em sua maioria — comum em
    # metadados de APIs como Crossref, que às vezes preservam palavras de função
    # em minúsculo mas mantêm o resto em maiúsculo), converte para minúsculas
    # antes de aplicar as regras de capitalização por palavra.
    raw_words = title_clean.split(" ")
    letter_words = [re.sub(r'[^\w-]', '', w) for w in raw_words if re.sub(r'[^\w-]', '', w)]
    upper_words = [w for w in letter_words if w.isupper() and len(w) >= 2]
    if letter_words and (title_clean.isupper() or len(upper_words) / len(letter_words) >= 0.6):
        title_clean = title_clean.lower()
        
    words = title_clean.split(" ")
    formatted_words = []
    
    for idx, word in enumerate(words):
        clean_word = re.sub(r'[^\w-]', '', word)
        c_lower = clean_word.lower()
        
        if c_lower in SPECIAL_TERMS:
            prefix = word[:word.find(clean_word)] if clean_word and clean_word in word else ""
            suffix_start = word.find(clean_word) + len(clean_word) if clean_word and clean_word in word else len(word)
            suffix = word[suffix_start:] if clean_word and clean_word in word else ""
            formatted_words.append(f"{prefix}{SPECIAL_TERMS[c_lower]}{suffix}")
        elif c_lower in ACRONYMS:
            formatted_words.append(word.upper())
        elif c_lower in PROPER_NOUNS:
            formatted_words.append(word.capitalize())
        elif (clean_word.isupper() and len(clean_word) >= 2) or any(c.isupper() for c in clean_word[1:]):
            formatted_words.append(word)
        elif idx == 0 and not is_subtitle:
            formatted_words.append(word.capitalize())
        else:
            formatted_words.append(word.lower())
            
    return " ".join(formatted_words)


def _sentence_with_period(text: str) -> str:
    """Adiciona ponto final apenas quando o trecho não termina com pontuação final."""
    clean = (text or "").strip()
    if not clean:
        return ""
    return clean if clean.endswith((".", "?", "!")) else f"{clean}."


def _format_family_name(family: str) -> str:
    """Capitaliza sobrenomes para APA preservando partículas e nomes já estilizados."""
    if not family:
        return ""
    pieces = []
    for token in family.split():
        lower = token.lower()
        if lower in NAME_PARTICLES:
            pieces.append(lower)
        elif token.isupper() or token.islower():
            pieces.append(token[:1].upper() + token[1:].lower())
        elif any(c.isupper() for c in token[1:]):
            pieces.append(token)
        else:
            pieces.append(token[:1].upper() + token[1:].lower())
    return " ".join(pieces)

def _format_authors_abnt(authors: list) -> str:
    """Formata lista de autores segundo ABNT (SOBRENOME, Nome; SOBRENOME, Nome (org.) ou ENTIDADE. Subórgão)."""
    if not authors:
        return ""
    
    formatted_authors = []
    global_role = ""
    for a in authors:
        family = a.get("family", "").upper()
        given = a.get("given", "")
        role = a.get("role", "")
        if role and not global_role:
            global_role = role
            
        if a.get("is_corporate"):
            if family and given:
                formatted_authors.append(f"{family}. {given}")
            else:
                formatted_authors.append(family or given)
        else:
            if family and given:
                formatted_authors.append(f"{family}, {given}")
            elif family:
                formatted_authors.append(family)
            elif given:
                formatted_authors.append(given.upper())
            
    if len(formatted_authors) > 3 or (authors and authors[0].get('et_al')):
        res = f"{formatted_authors[0]} *et al.*"
    elif len(formatted_authors) == 1:
        res = formatted_authors[0]
    else:
        res = "; ".join(formatted_authors)
        
    if global_role:
        gr_clean = global_role.lower().rstrip('.')
        if 'org' in gr_clean:
            role_label = 'orgs.' if len(formatted_authors) > 1 else 'org.'
        elif 'ed' in gr_clean:
            role_label = 'eds.' if len(formatted_authors) > 1 else 'ed.'
        elif 'coord' in gr_clean:
            role_label = 'coords.' if len(formatted_authors) > 1 else 'coord.'
        elif 'comp' in gr_clean:
            role_label = 'comps.' if len(formatted_authors) > 1 else 'comp.'
        else:
            role_label = f"{gr_clean}."
            
        # Se o autor termina com inicial abreviada (ex: 'TAVARES, A. R.'), preserva o ponto da inicial
        if re.search(r'\b[A-Za-z]\.$', res.strip()):
            res = f"{res.strip()} ({role_label})"
        else:
            res = f"{res.strip().rstrip('.')} ({role_label})"
    else:
        res = res.strip().rstrip('.')
        
    return res

def format_corporate_name(name: str) -> str:
    """Formata nome de entidade corporativa/instituição (ex: INSTITUTO FEDERAL DE EDUCAÇÃO -> Instituto Federal de Educação)."""
    if not name:
        return ""
    words = name.split()
    lower_words = {"de", "do", "da", "dos", "das", "e", "em", "para", "com", "by", "of", "and"}
    res = []
    for idx, w in enumerate(words):
        w_clean = re.sub(r'[^\w]', '', w)
        if idx > 0 and w_clean.lower() in lower_words:
            res.append(w.lower())
        else:
            res.append(w.capitalize())
    return " ".join(res)

def _format_authors_apa(authors: list) -> str:
    """Formata lista de autores segundo APA 7ª Edição (Family, G. M. ou Entidade. Subórgão)."""
    if not authors:
        return ""
    
    formatted_authors = []
    for a in authors:
        family = a.get("family", "")
        given = a.get("given", "")
        if a.get("is_corporate"):
            corp_name = format_corporate_name(family)
            if corp_name and given:
                formatted_authors.append(f"{corp_name}. {given}")
            else:
                formatted_authors.append(corp_name or given)
        else:
            family_cap = _format_family_name(family)
            initials = " ".join([f"{name[0].upper()}." for name in given.split() if name])
            if family_cap and initials:
                formatted_authors.append(f"{family_cap}, {initials}")
            elif family_cap:
                formatted_authors.append(family_cap)
            
    if len(formatted_authors) == 1:
        res = formatted_authors[0]
    elif len(formatted_authors) == 2:
        res = f"{formatted_authors[0]}, & {formatted_authors[1]}"
    elif len(formatted_authors) > 2 and len(formatted_authors) <= 20:
        res = ", ".join(formatted_authors[:-1]) + f", & {formatted_authors[-1]}"
    elif len(formatted_authors) > 20:
        res = ", ".join(formatted_authors[:19]) + f", ... {formatted_authors[-1]}"
    else:
        res = ""
        
    return res.strip()

def _format_page_abnt(page: str) -> str:
    """Formata número de página ou artigo no padrão ABNT."""
    p = page.strip()
    if not p:
        return ""
    
    if re.match(r'^e\d+', p, re.IGNORECASE):
        return p.lower()
        
    if '-' in p or '–' in p or ',' in p:
        return f"p. {p}"
        
    return f"p. {p}"


def _format_pages_apa(page: str) -> str:
    """Formata páginas para APA, distinguindo página única, intervalo e e-location."""
    p = (page or "").strip()
    if not p:
        return ""
    if re.match(r'^e\d+', p, re.I):
        return p
    if '-' in p or '–' in p or ',' in p:
        return f"pp. {p}"
    return f"p. {p}"


def _format_editors_apa(authors: list) -> str:
    """Formata organizadores/editores no trecho In da APA: G. Sobrenome."""
    formatted = []
    for a in authors or []:
        family = a.get("family", "")
        given = a.get("given", "")
        if a.get("is_corporate"):
            name = format_corporate_name(family or given)
        else:
            initials = " ".join([f"{name[0].upper()}." for name in given.split() if name])
            family_cap = _format_family_name(family)
            name = f"{initials} {family_cap}".strip()
        if name:
            formatted.append(name)
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]} & {formatted[1]}"
    if len(formatted) > 2:
        return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"
    return ""


def _normalize_url(url: str) -> str:
    return (url or "").strip().rstrip("/").lower()

def _format_bold_title(raw_title: str) -> str:
    """Apenas o título principal antes dos dois pontos fica em negrito no ABNT NBR 6023!"""
    if not raw_title:
        return ""
    if ":" in raw_title:
        t_main, t_sub = raw_title.split(":", 1)
        return f"**{format_sentence_case(t_main.strip(), is_subtitle=False)}**: {format_sentence_case(t_sub.strip(), is_subtitle=True)}"
    else:
        return f"**{format_sentence_case(raw_title.strip(), is_subtitle=False)}**"

def _case_date_abnt(value):
    try:
        day = datetime.strptime(value, '%d/%m/%Y')
    except ValueError:
        return value
    months = ('jan.', 'fev.', 'mar.', 'abr.', 'maio', 'jun.', 'jul.', 'ago.', 'set.', 'out.', 'nov.', 'dez.')
    return f'{day.day} {months[day.month - 1]} {day.year}'


def format_case_citation(meta):
    if meta.get('item_type') != 'caseLaw' or not meta.get('case_number'):
        return ''
    number = f'{int(meta["case_number"]):,}'.replace(',', '.')
    label = f'{meta.get("case_class", "ADI")} {number}'
    if meta.get('case_suffix'):
        label += f' {meta["case_suffix"]}'
    fields = ['STF', label]
    if meta.get('relator'):
        fields.append(f'Rel. Min. {meta["relator"]}')
    if meta.get('court_body'):
        fields.append(meta['court_body'])
    if meta.get('judgment_date'):
        fields.append(f'j. {meta["judgment_date"]}')
    if meta.get('publication_date'):
        fields.append(f'DJe {meta["publication_date"]}')
    if meta.get('case_page'):
        fields.append(f'p. {meta["case_page"]}')
    return '(' + ', '.join(fields) + ')'


def format_abnt(meta: dict) -> str:
    """Gera referência no padrão ABNT (NBR 6023) para os 10 tipos de documento."""
    if not meta:
        return "Referência não encontrada."
    
    authors_str = _format_authors_abnt(meta.get("authors", []))
    raw_title = meta.get("title", "")
    item_type = meta.get("item_type", "journalArticle")
    year = meta.get("year", "")
    start_month = meta.get("start_month")
    end_month = meta.get("end_month")
    day = meta.get("day")
    month_str = meta.get("month_str", "")
    
    is_eng = is_english_publication(meta)
    
    if month_str:
        if not is_eng:
            month_str_formatted = "/".join([m.strip().lower() for m in month_str.split('/')])
        else:
            month_str_formatted = month_str
        date_abnt = f"{month_str_formatted} {year}".strip()
    else:
        date_abnt = format_date_abnt(year, start_month, end_month, day=day, is_english=is_eng)
    display_date_abnt = date_abnt if date_abnt else "[s. d.]"
        
    city = normalize_place(meta.get("city", "")).value
    if not city:
        city = "[S. l.]"
        
    publisher = meta.get("publisher", "")
    doi = meta.get("doi", "")
    url = meta.get("url", "")
    access_date = meta.get("access_date", "")
    edition = meta.get("edition", "")
    
    parts = []
    
    if item_type == 'caseLaw':
        if meta.get('jurisdiction'):
            parts.append(meta['jurisdiction'].upper() + '.')
        if meta.get('court'):
            parts.append(meta['court'].rstrip('.') + '.')
        if raw_title:
            parts.append(f'**{raw_title.rstrip(".")}**.')
        if meta.get('ementa'):
            parts.append(meta['ementa'].rstrip('.') + '.')
        if meta.get('relator'):
            parts.append(f'Relator: Min. {meta["relator"]},' if meta.get('judgment_date') else f'Relator: Min. {meta["relator"]}.')
        if meta.get('judgment_date'):
            parts.append(f'julgado em {_case_date_abnt(meta["judgment_date"])}.')
        parts.append(f'{city}: {publisher or "[s. n.]"}, [{year}].' if year else f'{city}: {publisher or "[s. n.]"}, [s. d.].')

    # 1. LEGISLAÇÃO (ABNT NBR 6023 Seção 7.3)
    elif item_type in {"legislation", "bill"}:
        jurisdiction = meta.get("jurisdiction", "").upper()
        ementa = meta.get("ementa", "")
        if jurisdiction:
            parts.append(f"{jurisdiction}.")
        if item_type == 'bill' and meta.get('legislative_house'):
            house = {'camara': 'Câmara dos Deputados', 'senado': 'Senado Federal'}.get(meta['legislative_house'], meta['legislative_house'])
            parts.append(f'{house}.')
        if item_type == 'legislation' and meta.get('publication_mode') == 'planalto':
            parts.append(f'**{raw_title.rstrip(".")}**.')
        else:
            parts.append(_sentence_with_period(raw_title))
        if ementa:
            parts.append(_sentence_with_period(ementa))
        if meta.get('publication_title') and meta.get('publication_mode') != 'planalto':
            publication = [f'**{meta["publication_title"]}**', city]
            if meta.get('section'):
                publication.append(f'Seção {meta["section"]}')
            if meta.get('page'):
                publication.append(f'p. {meta["page"]}')
            publication.append(meta.get('publication_date') or year or '[s. d.]')
            parts.append(', '.join(publication) + '.')
        else:
            parts.append(f"{city}: {publisher if publisher else '[s. n.]'}, {year if year else '[s. d.]'}.")
        
    # 2. CAPÍTULO DE LIVRO (In: Autor. Título do livro)
    elif item_type == "chapter":
        if authors_str:
            parts.append(f"{authors_str}.")
        parts.append(_sentence_with_period(format_sentence_case(raw_title)))
        
        b_authors = _format_authors_abnt(meta.get("book_authors", []))
        b_title = _format_bold_title(meta.get("book_title", ""))
        
        in_part = "*In*:"
        if b_authors:
            in_part += f" {b_authors}."
        if b_title:
            in_part += f" {b_title}."
        if edition:
            in_part += f" {edition}"
        parts.append(in_part)
        
        pub_str = publisher if publisher else "[s. n.]"
        pag_str = f". {_format_page_abnt(meta.get('page', ''))}" if meta.get('page') else ""
        parts.append(f"{city}: {pub_str}, {display_date_abnt}{pag_str}.")

    # 3. ANAIS DE SIMPÓSIO / EVENTO
    elif item_type == "proceedings":
        if authors_str:
            parts.append(f"{authors_str}.")
        parts.append(_sentence_with_period(format_sentence_case(raw_title)))
        
        ev_name = meta.get("event_name", "").upper()
        ev_num = meta.get("event_number", "")
        ev_yr = meta.get("event_year", "")
        ev_city = normalize_place(meta.get("event_city", "")).value
        proc_title = meta.get("proceedings_title", "Anais [...]")
        
        ev_info = f"*In*: {ev_name}"
        if ev_num:
            ev_info += f", {ev_num}"
        if ev_yr:
            ev_info += f", {ev_yr}"
        if ev_city:
            ev_info += f", {ev_city}"
        ev_info += f". **{proc_title}**"
        parts.append(ev_info)
        
        pub_str = publisher if publisher else "[s. n.]"
        pag_str = f". {_format_page_abnt(meta.get('page', ''))}" if meta.get('page') else ""
        parts.append(f"{city}: {pub_str}, {display_date_abnt}{pag_str}.")

    # 4. TESE / DISSERTAÇÃO / TCC / TRABALHO ACADÊMICO (ABNT NBR 6023 Seção 7.8)
    elif item_type == "thesis":
        if authors_str:
            parts.append(f"{authors_str}.")
        parts.append(f"{_format_bold_title(raw_title)}.")
        
        deg_yr = meta.get("degree_year") or year
        deg_tp = meta.get("degree_type", "Tese (Doutorado)")
        inst = meta.get("institution", "")
        
        if deg_yr:
            parts.append(f"{deg_yr}.")
            
        inst_city_str = f"{inst}, {city}" if inst and city and city != "[S. l.]" else (inst or city or "[S. l.]")
        year_str = f", {year}" if year else ""
        info = f"{deg_tp} – {inst_city_str}{year_str}."
        parts.append(info)

    # 5. PATENTE
    elif item_type == "patent":
        if authors_str:
            parts.append(f"{authors_str}.")
        parts.append(f"{_format_bold_title(raw_title)}.")
        patent_no = meta.get("patent_no", "")
        dep_info = meta.get("deposit_info", "")
        conc_info = meta.get("concession_info", "")
        parts.append(f"{patent_no}.")
        if dep_info:
            parts.append(f"{dep_info}")
        if conc_info:
            parts.append(f"{conc_info}")

    # 6. ARTIGO DE JORNAL / REVISTA
    elif item_type == "newspaperArticle":
        if authors_str:
            parts.append(f"{authors_str}.")
        parts.append(_sentence_with_period(format_sentence_case(raw_title)))
        newspaper = meta.get("newspaper", "")
        dt_str = meta.get("date_str", date_abnt) or "[s. d.]"
        sec = meta.get("section", "")
        pag = meta.get("page", "")
        
        j_part = f"**{newspaper}**, {city}, {dt_str}."
        if sec:
            j_part += f" {sec}."
        if pag:
            j_part += f" p. {pag}."
        parts.append(j_part)

    # 7. WEBSITE / PÁGINA WEB (ABNT NBR 6023 Seção 7.15)
    elif item_type == "website":
        if authors_str:
            parts.append(f"{authors_str}.")
        parts.append(f"{_format_bold_title(raw_title)}.")
        site = meta.get("site_name", "")
        dt_str = meta.get("date_str", "") or display_date_abnt
        site_city = city
        if site:
            parts.append(f"{site},")
        parts.append(f"{site_city}, {dt_str}.")

    # 8. LIVRO INTEIRO
    elif item_type == "book":
        if authors_str:
            parts.append(f"{authors_str}.")
        parts.append(f"{_format_bold_title(raw_title)}.")
        if edition:
            parts.append(f"{edition}")
        pub_str = publisher if publisher else "[s. n.]"
        if date_abnt:
            parts.append(f"{city}: {pub_str}, {date_abnt}.")
        else:
            parts.append(f"{city}: {pub_str}, [s. d.].")
        
    # 9. DOCUMENTO INSTITUCIONAL / ACTO LEGAL
    elif item_type == "legal":
        if authors_str:
            parts.append(f"{authors_str}.")
        parts.append(f"{_format_bold_title(raw_title)}.")
        if publisher:
            parts.append(f"{city}: {publisher}, {display_date_abnt}.")
        else:
            parts.append(f"{city}, {display_date_abnt}.")
            
    # 10. ARTIGO DE PERIÓDICO CIENTÍFICO (Padrão)
    else:
        if authors_str:
            parts.append(f"{authors_str}.")
            
        title = format_sentence_case(raw_title)
        journal = meta.get("journal", "")
        volume = meta.get("volume", "")
        issue = meta.get("issue", "")
        raw_page = meta.get("page", "")
        page_str = _format_page_abnt(raw_page)
        
        parts.append(_sentence_with_period(title))
        if journal:
            parts.append(f"**{journal}**,")
        parts.append(f"{city},")
        if volume:
            parts.append(f"v. {volume},")
        if issue:
            parts.append(f"n. {issue},")
        if page_str:
            parts.append(f"{page_str},")
        if date_abnt:
            parts.append(f"{date_abnt}.")
        else:
            parts.append("[s. d.].")
            
    # DOI
    doi_link = ""
    if doi:
        clean_doi = re.sub(r'^doi:\s*|^https?://doi\.org/', '', doi, flags=re.I).strip()
        doi_link = f"https://doi.org/{clean_doi}"
        parts.append(f"DOI: [{doi_link}]({doi_link}).")
        
    # Disponível em: e Acesso em:
    if url and _normalize_url(url) != _normalize_url(doi_link):
        parts.append(f"Disponível em: [{url}]({url}).")
    if (url or doi_link) and access_date:
        parts.append(f"Acesso em: {access_date}.")
        
    res = " ".join(parts).replace(" ,", ",").replace(" .", ".")
    res = res.replace('*et al.*.', '*et al.*')
    res = re.sub(r'([^\.])\.\.(?!\.)', r'\1.', res)
    
    return res

def format_apa(meta: dict) -> str:
    """Gera referência no padrão APA (7ª Edição) para todos os tipos de documento."""
    if not meta:
        return "Reference not found."
    if meta.get('item_type') == 'caseLaw':
        return format_abnt(meta)
    
    authors_str = _format_authors_apa(meta.get("authors", []))
    raw_title = meta.get("title", "")
    item_type = meta.get("item_type", "journalArticle")
    year = meta.get("year", "")
    start_month = meta.get("start_month")
    end_month = meta.get("end_month")
    day = meta.get("day")
    
    date_apa = format_date_apa(year, start_month, end_month, day=day)
    if item_type == "journalArticle":
        date_apa = str(year) if year else "n.d."
    doi = meta.get("doi", "")
    url = meta.get("url", "")
    publisher = meta.get("publisher", "")
    edition = meta.get("edition", "")
    
    parts = []
    if authors_str:
        parts.append(f"{authors_str}")
    elif item_type in {"legislation", "bill"} and meta.get('jurisdiction'):
        parts.append(format_corporate_name(meta['jurisdiction']))
    elif item_type == "website" and meta.get("site_name"):
        parts.append(meta.get("site_name"))

    has_leading_agent = bool(parts)
    if has_leading_agent:
        parts.append(f"({date_apa}).")
    
    if item_type in {"legislation", "bill"}:
        ementa = meta.get("ementa", "")
        title_str = f"*{raw_title}" + (f": {ementa.rstrip('.')}" if ementa else '') + '*'
        parts.append(f"{title_str}.")
        if publisher:
            parts.append(f"{publisher}.")
    elif item_type == "book":
        title = format_sentence_case(raw_title)
        if edition:
            parts.append(f"*{title}* ({edition}).")
        else:
            parts.append(f"*{title}*.")
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
        if publisher:
            parts.append(f"{publisher}.")
    elif item_type == "legal":
        if ":" in raw_title:
            t_main, t_sub = raw_title.split(":", 1)
            title = f"{t_main.strip()}: {format_sentence_case(t_sub.strip())}"
        else:
            title = format_sentence_case(raw_title)
        parts.append(f"*{title}*.")
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
        if publisher:
            parts.append(f"{publisher}.")
    elif item_type == "chapter":
        title = format_sentence_case(raw_title)
        parts.append(_sentence_with_period(title))
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
        book_authors = _format_editors_apa(meta.get("book_authors", []))
        book_title = format_sentence_case(meta.get("book_title", ""))
        page = _format_pages_apa(meta.get("page", ""))
        in_part = "In"
        if book_authors:
            in_part += f" {book_authors}"
            role = ""
            for author in meta.get("book_authors", []):
                if author.get("role"):
                    role = author["role"].lower()
                    break
            role_label = "Orgs." if "org" in role or "coord" in role else "Eds."
            if len(meta.get("book_authors", [])) == 1:
                role_label = "Org." if "org" in role or "coord" in role else "Ed."
            in_part += f" ({role_label}),"
        if book_title:
            in_part += f" *{book_title}*"
        extras = []
        if edition:
            extras.append(edition)
        if page:
            extras.append(page)
        if extras:
            in_part += f" ({'; '.join(extras)})"
        parts.append(f"{in_part}.")
        if publisher:
            parts.append(f"{publisher}.")
    elif item_type == "proceedings":
        title = format_sentence_case(raw_title)
        parts.append(_sentence_with_period(title))
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
        proc_title = meta.get("proceedings_title", "")
        event_name = meta.get("event_name", "")
        page = _format_pages_apa(meta.get("page", ""))
        proc_part = ""
        if proc_title:
            proc_part = f"*{proc_title}*"
        elif event_name:
            proc_part = f"*{event_name}*"
        if page and proc_part:
            proc_part += f" ({page})"
        if proc_part:
            parts.append(f"{proc_part}.")
        if publisher:
            parts.append(f"{publisher}.")
    elif item_type == "thesis":
        title = format_sentence_case(raw_title)
        degree_type = meta.get("degree_type", "Tese (Doutorado)")
        institution = meta.get("institution", "")
        bracket = degree_type
        if institution:
            bracket += f", {institution}"
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
        parts.append(f"*{title}* [{bracket}].")
    elif item_type == "patent":
        title = format_sentence_case(raw_title)
        patent_no = meta.get("patent_no", "")
        if patent_no:
            parts.append(f"*{title}* ({patent_no}).")
        else:
            parts.append(f"*{title}*.")
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
    elif item_type == "newspaperArticle":
        title = format_sentence_case(raw_title)
        newspaper = meta.get("newspaper", "")
        page = _format_pages_apa(meta.get("page", ""))
        section = meta.get("section", "")
        parts.append(_sentence_with_period(title))
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
        if newspaper:
            news_part = f"*{newspaper}*"
            details = ", ".join([x for x in [section, page] if x])
            if details:
                news_part += f", {details}"
            parts.append(f"{news_part}.")
    elif item_type == "website":
        title = format_sentence_case(raw_title)
        site = meta.get("site_name", "")
        parts.append(f"*{title}*.")
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
        if site and (not authors_str or site.lower() not in " ".join(parts).lower()):
            parts.append(f"{site}.")
    else:
        # Artigo de Periódico
        title = format_sentence_case(raw_title)
        journal = meta.get("journal", "")
        volume = meta.get("volume", "")
        issue = meta.get("issue", "")
        page = meta.get("page", "")
        
        parts.append(_sentence_with_period(title))
        if not has_leading_agent:
            parts.append(f"({date_apa}).")
        if journal:
            journal_str = f"*{journal}*"
            if volume:
                journal_str += f", *{volume}*"
            if issue:
                journal_str += f"({issue})"
            if page:
                journal_str += f", {page}"
            parts.append(f"{journal_str}.")
            
    if doi:
        clean_doi = re.sub(r'^doi:\s*|^https?://doi\.org/', '', doi, flags=re.I).strip()
        doi_link = f"https://doi.org/{clean_doi}"
        parts.append(f"[{doi_link}]({doi_link})")
    elif url:
        parts.append(f"[{url}]({url})")
        
    res = " ".join(parts)
    res = re.sub(r' (?=\.(?!\.))', '', res)
    res = re.sub(r'(?<!\.)\.\s+\.(?!\.)', '.', res)
    
    return res

ITEM_TYPE_LABELS = {
    "journalArticle": "📄 Artigo de Periódico Científico",
    "book": "📖 Livro",
    "chapter": "📑 Capítulo de Livro",
    "proceedings": "🏛️ Trabalho em Evento / Anais de Congresso",
    "thesis": "🎓 Tese / Dissertação / TCC",
    "legislation": "⚖️ Legislação / Ato Normativo",
    "bill": "Projeto de lei",
    "unknown": "Identificação pendente",
    "legal": "🏛️ Documento Institucional / Governamental",
    "patent": "💡 Patente",
    "newspaperArticle": "📰 Artigo de Jornal / Revista",
    "website": "🌐 Website / Documento Eletrônico",
}

def get_item_type_label(item_type: str) -> str:
    """Retorna o nome legível e formatado do tipo de referência."""
    return 'Julgado / Acórdão' if item_type == 'caseLaw' else ITEM_TYPE_LABELS.get(item_type, "📄 Artigo / Obra Geral")

def get_missing_attributes(meta: dict) -> list:
    """
    Analisa os metadados e retorna uma lista de elementos faltantes segundo a ABNT NBR 6023.
    Se todos os elementos principais estiverem presentes, retorna lista vazia.
    """
    if not meta:
        return ["Dados da referência não encontrados"]
        
    missing = []
    item_type = meta.get("item_type", "journalArticle")
    
    authors = meta.get("authors", [])
    title = meta.get("title", "")
    city = meta.get("city", "")
    year = meta.get("year", "")
    publisher = meta.get("publisher", "")
    url = meta.get("url", "")
    page = meta.get("page", "")
    volume = meta.get("volume", "")
    issue = meta.get("issue", "")
    
    # Autores e Título são universais
    if not authors:
        missing.append("Autor(es) / Entidade responsável")
    if not title:
        missing.append("Título da obra")
    if not city or city == "[S. l.]":
        missing.append("Cidade de publicação (atribuído [S. l.])")
    if not year:
        missing.append("Ano de publicação")

    # Regras específicas por tipo de documento segundo ABNT NBR 6023:2018
    if item_type == 'caseLaw':
        for field, label in (('case_state', 'UF do processo'), ('ementa', 'Ementa do acórdão'),
                             ('relator', 'Relator'), ('court_body', 'Órgão julgador'),
                             ('judgment_date', 'Data do julgamento'),
                             ('publication_date', 'Data de publicação no DJe'),
                             ('url', 'Link oficial do inteiro teor')):
            if not meta.get(field):
                missing.append(label)
    elif item_type == "journalArticle":
        journal = meta.get("journal", "")
        if not journal:
            missing.append("Nome do periódico/revista")
        if not volume and not issue:
            missing.append("Volume ou Número do periódico (v. / n.)")
        if not page:
            missing.append("Intervalo de páginas (p.)")
        if not meta.get("doi") and not url and not (page and (volume or issue)):
            missing.append("DOI ou URL de acesso ao artigo")

    elif item_type == "book":
        if not publisher or publisher == "[s. n.]":
            missing.append("Nome da editora")

    elif item_type == "chapter":
        book_title = meta.get("book_title", "")
        book_authors = meta.get("book_authors", [])
        if not book_title:
            missing.append("Título do livro (obra principal)")
        if not book_authors:
            missing.append("Autor(es) ou Organizador(es) do livro")
        if not publisher or publisher == "[s. n.]":
            missing.append("Nome da editora")
        if not page:
            missing.append("Intervalo de páginas do capítulo (p. X-Y)")

    elif item_type == "proceedings":
        event_name = meta.get("event_name", "")
        if not event_name:
            missing.append("Nome do evento/congresso")
        if not publisher or publisher == "[s. n.]":
            missing.append("Editora/Organização dos anais")
        if not page:
            missing.append("Intervalo de páginas do trabalho (p. X-Y)")
        if not meta.get("doi") and not url:
            missing.append("DOI ou URL de acesso aos anais")

    elif item_type == "thesis":
        institution = meta.get("institution", "")
        degree_type = meta.get("degree_type", "")
        if not institution:
            missing.append("Nome da instituição de ensino/pesquisa (Universidade/Faculdade)")
        if not degree_type:
            missing.append("Grau acadêmico (Tese/Dissertação/TCC)")
        elif " em " not in degree_type.lower() and " de " not in degree_type.lower():
            # ABNT NBR 6023 Item 7.8 exige grau e área de concentração/programa
            missing.append("Área de concentração / Programa do trabalho acadêmico (ex: Doutorado em Filosofia da Educação)")

    elif item_type == "website":
        site_name = meta.get("site_name", "")
        if not site_name:
            missing.append("Nome do site/portal")
        if not url:
            missing.append("URL de acesso à página")
        if not meta.get("access_date"):
            missing.append("Data de acesso (Acesso em: dia mês. ano)")

    elif item_type == "newspaperArticle":
        newspaper = meta.get("newspaper", "")
        section = meta.get("section", "")
        if not newspaper:
            missing.append("Nome do jornal")
        if not page and not section:
            missing.append("Página ou Seção do jornal")

    elif item_type in {"legislation", "bill"}:
        ementa = meta.get("ementa", "")
        if not ementa:
            missing.append("Ementa da lei/decreto")
        if not url:
            missing.append("Link oficial de publicação da lei")
        if not meta.get('legal_number'):
            missing.append('Numero da norma/projeto')
        if not meta.get('legal_year'):
            missing.append('Ano da norma/projeto')
        if item_type == 'bill':
            if not meta.get('legislative_house'):
                missing.append('Casa legislativa')
            if not publisher:
                missing.append('Orgao de publicacao do projeto')
        elif meta.get('publication_mode') == 'planalto':
            if not publisher:
                missing.append('Orgao responsavel pela pagina oficial')
        elif not meta.get('publication_title') or not meta.get('publication_date'):
            missing.append('Veiculo e data de publicacao oficial')

    elif item_type == "legal":
        if not publisher:
            missing.append("Órgão / Instituição responsável")
        if not url:
            missing.append("Link de acesso ao documento institucional")

    elif item_type == "patent":
        if not meta.get("patent_no"):
            missing.append("Número de registro da patente (ex: BR 10...)")
        if not meta.get("deposit_info"):
            missing.append("Data de depósito da patente")
            
    return missing
