"""Evidence-first bibliographic resolution.

Resolution is separate from parsing/formatting. A resolved record is accepted
only when a stable authority record or supported public source identifies the
same work. Every returned field carries a source and confidence.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from reference_validation import normalized, title_similarity, verify_work_identity

ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "data" / "authority_registry.json"
RECORDS_PATH = ROOT / "data" / "verified_records.json"


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [] if path.name.startswith("verified") else {}


def _source(name, url):
    return {"name": name, "url": url, "retrieved_at": datetime.now(timezone.utc).isoformat()}


def _safe_public_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
            return False
        host = p.hostname.casefold()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return False
        try:
            ip = ipaddress.ip_address(host)
            return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
        except ValueError:
            pass
        # DNS is checked so a public-looking hostname cannot silently target a private address.
        for info in socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (ValueError, OSError, socket.gaierror):
        return False


def _authors_from_names(values):
    out = []
    for name in values:
        name = re.sub(r"\s+", " ", str(name or "")).strip()
        if not name:
            continue
        if "," in name:
            family, given = [p.strip() for p in name.split(",", 1)]
            out.append({"family": family, "given": given})
        elif name.isupper() or len(name.split()) > 4:
            out.append({"family": name, "given": "", "is_corporate": True})
        else:
            given, _, family = name.rpartition(" ")
            out.append({"family": family or name, "given": given})
    return out


def fetch_public_page_metadata(url: str) -> dict:
    """Extract citation/JSON-LD metadata from a public web page.

    This resolver deliberately rejects private/local network targets (SSRF guard).
    """
    if not _safe_public_url(url):
        return {}
    try:
        response = requests.get(
            url, timeout=(5, 15), allow_redirects=True,
            headers={"User-Agent": "BrainFormat/4.0 bibliographic-verifier"},
        )
        response.raise_for_status()
        if len(response.content) > 4 * 1024 * 1024 or not _safe_public_url(response.url):
            return {}
    except requests.RequestException:
        return {}
    soup = BeautifulSoup(response.content, "html.parser")
    # Anti-bot pages must never become bibliographic evidence.
    page_title = (soup.title.get_text(" ", strip=True) if soup.title else "").casefold()
    if "not a bot" in page_title or "captcha" in page_title:
        return {}

    meta_tags = {}
    for tag in soup.find_all("meta"):
        key = (tag.get("name") or tag.get("property") or "").casefold()
        content = tag.get("content", "").strip()
        if key and content:
            meta_tags.setdefault(key, []).append(content)

    def first(*keys):
        for key in keys:
            vals = meta_tags.get(key.casefold())
            if vals:
                return vals[0]
        return ""

    data = {
        "title": first("citation_title", "dc.title", "dcterms.title", "og:title"),
        "publisher": first("citation_publisher", "dc.publisher", "dcterms.publisher"),
        "site_name": first("og:site_name"),
        "date_str": first("citation_publication_date", "citation_date", "dc.date.issued",
                          "dcterms.issued", "article:published_time", "date", "dc.date"),
        "journal": first("citation_journal_title"),
        "volume": first("citation_volume", "dc.source.volume"),
        "issue": first("citation_issue", "dc.source.issue"),
        "doi": first("citation_doi", "dc.identifier.doi"),
        "pdf_url": first("citation_pdf_url"),
    }
    first_page = first("citation_firstpage")
    last_page = first("citation_lastpage")
    if first_page:
        data["page"] = first_page + (("-" + last_page) if last_page and last_page != first_page else "")
    names = meta_tags.get("citation_author", []) or meta_tags.get("dc.creator", [])
    if names:
        data["authors"] = _authors_from_names(names)

    # Preserve Dublin Core fields that are especially useful for theses,
    # dissertations and institutional repositories.
    descriptions = (
        meta_tags.get("dc.description", [])
        + meta_tags.get("dcterms.description", [])
        + meta_tags.get("description", [])
    )
    identifiers = (
        meta_tags.get("dc.identifier", [])
        + meta_tags.get("dc.identifier.uri", [])
        + meta_tags.get("dcterms.identifier", [])
    )
    contributors = meta_tags.get("dc.contributor", []) + meta_tags.get("dcterms.contributor", [])
    types = meta_tags.get("dc.type", []) + meta_tags.get("dcterms.type", [])
    if descriptions:
        data["_descriptions"] = descriptions
    if identifiers:
        data["_identifiers"] = identifiers
    if contributors:
        data["_contributors"] = contributors
    if types:
        data["_types"] = types

    # JSON-LD is frequently more complete than HTML citation tags.
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        queue = payload if isinstance(payload, list) else [payload]
        while queue:
            obj = queue.pop(0)
            if not isinstance(obj, dict):
                continue
            if isinstance(obj.get("@graph"), list):
                queue.extend(obj["@graph"])
            data["title"] = data.get("title") or obj.get("headline") or obj.get("name") or ""
            data["date_str"] = data.get("date_str") or obj.get("datePublished") or ""
            pub = obj.get("publisher")
            if isinstance(pub, dict):
                data["publisher"] = data.get("publisher") or pub.get("name", "")
            auth = obj.get("author")
            if not data.get("authors") and auth:
                auth = auth if isinstance(auth, list) else [auth]
                names = [a.get("name", "") if isinstance(a, dict) else str(a) for a in auth]
                data["authors"] = _authors_from_names(names)
            part = obj.get("isPartOf")
            if isinstance(part, dict):
                data["newspaper"] = data.get("newspaper") or part.get("name", "")

    date_value = str(data.get("date_str", ""))
    year = re.search(r"\b(19|20)\d{2}\b", date_value)
    if year:
        data["year"] = year.group(0)
    month = re.search(r"\b(?:19|20)\d{2}[-/](0?[1-9]|1[0-2])(?:[-/]\d{1,2})?\b", date_value)
    if month:
        data["start_month"] = int(month.group(1))
    data["url"] = response.url
    return {k: v for k, v in data.items() if v not in ("", None, [], {})}




def academic_repository_metadata(page: dict, *, fallback_url: str = "") -> dict:
    """Interpret Dublin Core/DSpace metadata as an academic work.

    The repository's generic DC.type is not trusted when a description explicitly
    states thesis/dissertation/TCC/monograph. This avoids treating theses mirrored
    as "livro digital" as books.
    """
    if not page:
        return {}

    descriptions = [str(x) for x in page.get("_descriptions", [])]
    types = [str(x) for x in page.get("_types", [])]
    contributors = [str(x) for x in page.get("_contributors", [])]
    blob = " ".join(descriptions + types + contributors)

    kind = ""
    degree = ""
    patterns = [
        ("Tese", r"\bTese\s*\((?:doutorado|doctoral|ph\.?d\.?)\)"),
        ("Dissertação", r"\bDisserta[cç][aã]o\s*\((?:mestrado|master)\)"),
        ("Monografia", r"\bMonografia\b"),
        ("Trabalho de Conclusão de Curso", r"\b(?:Trabalho de Conclus[aã]o de Curso|TCC)\b"),
    ]
    for label, pattern in patterns:
        if re.search(pattern, blob, re.I):
            kind = label
            break
    if not kind:
        return {}

    # Extract institution/program/city from common DSpace description patterns.
    institution = ""
    city = ""
    program = ""
    defense_date = ""
    academic_desc = next((d for d in descriptions if re.search(
        r"\b(?:Tese|Disserta[cç][aã]o|Monografia|Trabalho de Conclus[aã]o de Curso|TCC)\b", d, re.I
    )), "")

    inst_match = re.search(
        r"[-–—]\s*([^,.;]+(?:Universidade|University|Instituto|Institute|Faculdade|Fundação)[^,.;]*|"
        r"(?:Universidade|University|Instituto|Institute|Faculdade|Fundação)[^,.;]*)",
        academic_desc, re.I,
    )
    if inst_match:
        institution = re.sub(r"\s+", " ", inst_match.group(1)).strip(" -–—,.;")
    else:
        inst_match = re.search(
            r"[-–—]\s*([^,.;]+),", academic_desc
        )
        if inst_match:
            institution = re.sub(r"\s+", " ", inst_match.group(1)).strip()

    program_match = re.search(
        r"(Programa de P[oó]s-Gradua[cç][aã]o em\s+[^.]+)", academic_desc, re.I
    )
    if not program_match:
        program_match = next(
            (re.search(r"(Programa de P[oó]s-Gradua[cç][aã]o em\s+.+)", c, re.I) for c in contributors
             if re.search(r"Programa de P[oó]s-Gradua[cç][aã]o", c, re.I)),
            None,
        )
    if program_match:
        program = re.sub(r"\s+", " ", program_match.group(1)).strip(" .")

    defense_match = re.search(
        r"Defesa:\s*([^,.;]+),\s*(\d{1,2}/\d{1,2}/\d{4})", academic_desc, re.I
    )
    if defense_match:
        city = defense_match.group(1).strip()
        defense_date = defense_match.group(2)

    # Prefer a persistent/institutional identifier over an aggregator URL.
    identifiers = [str(x).strip() for x in page.get("_identifiers", []) if str(x).strip()]
    preferred_url = ""
    for value in identifiers:
        if value.lower().startswith("https://hdl.handle.net/"):
            preferred_url = value
            break
    if not preferred_url:
        for value in identifiers:
            if value.lower().startswith(("http://", "https://")):
                preferred_url = value
                break
    preferred_url = preferred_url or page.get("url") or fallback_url

    # If the identified institution has a configured institutional repository,
    # prefer its canonical Handle URL over an aggregator/mirror.
    handle_match = re.search(r"(\d+/\d+)", preferred_url or fallback_url)
    if institution and handle_match:
        for profile in _load(REGISTRY_PATH).values():
            repo_base = profile.get("repository_base")
            aliases = profile.get("aliases", [])
            if repo_base and any(normalized(alias) in normalized(institution) for alias in aliases):
                preferred_url = repo_base.rstrip("/") + "/" + handle_match.group(1)
                break

    year = ""
    if defense_date:
        year = defense_date[-4:]
    if not year:
        # DSpace mirrors often expose import dates before the original year.
        years = []
        for value in descriptions + identifiers:
            years.extend(re.findall(r"\b(?:19|20)\d{2}\b", value))
        years.extend(re.findall(r"\b(?:19|20)\d{2}\b", str(page.get("date_str", ""))))
        if years:
            year = min(years)
    if not year:
        year = str(page.get("year") or "")

    if kind == "Tese":
        area = re.sub(r"^Programa de P[oó]s-Gradua[cç][aã]o em\s+", "", program, flags=re.I).strip()
        degree = f"Tese (Doutorado em {area})" if area else "Tese (Doutorado)"
    elif kind == "Dissertação":
        area = re.sub(r"^Programa de P[oó]s-Gradua[cç][aã]o em\s+", "", program, flags=re.I).strip()
        degree = f"Dissertação (Mestrado em {area})" if area else "Dissertação (Mestrado)"
    else:
        degree = kind

    result = {
        "item_type": "thesis",
        "title": page.get("title", ""),
        "authors": page.get("authors", []),
        "year": year,
        "degree_year": year,
        "degree_type": degree,
        "institution": institution,
        "city": city,
        "url": preferred_url,
    }
    if program:
        result["program"] = program
    if defense_date:
        result["defense_date"] = defense_date
    return {k: v for k, v in result.items() if v not in ("", None, [], {})}


def fetch_academic_repository(url: str) -> dict:
    """Resolve an academic work from DSpace-style metadata."""
    page = fetch_public_page_metadata(url)
    meta = academic_repository_metadata(page, fallback_url=url)
    if not meta:
        return {}
    source = _source("Repositório acadêmico", page.get("url") or url)
    meta["_source"] = source
    meta["_field_sources"] = {k: source for k in meta if not k.startswith("_")}
    meta["_field_confidence"] = {k: 0.99 for k in meta if not k.startswith("_")}
    meta["_work_verified"] = True
    return meta

def enrich_from_official_page(base: dict, parsed: dict | None = None) -> dict:
    """Complement any already-identified work from its canonical public page.

    This is type-agnostic: it never guesses document-specific values and only
    merges metadata after the page identity is confirmed by DOI or strong
    bibliographic agreement.
    """
    if not base or not base.get("url"):
        return base
    page = fetch_public_page_metadata(base["url"])
    if not page:
        return base

    candidate = dict(page)
    candidate.setdefault("item_type", base.get("item_type", ""))
    same_doi = bool(
        base.get("doi") and page.get("doi")
        and str(base["doi"]).casefold().strip() == str(page["doi"]).casefold().strip()
    )
    if not same_doi:
        probe = {
            "title": base.get("title", ""),
            "year": base.get("year", ""),
            "item_type": base.get("item_type", ""),
        }
        if base.get("authors") and page.get("authors"):
            probe["authors"] = base["authors"]
        if not verify_work_identity(probe, candidate):
            return base

    result = dict(base)
    source = _source("Página oficial da obra", page.get("url") or base["url"])
    sources = list(result.get("_sources") or ([result["_source"]] if result.get("_source") else []))
    if not any(s.get("url") == source["url"] for s in sources):
        sources.append(source)
    result["_sources"] = sources

    field_sources = dict(result.get("_field_sources") or {})
    field_confidence = dict(result.get("_field_confidence") or {})

    # Prefer the official page when it has a demonstrably more complete title.
    if page.get("title") and (
        not result.get("title")
        or len(normalized(page["title"])) > len(normalized(result.get("title", ""))) + 8
    ):
        result["title"] = page["title"]
        field_sources["title"] = source
        field_confidence["title"] = 1.0

    # Generic bibliographic fields that are safe to reuse across document types.
    for key in (
        "authors", "publisher", "site_name", "journal", "volume", "issue",
        "page", "year", "start_month", "doi", "isbn", "url"
    ):
        value = page.get(key)
        if value in ("", None, [], {}):
            continue
        # Existing explicit bibliographic values win unless the field is a
        # canonical locator/date that the official page can safely refine.
        if not result.get(key) or key in {"url", "start_month"}:
            result[key] = value
            field_sources[key] = source
            field_confidence[key] = 1.0

    result["_field_sources"] = field_sources
    result["_field_confidence"] = field_confidence
    return result

def _record_match(clean_text: str, parsed: dict) -> dict:
    records = _load(RECORDS_PATH)
    ntext = normalized(clean_text)
    parsed_title = normalized(parsed.get("title", ""))
    for record in records:
        match = record.get("match", {})
        url = match.get("url", "")
        title = match.get("title", "")
        entity = match.get("entity", "")
        url_ok = bool(url and normalized(url) in normalized(clean_text))
        title_norm = normalized(title)
        title_ok = bool(title_norm and (title_norm in ntext or (parsed_title and title_similarity(parsed_title, title) >= 0.86)))
        entity_ok = not entity or normalized(entity) in ntext
        if (url_ok or title_ok) and entity_ok:
            meta = dict(record["metadata"])
            source = _source(record.get("source_name", "Registro de autoridade verificado"), record.get("source_url", url))
            meta["_source"] = source
            meta["_field_sources"] = {k: source for k in meta if not k.startswith("_")}
            meta["_field_confidence"] = {k: float(record.get("confidence", 1.0)) for k in meta if not k.startswith("_")}
            meta["_authority_record"] = True
            meta["_work_verified"] = True
            return meta
    return {}


def _apply_entity_profile(clean_text: str, parsed: dict) -> dict:
    profiles = _load(REGISTRY_PATH)
    ntext = normalized(clean_text)
    for key, profile in profiles.items():
        aliases = profile.get("aliases", []) + [key]
        if not any(normalized(alias) in ntext for alias in aliases):
            continue
        meta = {}
        for field in ("publisher", "city", "site_name", "newspaper"):
            if profile.get(field) and not parsed.get(field):
                meta[field] = profile[field]
        if profile.get("corporate_author") and (not parsed.get("authors") or parsed.get("authors", [{}])[0].get("family", "").casefold() in {a.casefold() for a in aliases}):
            meta["authors"] = [{"family": profile["corporate_author"], "given": "", "is_corporate": True}]
        if not meta:
            return {}
        source = _source("Cadastro de autoridade institucional", profile.get("authority_url", ""))
        meta["_source"] = source
        meta["_field_sources"] = {k: source for k in meta if not k.startswith("_")}
        # Entity defaults are high-confidence but not equivalent to a work-level record.
        meta["_field_confidence"] = {k: 0.95 for k in meta if not k.startswith("_")}
        meta["_entity_profile"] = True
        meta["_work_verified"] = False
        return meta
    return {}


def resolve_reference(clean_text: str, parsed: dict, *, online: bool = True) -> dict:
    """Return best evidence candidate, never a speculative completion."""
    exact = _record_match(clean_text, parsed)
    if exact:
        return exact

    entity = _apply_entity_profile(clean_text, parsed)

    url = parsed.get("url", "")
    if online and url:
        # First try a generic academic repository resolver. It only returns a
        # record when Dublin Core explicitly identifies an academic work.
        academic = fetch_academic_repository(url)
        if academic:
            return academic

        host = (urlparse(url).hostname or "").casefold()

        # Some institutional repositories have broken TLS chains in Python but
        # expose the same Handle through trusted mirrors. Use the Handle as the
        # stable identifier and never infer bibliographic fields from the host.
        handle = re.search(r"/(?:xmlui/)?handle/(\d+/\d+)", url, re.I)
        if host.endswith("ufpr.br") and handle:
            mirror = "https://educapes.capes.gov.br/handle/" + handle.group(1)
            academic = fetch_academic_repository(mirror)
            if academic:
                academic["url"] = "https://acervodigital.ufpr.br/handle/" + handle.group(1)
                source = academic.get("_source", {})
                academic.setdefault("_field_sources", {})["url"] = source
                return academic

        supported = host.endswith("globo.com") or host.endswith("wipo.int") or host.endswith("fgv.br")
        if supported:
            page = fetch_public_page_metadata(url)
            if page:
                # Host semantics are evidence, not guesses.
                if host.endswith("oglobo.globo.com") or host == "oglobo.globo.com":
                    page.update(item_type="newspaperArticle", newspaper="O Globo", city="Rio de Janeiro")
                source = _source("Metadados da pagina oficial", url)
                page["_source"] = source
                page["_field_sources"] = {k: source for k in page if not k.startswith("_")}
                page["_field_confidence"] = {k: 0.98 for k in page if not k.startswith("_")}
                page["_work_verified"] = True
                return page

    return entity
