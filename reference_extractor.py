"""Extração de referências a partir de documentos (DOCX, PDF, TXT e MD).

Este módulo não consulta fontes externas. Ele localiza a seção de referências,
separa as entradas, extrai identificadores e cruza as citações do corpo do texto
com a lista final. A verificação bibliográfica continua em `/api/format`.
"""
import io
import re
import unicodedata
import zipfile

from defusedxml import ElementTree as SafeET
from pypdf import PdfReader

from parsers import DOI_REGEX, URL_REGEX, extract_isbn

SUPPORTED_EXTENSIONS = {'.docx', '.pdf', '.txt', '.md'}
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
WORD_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

REFERENCE_HEADINGS = {'referencias', 'referencias bibliograficas', 'bibliografia'}
# Título de apêndice ou anexo com identificador: 'APÊNDICE B – Tabela', 'ANEXO A'.
END_HEADING_RE = re.compile(r"^(?:AP[ÊE]NDICE|ANEXO|GLOSS[ÁA]RIO|[ÍI]NDICE)S?\b", re.IGNORECASE)

# Autor em caixa alta seguido de vírgula e nome: "SILVA, Maria" ou "DA SILVA, João".
AUTHOR_START = re.compile(r"^[A-ZÀ-Ý][A-ZÀ-Ý'\-]+(?:\s+[A-ZÀ-Ý][A-ZÀ-Ý'\-]+)*,\s+[A-ZÀ-Ýa-zà-ÿ]")
# Entidade ou título em caixa alta seguido de ponto: "BRASIL. Lei ..." ou "ABNT. NBR ...".
ENTITY_START = re.compile(r"^[A-ZÀ-Ý][A-ZÀ-Ý\s.\-&]{1,}\.\s")
# Traço que substitui o nome de autor repetido: "___. Título".
REPEATED_AUTHOR_START = re.compile(r"^[_\-—–]{3,}")
YEAR_RE = re.compile(r"\b[c©]?(1[89]\d{2}|20\d{2})[a-z]?\b")
PARENTHETICAL_RE = re.compile(r"\(([^()]{2,250})\)")
NARRATIVE_RE = re.compile(r"((?:[A-ZÀ-Ý][\wÀ-ÿ\'\-]+(?:\s+e\s+|\s+|\s*;\s*)){0,3}[A-ZÀ-Ý][\wÀ-ÿ\'\-]+)(?:\s+et\s+al\.)?\s*\((?:[c©]?)(\d{4})[a-z]?(?:,\s*p+\.?\s*[\d\-]+)?\)")
# Rótulo copiado de gerenciador antes da referência: "Barros, 2021 BARROS, José ..." ou "Alencar; Monti, 2021 <= ... ALENCAR, ...".
LABEL_PREFIX_RE = re.compile(r"^(?:[^\n.]|\bal\.){1,120}?[,;]\s*\d{4}[a-z]?\.?\s+(?:<=\s+(?:[^\n.]|\bal\.){1,160}?\d{4}[a-z]?\.?\s+)*(?=[A-ZÀ-Ý][A-ZÀ-Ý\'\-]+[,.\s])")
# Palavras iniciais de frase que não são sobrenome, como em 'Segundo Silva (2019)'.
SENTENCE_STARTERS = {"segundo", "conforme", "para", "ja", "como", "sobre", "em", "no", "na", "nos", "nas", "por",
                     "ver", "apud", "este", "esta", "esse", "essa", "assim", "tambem", "ainda", "vide", "cf", "ao",
                     "pelo", "pela", "quanto", "novo", "nova"}
ACCESS_RE = re.compile(r"Acesso em:\s*(\d{1,2}\s+[a-zç]+\.?\s*\d{4})", re.IGNORECASE)
TOC_LINE_RE = re.compile(r"\.{3,}|\s\d+$")


def _fold(text: str) -> str:
    """Minúsculas, sem acentos e sem numeração de seção (ex.: '5 REFERÊNCIAS' -> 'referencias')."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"^\d+(?:\.\d+)*\s+", "", text.strip())
    return re.sub(r"\s+", " ", text).strip(" :.")


def read_document(filename: str, content: bytes) -> tuple[list[str], bool]:
    """Lê o documento e devolve (linhas, parágrafo_é_entrada).

    No DOCX cada parágrafo do Word é uma entrada, pois o Word preserva a
    recuperação de linha da referência. Em PDF e TXT as entradas são inferidas.
    """
    name = (filename or "").lower()
    ext = next((e for e in SUPPORTED_EXTENSIONS if name.endswith(e)), "")
    if not ext:
        raise ValueError("Formato não suportado. Envie .docx, .pdf, .txt ou .md.")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("Arquivo acima de 10 MB.")
    if ext == ".docx":
        return _read_docx(content), True
    if ext == ".pdf":
        return _read_pdf(content), False
    return content.decode("utf-8-sig", errors="replace").splitlines(), False


def _read_docx(content: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError("Arquivo DOCX inválido.") from exc
    root = SafeET.fromstring(xml_bytes)
    paragraphs = []
    for para in root.iter(f"{WORD_NS}p"):
        pieces = []
        for node in para.iter():
            if node.tag == f"{WORD_NS}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{WORD_NS}tab":
                pieces.append("\t")
            elif node.tag == f"{WORD_NS}br":
                pieces.append("\n")
        paragraphs.append("".join(pieces))
    return paragraphs


def _read_pdf(content: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(content))
        lines = []
        for page in reader.pages:
            # Números isolados são paginação; sem blocos vazios entre páginas,
            # uma entrada que atravessa a quebra de página continua inteira.
            lines.extend(line for line in (page.extract_text() or "").splitlines() if not line.strip().isdigit())
    except Exception as exc:
        raise ValueError("PDF ilegível ou protegido por senha.") from exc
    return lines


def find_reference_section(lines: list[str]) -> tuple[list[str], list[str]] | None:
    """Devolve (linhas da seção de referências, linhas anteriores) ou None.

    Usa o último título 'REFERÊNCIAS' que não seja linha de sumário, pois o
    sumário costuma repetir o título. A seção termina em apêndice ou anexo.
    """
    heading_at = [
        i for i, line in enumerate(lines)
        if _fold(line) in REFERENCE_HEADINGS and not TOC_LINE_RE.search(line.strip())
    ]
    if not heading_at:
        return None
    start = heading_at[-1]
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if END_HEADING_RE.match(lines[j].strip()):
            end = j
            break
    return lines[start + 1:end], lines[:start]


def _starts_entry(line: str) -> bool:
    """Indica se a linha começa uma nova entrada (autor, entidade ou traço de repetição)."""
    return bool(AUTHOR_START.match(line) or ENTITY_START.match(line) or REPEATED_AUTHOR_START.match(line))


def split_entries(lines: list[str], paragraph_mode: bool) -> list[str]:
    """Separa as entradas da seção. Em modo parágrafo, cada linha não vazia é uma entrada."""
    if paragraph_mode:
        return [" ".join(line.split()) for line in lines if line.strip()]

    entries: list[str] = []
    current = ""
    for raw in lines:
        line = " ".join(raw.split())
        if not line:
            if current:
                entries.append(current)
                current = ""
            continue
        if not current:
            current = line
        elif _starts_entry(line) or (current.endswith((".", ")")) and line[:1].isupper()):
            entries.append(current)
            current = line
        elif current.endswith("-") and line[:1].islower():
            current = current[:-1] + line  # hifenização de quebra de linha em PDF
        else:
            current = f"{current} {line}"
    if current:
        entries.append(current)
    return entries


def extract_identifiers(entry: str) -> dict:
    """Extrai DOI, ISBN, URLs e data de acesso informados no texto da entrada."""
    doi_match = DOI_REGEX.search(entry)
    doi = doi_match.group(0).rstrip(".") if doi_match else ""
    urls = [m.group(0).rstrip(".>,;") for m in URL_REGEX.finditer(entry)]
    urls = [u for u in urls if not re.match(r"https?://(?:dx\.)?doi\.org/", u, re.IGNORECASE)]
    access = ACCESS_RE.search(entry)
    return {
        "doi": doi,
        "isbn": extract_isbn(entry),
        "urls": urls,
        "acesso": access.group(1) if access else "",
    }


NAME_PARTICLES = {"de", "da", "do", "das", "dos", "del", "di", "du", "van", "von"}


def _surname(text: str) -> str:
    """Primeiro sobrenome de uma lista de autores: 'SILVA; SOUZA et al.' -> 'SILVA'. Ignora partículas: 'de Souza' -> 'Souza'."""
    first = re.split(r"\s+et\s+al\.?|\s+e\s+|\s*&\s*|\s*;\s*|,", text.strip(), maxsplit=1)[0]
    words = [w.strip(".") for w in first.split()]
    while len(words) > 1 and words[0].lower() in NAME_PARTICLES:
        words.pop(0)
    return words[0] if words else ""


def _names(text: str) -> dict[str, str]:
    """Sobrenomes de um trecho de autoria: {forma normalizada: forma original}, sem partículas."""
    names: dict[str, str] = {}
    for word in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ'\-]+", text):
        key = _fold(word)
        if key not in NAME_PARTICLES and key not in SENTENCE_STARTERS:
            names.setdefault(key, word)
    return names


def find_citations(body_text: str) -> list[dict]:
    """Encontra citações autor-data: '(SILVA, 2019)', '(SILVA et al., 2019; SOUZA, 2020)' e 'Silva (2019)'.

    Uma citação casa com qualquer sobrenome do grupo: '(ALENCAR; MONTI, 2021)' vale para
    as duas entradas. Parte sem ano herda o ano da parte seguinte.
    """
    found = []
    for group in PARENTHETICAL_RE.finditer(body_text):
        pending: dict[str, str] = {}
        for part in group.group(1).split(";"):
            year = re.search(r"\b[c©]?(\d{4})[a-z]?\b", part)
            names = _names(part[:year.start()] if year else part)
            if not year:
                pending.update(names)
                continue
            all_names = {**pending, **names}
            if all_names:
                found.append({"sobrenome": "; ".join(all_names.values()), "nomes": list(all_names),
                              "ano": year.group(1), "trecho": f"({part.strip()})"})
            pending = {}
    for m in NARRATIVE_RE.finditer(body_text):
        names = _names(m.group(1))
        if names:
            found.append({"sobrenome": m.group(1), "nomes": list(names), "ano": m.group(2), "trecho": m.group(0)})
    unique = {}
    for item in found:
        unique.setdefault((tuple(sorted(item["nomes"])), item["ano"]), item)
    return list(unique.values())


def _entry_key(entry: str) -> tuple[set[str], set[str]]:
    """Nomes dos autores (ou da entidade) e anos de publicação. Ignora a data de acesso."""
    before_access = re.split(r"Acesso em", entry, flags=re.IGNORECASE)[0]
    author_block = re.split(r"\.\s", before_access, maxsplit=1)[0]
    authors: set[str] = set()
    for part in author_block.split(";"):
        authors |= set(_names(part.split(",")[0]))
    words = re.findall(r"[A-Za-zÀ-ÿ]+", re.sub(r"\(.*?\)", "", author_block))
    is_entity = "," not in author_block and words and all(
        w.isupper() or _fold(w) in NAME_PARTICLES for w in words)
    if is_entity:
        initials = "".join(w[0] for w in words if _fold(w) not in NAME_PARTICLES | {"e"})
        if len(initials) >= 2:
            authors.add(_fold(initials))
    return authors, set(YEAR_RE.findall(before_access))


def cross_check(citations: list[dict], entries: list[str]) -> dict:
    """Compara citações e referências: citação sem entrada e entrada sem citação."""
    keys = [_entry_key(e) for e in entries]
    cited_entries = set()
    missing = []
    for c in citations:
        names, year = set(c["nomes"]), c["ano"]
        matches = [i for i, (authors, years) in enumerate(keys) if names & authors and year in years]
        if matches:
            cited_entries.update(matches)
        else:
            missing.append(c)
    uncited = [i + 1 for i in range(len(entries)) if i not in cited_entries]
    return {
        "total": len(citations),
        "sem_referencia": missing,
        "referencias_sem_citacao": uncited,
    }


def strip_citation_label(entry: str) -> str:
    """Remove o rótulo de chave de citação que alguns gerenciadores colam antes da referência."""
    return LABEL_PREFIX_RE.sub("", entry, count=1).strip()


def _dedupe_key(entry: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(entry))


def _looks_like_reference(entry: str) -> bool:
    """Critério mínimo: ano, DOI ou URL, ou início de autor/entidade em uma linha de tamanho razoável."""
    if YEAR_RE.search(entry) or DOI_REGEX.search(entry) or URL_REGEX.search(entry):
        return True
    return len(entry) >= 30 and bool(AUTHOR_START.match(entry) or ENTITY_START.match(entry))


def _entry_alerts(entry: str) -> list[str]:
    alerts = []
    if len(entry) < 30:
        alerts.append("Entrada muito curta: pode ser quebra de linha ou fragmento.")
    if not YEAR_RE.search(entry):
        alerts.append("Ano não encontrado na entrada.")
    if not _looks_like_reference(entry):
        alerts.append("Não parece referência: confira se pertence à lista.")
    return alerts


def extract_references(filename: str, content: bytes) -> dict:
    """Ponto de entrada: lê o documento e devolve entradas, identificadores, alertas e cruzamento de citações."""
    lines, paragraph_mode = read_document(filename, content)
    section = find_reference_section(lines)
    warnings = []
    if section is None:
        return {
            "arquivo": filename, "secao_encontrada": False, "total": 0, "referencias": [],
            "citacoes": {"total": 0, "sem_referencia": [], "referencias_sem_citacao": []},
            "avisos": ["Seção 'REFERÊNCIAS' não encontrada. Verifique o título ou cole as entradas manualmente."],
        }
    ref_lines, body_lines = section
    entries, seen, duplicates = [], set(), 0
    for entry in (strip_citation_label(e) for e in split_entries(ref_lines, paragraph_mode)):
        key = _dedupe_key(entry)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        entries.append(entry)
    if duplicates:
        warnings.append(f"{duplicates} entrada(s) repetida(s) ignorada(s): a lista aparece copiada mais de uma vez.")
    trailing = 0
    while entries and not _looks_like_reference(entries[-1]):
        entries.pop()
        trailing += 1
    if trailing:
        warnings.append(f"{trailing} parágrafo(s) após a última referência foram ignorados: não parecem referências.")
    if not entries:
        warnings.append("Seção de referências encontrada, mas sem entradas.")
    citations = find_citations("\n".join(body_lines))
    check = cross_check(citations, entries)
    if check["sem_referencia"]:
        warnings.append(f"{len(check['sem_referencia'])} citação(ões) no corpo sem entrada correspondente.")
    if check["referencias_sem_citacao"]:
        warnings.append(f"{len(check['referencias_sem_citacao'])} referência(s) sem citação no corpo.")
    if not paragraph_mode:
        warnings.append("PDF/TXT: as quebras de entrada foram inferidas. Confira os alertas de cada item.")
    return {
        "arquivo": filename,
        "secao_encontrada": True,
        "total": len(entries),
        "referencias": [
            {"indice": i + 1, "texto": e, **extract_identifiers(e), "alertas": _entry_alerts(e)}
            for i, e in enumerate(entries)
        ],
        "citacoes": check,
        "avisos": warnings,
    }
