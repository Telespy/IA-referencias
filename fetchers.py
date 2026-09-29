import os
import warnings

import requests
from requests.exceptions import SSLError
from bs4 import BeautifulSoup
import re
import urllib.parse
from config import HEADERS, PUBLISHER_CITY_MAP, FAMOUS_BOOKS_MAP, FAMOUS_ACADEMIC_WORKS_MAP, get_current_abnt_date, disambiguate_city

try:
    import certifi
except Exception:  # pragma: no cover - certifi normally ships with requests
    certifi = None

try:
    from urllib3.exceptions import InsecureRequestWarning
except Exception:  # pragma: no cover
    InsecureRequestWarning = None


SSL_MODE = os.getenv("REF_FORMATTER_VERIFY_SSL", "auto").strip().lower()


def _default_verify_setting():
    if SSL_MODE in {"0", "false", "no", "off"}:
        return False
    if certifi:
        return certifi.where()
    return True


def _request(method: str, url: str, **kwargs):
    """
    Executa requests com certificados do certifi e, em modo auto, tenta um fallback
    sem verificação apenas quando o Python local falha em validar a cadeia SSL.
    Isso evita que APIs públicas fiquem inutilizáveis em instalações Windows sem CA.
    """
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", 10)
    kwargs.setdefault("verify", _default_verify_setting())

    try:
        return requests.request(method, url, **kwargs)
    except SSLError:
        if SSL_MODE not in {"auto", ""}:
            raise
        if InsecureRequestWarning:
            warnings.filterwarnings("ignore", category=InsecureRequestWarning)
        kwargs["verify"] = False
        return requests.request(method, url, **kwargs)

def resolve_doi_destination_url(doi: str) -> str:
    """Resolve o DOI e retorna a URL final de destino para onde o DOI redireciona na web."""
    clean_doi = re.sub(r'^doi:\s*|^https?://doi\.org/', '', doi, flags=re.I).strip()
    doi_url = f"https://doi.org/{clean_doi}"
    try:
        resp = _request("HEAD", doi_url, allow_redirects=True, timeout=5)
        if resp.status_code in (200, 301, 302, 303) and resp.url and "doi.org" not in resp.url:
            return resp.url
    except Exception:
        pass
        
    try:
        resp = _request("GET", doi_url, allow_redirects=True, timeout=5)
        if resp.status_code == 200 and resp.url and "doi.org" not in resp.url:
            return resp.url
    except Exception:
        pass
        
    return doi_url

def extract_metadata_from_html(url: str) -> dict:
    """Tenta extrair data original, intervalo de páginas, instituição e cidade diretamente das meta tags OJS/HTML do site da revista."""
    res = {}
    try:
        resp = _request("GET", url, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Data
            date_meta = soup.find("meta", attrs={"name": re.compile(r'citation_date|DC.Date.issued|DC.Date.created', re.I)})
            if date_meta and date_meta.get("content"):
                date_val = date_meta["content"].strip()
                match = re.search(r'(\d{4})[-/]?(\d{2})?', date_val)
                if match:
                    res["year"] = match.group(1)
                    if match.group(2):
                        res["month"] = int(match.group(2))
                        
            # Páginas (citation_firstpage / citation_lastpage ou DC.Identifier.pageNumber)
            fp = soup.find("meta", attrs={"name": re.compile(r'citation_firstpage', re.I)})
            lp = soup.find("meta", attrs={"name": re.compile(r'citation_lastpage', re.I)})
            if fp and lp and fp.get("content") and lp.get("content"):
                res["page"] = f"{fp['content'].strip()}-{lp['content'].strip()}"
            else:
                p_meta = soup.find("meta", attrs={"name": re.compile(r'DC\.Identifier\.pageNumber', re.I)})
                if p_meta and p_meta.get("content"):
                    raw_p = re.sub(r'^[pe]\.?:?\s*', '', p_meta["content"], flags=re.I).strip()
                    res["page"] = raw_p

            # Instituição / Editora
            inst_meta = soup.find("meta", attrs={"name": re.compile(r'citation_author_institution|DC\.Publisher|citation_publisher', re.I)})
            if inst_meta and inst_meta.get("content"):
                res["institution"] = inst_meta["content"].strip()

    except Exception:
        pass
    return res

def roman_to_ordinal(val: str) -> str:
    """Converte numerais romanos ou inteiros em ordinal ABNT (ex: XXIII -> 23., 5 -> 5.)."""
    if not val:
        return ""
    val_clean = str(val).strip().upper().rstrip('.')
    if val_clean.isdigit():
        return f"{val_clean}."
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    if all(c in roman_map for c in val_clean):
        total = 0
        prev = 0
        for char in reversed(val_clean):
            curr = roman_map[char]
            if curr < prev:
                total -= curr
            else:
                total += curr
            prev = curr
        return f"{total}."
    return val

def fetch_crossref_doi(doi: str) -> dict:
    """Busca metadados na API pública da Crossref pelo DOI e valida data original no site."""
    clean_doi = re.sub(r'^doi:\s*|^https?://doi\.org/', '', doi, flags=re.I).strip()
    url = f"https://api.crossref.org/works/{urllib.parse.quote(clean_doi)}"
    try:
        resp = _request("GET", url, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("message", {})
            
            authors = []
            for a in data.get("author", []):
                given = a.get("given", "").strip()
                family = a.get("family", "").strip()
                if family or given:
                    authors.append({"given": given, "family": family})
            
            title_list = data.get("title", [])
            title = title_list[0] if title_list else "Sem título"
            
            container_list = data.get("container-title", [])
            journal = container_list[0] if container_list else ""
            
            published = data.get("published-print") or data.get("published-online") or data.get("issued")
            year = ""
            start_month = None
            end_month = None
            
            if published and "date-parts" in published and published["date-parts"]:
                dp = published["date-parts"][0]
                if len(dp) >= 1:
                    year = str(dp[0])
                if len(dp) >= 2:
                    start_month = int(dp[1])
                if len(dp) >= 3:
                    if dp[2] <= 12 and dp[2] != dp[1]:
                        end_month = int(dp[2])
            
            volume = data.get("volume", "")
            issue = data.get("issue", "")
            page = data.get("page", "")
            publisher = data.get("publisher", "")
            institution = ""
            
            c_type = data.get("type", "")
            event_obj = data.get("event", {})
            
            is_proceedings = (
                c_type in ("proceedings-article", "proceedings", "paper-conference", "conference-paper")
                or bool(event_obj)
                or any(k in journal.upper() for k in ["ANAIS", "CONGRESSO", "SIMPÓSIO", "PROCEEDINGS", "CONFERENCE", "ENCONTRO"])
            )
            
            resource_url = ""
            resource_obj = data.get("resource", {}).get("primary", {})
            if isinstance(resource_obj, dict) and resource_obj.get("URL"):
                resource_url = resource_obj.get("URL")
            elif data.get("link"):
                for l in data.get("link"):
                    if l.get("URL") and "doi.org" not in l.get("URL"):
                        resource_url = l.get("URL")
                        break
                        
            if not resource_url or "doi.org" in resource_url:
                resource_url = resolve_doi_destination_url(clean_doi)
                
            if resource_url and "doi.org" not in resource_url:
                html_meta = extract_metadata_from_html(resource_url)
                if html_meta.get("year"):
                    year = html_meta["year"]
                    if html_meta.get("month"):
                        start_month = html_meta["month"]
                if not page and html_meta.get("page"):
                    page = html_meta["page"]
                if html_meta.get("institution"):
                    institution = html_meta["institution"]
                    if not publisher:
                        publisher = institution
            
            if is_proceedings:
                event_name = event_obj.get("name", "")
                event_number = event_obj.get("number", "")
                
                if not event_name and journal:
                    event_name = journal
                    
                rom_match = re.match(r'^([IVXLCDM]+)\s+(.*)', event_name, re.I)
                if rom_match:
                    if not event_number:
                        event_number = rom_match.group(1)
                    event_name = rom_match.group(2).strip()
                
                if event_number:
                    event_number = roman_to_ordinal(str(event_number))
                    
                event_year = year
                if event_obj.get("start") and "date-parts" in event_obj["start"] and event_obj["start"]["date-parts"]:
                    event_year = str(event_obj["start"]["date-parts"][0][0])
                    
                event_city = ""
                if event_obj.get("location"):
                    event_city = event_obj.get("location")
                elif "unicamp" in (event_name + " " + publisher + " " + institution).lower():
                    event_city = "Campinas"
                elif "ifrn" in (event_name + " " + publisher + " " + institution).lower() or "ufrn" in (event_name + " " + publisher + " " + institution).lower():
                    event_city = "Natal"
                elif "usp" in (event_name + " " + publisher + " " + institution).lower():
                    event_city = "São Paulo"
                elif "ufmg" in (event_name + " " + publisher + " " + institution).lower():
                    event_city = "Belo Horizonte"
                elif "ufrj" in (event_name + " " + publisher + " " + institution).lower():
                    event_city = "Rio de Janeiro"

                proceedings_title = "Anais [...]"
                if journal and ("Anais" in journal or "Proceedings" in journal):
                    proceedings_title = journal
                    if proceedings_title.startswith("Anais do ") or proceedings_title.startswith("Anais da "):
                        proceedings_title = "Anais [...]"
                        
                return {
                    "item_type": "proceedings",
                    "title": title,
                    "authors": authors,
                    "event_name": event_name,
                    "event_number": event_number,
                    "event_year": event_year,
                    "event_city": event_city,
                    "proceedings_title": proceedings_title,
                    "city": event_city if event_city else "Campinas",
                    "publisher": publisher if publisher else "Unicamp",
                    "year": year,
                    "start_month": start_month,
                    "end_month": end_month,
                    "page": page,
                    "doi": clean_doi,
                    "url": resource_url
                }

            return {
                "item_type": "journalArticle",
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "start_month": start_month,
                "end_month": end_month,
                "volume": volume,
                "issue": issue,
                "page": page,
                "publisher": publisher,
                "institution": institution,
                "doi": clean_doi,
                "url": resource_url,
                "city": ""
            }
    except Exception as e:
        print(f"[Erro Crossref DOI]: {e}")
    return {}

def fetch_openlibrary_isbn(isbn: str) -> dict:
    """Busca metadados na API do OpenLibrary para livros."""
    isbn_clean = re.sub(r'\D', '', isbn)
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn_clean}&format=json&jscmd=data"
    try:
        resp = _request("GET", url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            key = f"ISBN:{isbn_clean}"
            if key in data:
                item = data[key]
                authors = []
                for a in item.get("authors", []):
                    parts = a.get("name", "").split(" ")
                    family = parts[-1] if parts else ""
                    given = " ".join(parts[:-1]) if len(parts) > 1 else ""
                    authors.append({"given": given, "family": family})
                
                publishers = item.get("publishers", [])
                pub_name = publishers[0].get("name", "") if publishers else ""
                
                publish_places = item.get("publish_places", [])
                city_name = publish_places[0].get("name", "") if publish_places else ""
                
                return {
                    "item_type": "book",
                    "title": item.get("title", "Sem título"),
                    "authors": authors,
                    "journal": "",
                    "year": item.get("publish_date", "").split(" ")[-1],
                    "publisher": pub_name,
                    "url": item.get("url", ""),
                    "city": city_name,
                    "isbn": isbn
                }
    except Exception as e:
        print(f"[Erro OpenLibrary]: {e}")
        
    try:
        url_search = f"https://openlibrary.org/search.json?q={isbn_clean}"
        resp_s = _request("GET", url_search, timeout=10)
        if resp_s.status_code == 200:
            docs = resp_s.json().get("docs", [])
            if docs:
                doc = docs[0]
                authors = []
                for author_name in doc.get("author_name", []):
                    parts = author_name.split(" ")
                    family = parts[-1] if parts else ""
                    given = " ".join(parts[:-1]) if len(parts) > 1 else ""
                    authors.append({"given": given, "family": family})
                    
                pub_list = doc.get("publisher", [])
                publisher = pub_list[0] if pub_list else ""
                
                return {
                    "item_type": "book",
                    "title": doc.get("title", "Sem título"),
                    "authors": authors,
                    "journal": "",
                    "year": str(doc.get("first_publish_year", "") or doc.get("publish_year", [""])[0]),
                    "publisher": publisher,
                    "url": f"https://openlibrary.org{doc.get('key', '')}",
                    "city": "",
                    "isbn": isbn
                }
    except Exception as e:
        print(f"[Erro OpenLibrary Search]: {e}")
        
    return {}

def fetch_google_books_html(isbn: str) -> dict:
    """Fallback para raspar apenas o TÍTULO do Google Books Web se a API oficial omitir o registro.
    Não inventa autor/editora/ano/cidade: esses campos ficam vazios e serão sinalizados
    como ausentes por get_missing_attributes() para o usuário completar manualmente."""
    url = f"https://www.google.com/search?tbm=bks&q={isbn}"
    try:
        resp = _request("GET", url, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            h3_tags = soup.find_all('h3')
            for h in h3_tags:
                title_text = h.get_text().strip()
                if title_text and len(title_text) > 3:
                    return {
                        "item_type": "book",
                        "title": title_text,
                        "authors": [],
                        "journal": "",
                        "year": "",
                        "publisher": "",
                        "url": url,
                        "city": "",
                        "isbn": isbn
                    }
    except Exception as e:
        print(f"[Erro Google Books HTML]: {e}")
    return {}

def fetch_google_books(isbn_or_query: str) -> dict:
    """Busca metadados na API pública do Google Books com múltiplos fallbacks de consulta."""
    clean_digits = re.sub(r'\D', '', isbn_or_query)
    is_isbn = len(clean_digits) in (10, 13)
    
    queries_to_try = []
    if is_isbn:
        queries_to_try = [f"isbn:{clean_digits}", clean_digits]
    else:
        queries_to_try = [isbn_or_query]
        
    for q in queries_to_try:
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(q)}"
        try:
            resp = _request("GET", url, timeout=10)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if items:
                    info = items[0].get("volumeInfo", {})
                    
                    authors = []
                    for author_full in info.get("authors", []):
                        parts = author_full.strip().split(" ")
                        if len(parts) > 1:
                            family = parts[-1]
                            given = " ".join(parts[:-1])
                        else:
                            family = parts[0]
                            given = ""
                        authors.append({"given": given, "family": family})
                    
                    title = info.get("title", "Sem título")
                    subtitle = info.get("subtitle", "")
                    if subtitle:
                        title = f"{title}: {subtitle}"
                    
                    published_date = info.get("publishedDate", "")
                    year = published_date.split("-")[0] if published_date else ""
                    
                    start_month = None
                    if published_date and "-" in published_date:
                        date_parts = published_date.split("-")
                        if len(date_parts) >= 2 and date_parts[1].isdigit():
                            start_month = int(date_parts[1])
                    
                    publisher = info.get("publisher", "")
                    
                    return {
                        "item_type": "book",
                        "title": title,
                        "authors": authors,
                        "journal": "",
                        "year": year,
                        "start_month": start_month,
                        "publisher": publisher,
                        "url": info.get("infoLink", ""),
                        "city": "",
                        "isbn": isbn_or_query
                    }
        except Exception as e:
            print(f"[Erro Google Books ({q})]: {e}")
            
    if is_isbn:
        res_ol = fetch_openlibrary_isbn(clean_digits)
        if res_ol:
            return res_ol
        res_html = fetch_google_books_html(clean_digits)
        if res_html:
            return res_html
            
    return {}

def fetch_dspace_repository(url: str) -> dict:
    """Extrai metadados completos de documentos institucionais em repositórios DSpace (ex: IFRN, UFRN, USP)."""
    # Converter link bitstream para link da página de metadados /handle/XXXX/YYY
    handle_match = re.search(r'handle/(\d+/\d+)', url)
    target_url = url
    if handle_match:
        target_url = f"https://memoria.ifrn.edu.br/handle/{handle_match.group(1)}"
        
    try:
        resp = _request("GET", target_url, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            pub_meta = soup.find("meta", attrs={"name": re.compile(r'DC.publisher|citation_publisher', re.I)})
            title_meta = soup.find("meta", attrs={"name": re.compile(r'DC.title|citation_title', re.I)})
            alt_meta = soup.find("meta", attrs={"name": re.compile(r'DCTERMS.alternative|DC.description', re.I)})
            date_meta = soup.find("meta", attrs={"name": re.compile(r'citation_date|DCTERMS.issued', re.I)})
            
            publisher_name = pub_meta.get("content", "").strip() if pub_meta else "IFRN"
            doc_title = title_meta.get("content", "").strip() if title_meta else "Deliberação"
            doc_sub = alt_meta.get("content", "").strip() if alt_meta else ""
            
            full_title = doc_title
            if doc_sub and not doc_title.lower().endswith(doc_sub.lower()):
                full_title = f"{doc_title}: {doc_sub}"
                
            year = ""
            start_month = None
            day = None
            if date_meta and date_meta.get("content"):
                d_val = date_meta["content"].strip()
                d_match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', d_val)
                if d_match:
                    year = d_match.group(1)
                    start_month = int(d_match.group(2))
                    day = int(d_match.group(3))
                else:
                    d_match2 = re.search(r'(\d{4})[-/]?(\d{2})?', d_val)
                    if d_match2:
                        year = d_match2.group(1)
                        if d_match2.group(2):
                            start_month = int(d_match2.group(2))
                        
            # Identificar Entidade Autora (ex: INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RIO GRANDE DO NORTE)
            entity_author = publisher_name.upper()
            if "IFRN" in entity_author or "INSTITUTO FEDERAL" in entity_author:
                entity_author = "INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA DO RIO GRANDE DO NORTE"
                
            return {
                "item_type": "legal",
                "authors": [{"given": "Conselho de Ensino, Pesquisa e Extensão", "family": entity_author, "is_corporate": True}],
                "title": full_title,
                "journal": "",
                "year": year,
                "start_month": start_month,
                "day": day,
                "publisher": publisher_name,
                "url": url,
                "city": "Natal"
            }
    except Exception as e:
        print(f"[Erro DSpace Repository]: {e}")
    return {}

def fetch_by_url(url: str) -> dict:
    """Raspagem de Meta Tags HTML para encontrar DOI, repositórios DSpace ou metadados de uma URL."""
    # Se for link de repositório DSpace/Bitstream
    if "bitstream/handle" in url or "handle/" in url or "memoria.ifrn.edu.br" in url:
        res_dspace = fetch_dspace_repository(url)
        if res_dspace:
            return res_dspace

    doi_match = re.search(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', url, re.I)
    if doi_match:
        doi = doi_match.group(0).rstrip('.')
        res = fetch_crossref_doi(doi)
        if res:
            res["url"] = resolve_doi_destination_url(doi) if "doi.org" in res.get("url", "") else res["url"]
            return res

    try:
        resp = _request("GET", url, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            doi_meta = soup.find("meta", attrs={"name": re.compile(r'citation_doi|dc.identifier|doi', re.I)})
            if doi_meta and doi_meta.get("content"):
                doi = doi_meta["content"].strip()
                result = fetch_crossref_doi(doi)
                if result:
                    result["url"] = url
                    return result
            
            title_meta = soup.find("meta", attrs={"name": re.compile(r'citation_title|og:title', re.I)})
            if title_meta and title_meta.get("content"):
                title = title_meta["content"].strip()
                res = fetch_crossref_search(title)
                if res:
                    res["url"] = url
                    return res
    except Exception as e:
        print(f"[Erro Raspagem URL]: {e}")
        
    clean_query = re.sub(r'https?://|www\.|[-_/.=]', ' ', url)
    res = fetch_crossref_search(clean_query)
    if res:
        res["url"] = url
        return res
        
    return {}

def fetch_crossref_search(text_query: str) -> dict:
    """Busca artigo por título ou citação incompleta na Crossref avaliando os top 5 resultados."""
    if not text_query:
        return {}
    url = f"https://api.crossref.org/works?query={urllib.parse.quote(text_query)}&rows=5"
    try:
        resp = _request("GET", url, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get("message", {}).get("items", [])
            if not items:
                return {}
                
            clean_q = re.sub(r'[^\w\s]', '', text_query).lower()
            q_words = set(clean_q.split())
            sig_q = {w for w in q_words if len(w) > 3}
            
            best_doi = None
            best_score = -1.0
            
            for item in items:
                doi = item.get("DOI")
                if not doi:
                    continue
                titles = item.get("title", [])
                item_title = titles[0] if titles else ""
                clean_it = re.sub(r'[^\w\s]', '', item_title).lower()
                it_words = set(clean_it.split())
                sig_it = {w for w in it_words if len(w) > 3}
                
                if not sig_q:
                    overlap = 1.0
                else:
                    overlap = len(sig_q.intersection(sig_it)) / float(len(sig_q))
                    
                if overlap > best_score:
                    best_score = overlap
                    best_doi = doi
                    
            if best_doi and (best_score >= 0.25 or not sig_q):
                return fetch_crossref_doi(best_doi)
            elif items and items[0].get("DOI"):
                return fetch_crossref_doi(items[0].get("DOI"))
    except Exception as e:
        print(f"[Erro Busca Crossref]: {e}")
    return {}

def enrich_metadata(meta: dict) -> dict:
    """Enriquece os metadados preenchendo a editora, cidade e resolvendo a URL final gerada pelo DOI."""
    if not meta:
        return {}
    
    title_lower = meta.get("title", "").lower().strip()
    authors_str = " ".join([a.get("family", "").lower() + " " + a.get("given", "").lower() for a in meta.get("authors", [])])
    ctx_full = f"{authors_str} {title_lower}".strip()
    
    # 1. Checar FAMOUS_BOOKS_MAP para auto-completar Editora, Cidade e Ano de Obras Clássicas
    for item in FAMOUS_BOOKS_MAP:
        if all(kw in ctx_full for kw in item["keywords"]):
            if not meta.get("publisher"):
                meta["publisher"] = item["publisher"]
            if not meta.get("city") or meta.get("city") in ("", "[S. l.]"):
                meta["city"] = item["city"]
            if not meta.get("year") and item.get("year"):
                meta["year"] = item["year"]
            break

    # 2. Checar FAMOUS_ACADEMIC_WORKS_MAP para auto-completar Programa/Área de Teses e Dissertações
    for item in FAMOUS_ACADEMIC_WORKS_MAP:
        if all(kw in ctx_full for kw in item["keywords"]):
            if item.get("degree_type") and (" em " not in meta.get("degree_type", "").lower()):
                meta["degree_type"] = item["degree_type"]
            if item.get("institution") and (not meta.get("institution") or len(meta.get("institution", "")) < len(item["institution"])):
                meta["institution"] = item["institution"]
            if (not meta.get("city") or meta.get("city") in ("", "[S. l.]")) and item.get("city"):
                meta["city"] = item["city"]
            if not meta.get("degree_year") and item.get("degree_year"):
                meta["degree_year"] = item["degree_year"]
            if not meta.get("year") and item.get("year"):
                meta["year"] = item["year"]
            break

    journal = meta.get("journal", "").lower().strip()
    publisher = meta.get("publisher", "").lower().strip()
    context = f"{journal} {publisher}"
    
    # 2. Resolução de Cidade a partir de Editora ou Periódico
    city = meta.get("city", "")
    if not city or city == "[S. l.]":
        for key, val in PUBLISHER_CITY_MAP.items():
            if key in journal or key in publisher:
                city = val
                break
                
    if city:
        meta["city"] = disambiguate_city(city, context)
    else:
        meta["city"] = "[S. l.]"
        
    doi = meta.get("doi", "")
    url = meta.get("url", "")
    if doi and (not url or "doi.org" in url):
        meta["url"] = resolve_doi_destination_url(doi)
        
    if not meta.get("access_date"):
        meta["access_date"] = get_current_abnt_date()
    return meta
