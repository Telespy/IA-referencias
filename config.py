import datetime
import re

# User-Agent delicado exigido pela Crossref API para melhor performance
HEADERS = {
    "User-Agent": "AcademicReferenceFormatter/1.0 (mailto:researcher@example.com)"
}

# Mapeamento de periódicos/editoras famosas para Cidade + Sigla (EUA, UK e países)
PUBLISHER_CITY_MAP = {
    # Periódicos famosos
    "biological psychiatry": "New York, NY",
    "brain stimulation": "Oxford, UK",
    "nature": "London, UK",
    "science": "Washington, DC",
    "the lancet": "London, UK",
    "cell": "Cambridge, MA",
    "plos one": "San Francisco, CA",
    "proceedings of the national academy of sciences": "Washington, DC",
    "pnas": "Washington, DC",
    "jama": "Chicago, IL",
    "new england journal of medicine": "Boston, MA",
    "frontiers in psychology": "Lausanne, CH",
    "frontiers in neuroscience": "Lausanne, CH",
    "brain": "Oxford, UK",
    "neuroimage": "Amsterdam",
    "neuron": "Cambridge, MA",
    "environment and planning b": "Thousand Oaks, CA",
    "geojournal": "Washington, DC",
    "european planning studies": "Oxford, UK",
    "regional studies": "London, UK",
    
    # Periódicos e Instituições Brasileiras
    "unilasalle": "Canoas",
    "la salle": "Canoas",
    "centro universitário la salle": "Canoas",
    "redes": "Canoas",
    "revista eletrônica direito e sociedade": "Canoas",
    "uff": "Niterói",
    "universidade federal fluminense": "Niterói",
    "ifrn": "Natal",
    "ufrn": "Natal",
    "usp": "São Paulo",
    "unicamp": "Campinas",
    "unesp": "São Paulo",
    "ufrj": "Rio de Janeiro",
    "ufmg": "Belo Horizonte",
    "ufrs": "Porto Alegre",
    "ufrgs": "Porto Alegre",
    "ufsc": "Florianópolis",
    "ufpr": "Curitiba",
    "ufpe": "Recife",
    "ufba": "Salvador",
    "ufc": "Fortaleza",
    
    # Editoras Brasileiras Famosas
    "paz e terra": "São Paulo",
    "vozes": "Petrópolis",
    "cortez": "São Paulo",
    "rocco": "Rio de Janeiro",
    "record": "Rio de Janeiro",
    "zahar": "Rio de Janeiro",
    "jorge zahar": "Rio de Janeiro",
    "companhia das letras": "São Paulo",
    "todavia": "São Paulo",
    "intrínseca": "Rio de Janeiro",
    "intrinseca": "Rio de Janeiro",
    "autêntica": "Belo Horizonte",
    "autentica": "Belo Horizonte",
    "boitempo": "São Paulo",
    "editora 34": "São Paulo",
    "papirus": "Campinas",
    "perspectiva": "São Paulo",
    "saraiva": "São Paulo",
    "artmed": "Porto Alegre",
    "grupo a": "Porto Alegre",
    "bookman": "Porto Alegre",
    "penso": "Porto Alegre",
    "manole": "Barueri, SP",
    "gutenberg": "Belo Horizonte",
    "editora unesp": "São Paulo",
    "editora fiocruz": "Rio de Janeiro",
    "edusp": "São Paulo",
    "editora unicamp": "Campinas",
    "editora ufrj": "Rio de Janeiro",
    "editora ufmg": "Belo Horizonte",
    "editora unb": "Brasília",
    "editora ufsc": "Florianópolis",
    "editora ufpr": "Curitiba",
    "editora ufrgs": "Porto Alegre",
    "editora uerj": "Rio de Janeiro",
    "editora uff": "Niterói",
    "editora ifrn": "Natal",
    "editora atlas": "São Paulo",
    "atlas": "São Paulo",
    "contexto": "São Paulo",
    "editora contexto": "São Paulo",
    "moderna": "São Paulo",
    "ática": "São Paulo",
    "atica": "São Paulo",
    "scipione": "São Paulo",
    "ftd": "São Paulo",
    "loyola": "São Paulo",
    "l&pm": "Porto Alegre",
    "lpm": "Porto Alegre",
    "martins fontes": "São Paulo",
    "wmf martins fontes": "São Paulo",
    "paulinas": "São Paulo",
    "paulus": "São Paulo",
    "hedra": "São Paulo",
    "global editora": "São Paulo",
    "brasiliense": "São Paulo",
    "civilização brasileira": "Rio de Janeiro",
    "civilizacao brasileira": "Rio de Janeiro",
    "josé olympio": "Rio de Janeiro",
    "jose olympio": "Rio de Janeiro",
    "nova fronteira": "Rio de Janeiro",
    "aleph": "São Paulo",
    "darkside": "Rio de Janeiro",
    "sextante": "Rio de Janeiro",
    "harpercollins": "Rio de Janeiro",
    "editora globo": "São Paulo",
    "parábola": "São Paulo",
    "parabola": "São Paulo",
    "intersaberes": "Curitiba",
    "ibpex": "Curitiba",

    # Jornais e Revistas
    "folha de s.paulo": "São Paulo",
    "folha de s. paulo": "São Paulo",
    "folha de sao paulo": "São Paulo",
    "o globo": "Rio de Janeiro",
    "o estado de s. paulo": "São Paulo",
    "o estado de sao paulo": "São Paulo",
    "estadão": "São Paulo",
    "estadao": "São Paulo",
    "valor econômico": "São Paulo",
    "valor economico": "São Paulo",
    "zero hora": "Porto Alegre",
    "correio braziliense": "Brasília",
    "jornal do brasil": "Rio de Janeiro",
    "gazeta do povo": "Curitiba",
    "diário de pernambuco": "Recife",
    "diario de pernambuco": "Recife",
    "tribuna do norte": "Natal",
    "veja": "São Paulo",
    "istoé": "São Paulo",
    "isto e": "São Paulo",
    "época": "Rio de Janeiro",
    "exame": "São Paulo",
    "piauí": "Rio de Janeiro",
    "piaui": "Rio de Janeiro",

    # Periódicos Científicos Brasileiros Famosos
    "trabalho, educação e saúde": "Rio de Janeiro",
    "revista brasileira de educação": "Rio de Janeiro",
    "trabalho necessário": "Niterói",
    "revista trabalho necessário": "Niterói",
    "retratos da escola": "Brasília",
    "cadernos de pesquisa": "São Paulo",
    "educação & sociedade": "Campinas",
    "educacao e sociedade": "Campinas",
    "cadernos de saúde pública": "Rio de Janeiro",
    "revista de saúde pública": "São Paulo",
    "dados": "Rio de Janeiro",
    "novos estudos cebrap": "São Paulo",
    "estudos avançados": "São Paulo",
    "maná": "Rio de Janeiro",
    "mana": "Rio de Janeiro",
    "horizontes antropológicos": "Porto Alegre",
    "scielo": "São Paulo",

    # Editoras Internacionais
    "elsevier": "Amsterdam",
    "alta books": "Rio de Janeiro",
    "springer": "Berlin",
    "springer nature": "Berlin",
    "oxford university press": "Oxford, UK",
    "cambridge university press": "Cambridge, UK",
    "harvard university press": "Cambridge, MA",
    "routledge": "London, UK",
    "wiley": "Hoboken, NJ",
    "john wiley & sons": "Hoboken, NJ",
    "mit press": "Cambridge, MA",
    "pearson": "London, UK",
    "mcgraw-hill": "New York, NY",
    "sage publications": "Thousand Oaks, CA",
    "edgard blücher": "São Paulo",
    "blucher": "São Paulo",
}

# Base de Conhecimento de Obras Acadêmicas Clássicas (Auto-completar Editora e Cidade)
FAMOUS_BOOKS_MAP = [
    {"keywords": ["foucault", "vigiar e punir"], "publisher": "Vozes", "city": "Petrópolis"},
    {"keywords": ["foucault", "microfísica do poder"], "publisher": "Graal", "city": "Rio de Janeiro"},
    {"keywords": ["foucault", "as palavras e as coisas"], "publisher": "Martins Fontes", "city": "São Paulo"},
    {"keywords": ["foucault", "arqueologia do saber"], "publisher": "Forense Universitária", "city": "Rio de Janeiro"},
    {"keywords": ["foucault", "história da sexualidade"], "publisher": "Graal", "city": "Rio de Janeiro"},
    {"keywords": ["freire", "pedagogia da autonomia"], "publisher": "Paz e Terra", "city": "São Paulo"},
    {"keywords": ["freire", "pedagogia do oprimido"], "publisher": "Paz e Terra", "city": "Rio de Janeiro"},
    {"keywords": ["freire", "pedagogia da esperança"], "publisher": "Paz e Terra", "city": "São Paulo"},
    {"keywords": ["freire", "educação como prática da liberdade"], "publisher": "Paz e Terra", "city": "Rio de Janeiro"},
    {"keywords": ["santos", "território e sociedade"], "publisher": "Record", "city": "Rio de Janeiro"},
    {"keywords": ["santos", "a natureza do espaço"], "publisher": "Hucitec", "city": "São Paulo"},
    {"keywords": ["santos", "por uma outra globalização"], "publisher": "Record", "city": "Rio de Janeiro"},
    {"keywords": ["marx", "o capital"], "publisher": "Boitempo", "city": "São Paulo"},
    {"keywords": ["marx", "manifesto do partido comunista"], "publisher": "Boitempo", "city": "São Paulo"},
    {"keywords": ["bourdieu", "a distinção"], "publisher": "Zahar", "city": "Rio de Janeiro"},
    {"keywords": ["bourdieu", "o poder simbólico"], "publisher": "Bertrand Brasil", "city": "Rio de Janeiro"},
    {"keywords": ["bourdieu", "a reprodução"], "publisher": "Vozes", "city": "Petrópolis"},
    {"keywords": ["vygotsky", "pensamento e linguagem"], "publisher": "Martins Fontes", "city": "São Paulo"},
    {"keywords": ["vigotski", "formação social da mente"], "publisher": "Martins Fontes", "city": "São Paulo"},
    {"keywords": ["bakhtin", "marxismo e filosofia da linguagem"], "publisher": "Hucitec", "city": "São Paulo"},
    {"keywords": ["bakhtin", "estética da criação verbal"], "publisher": "Martins Fontes", "city": "São Paulo"},
    {"keywords": ["piaget", "a construção do real na criança"], "publisher": "Ática", "city": "São Paulo"},
    {"keywords": ["deleuze", "mil platôs"], "publisher": "Editora 34", "city": "São Paulo"},
    {"keywords": ["adorno", "dialética do esclarecimento"], "publisher": "Zahar", "city": "Rio de Janeiro"},
    {"keywords": ["gramsci", "cadernos do cárcere"], "publisher": "Civilização Brasileira", "city": "Rio de Janeiro"},
    {"keywords": ["saviani", "pedagogia histórico-crítica"], "publisher": "Autores Associados", "city": "Campinas"},
    {"keywords": ["saviani", "história das ideias pedagógicas"], "publisher": "Autores Associados", "city": "Campinas"},
    {"keywords": ["saviani", "escola e democracia"], "publisher": "Autores Associados", "city": "Campinas"},
    {"keywords": ["luria", "desenvolvimento cognitivo"], "publisher": "Ícone", "city": "São Paulo"},
    {"keywords": ["minayo", "o desafio do conhecimento"], "publisher": "Hucitec", "city": "São Paulo"},
    {"keywords": ["bardin", "análise de conteúdo"], "publisher": "Edições 70", "city": "São Paulo"},
    {"keywords": ["gil", "como elaborar projetos de pesquisa"], "publisher": "Atlas", "city": "São Paulo"},
    {"keywords": ["severino", "metodologia do trabalho científico"], "publisher": "Cortez", "city": "São Paulo"},
    {"keywords": ["bauman", "modernidade líquida"], "publisher": "Jorge Zahar", "city": "Rio de Janeiro", "year": "2001"},
    {"keywords": ["bauman", "amor líquido"], "publisher": "Jorge Zahar", "city": "Rio de Janeiro", "year": "2004"},
    {"keywords": ["bauman", "vida líquida"], "publisher": "Jorge Zahar", "city": "Rio de Janeiro", "year": "2007"},
    {"keywords": ["lakatos", "metodologia científica"], "publisher": "Atlas", "city": "São Paulo", "year": "2003"},
    {"keywords": ["marconi", "metodologia científica"], "publisher": "Atlas", "city": "São Paulo", "year": "2003"},
    {"keywords": ["marconi", "lakatos"], "publisher": "Atlas", "city": "São Paulo", "year": "2003"},
    {"keywords": ["giddens", "consequências da modernidade"], "publisher": "Editora UNESP", "city": "São Paulo", "year": "1991"},
    {"keywords": ["giddens", "consequencias da modernidade"], "publisher": "Editora UNESP", "city": "São Paulo", "year": "1991"},
    {"keywords": ["giddens", "terceira via"], "publisher": "Record", "city": "Rio de Janeiro", "year": "1999"},
    {"keywords": ["giddens", "transformação da intimidade"], "publisher": "Editora UNESP", "city": "São Paulo", "year": "1993"},
    {"keywords": ["giddens", "sociologia"], "publisher": "Artmed", "city": "Porto Alegre", "year": "2005"},
    {"keywords": ["habermas", "ação comunicativa"], "publisher": "Wmf Martins Fontes", "city": "São Paulo", "year": "2012"},
    {"keywords": ["habermas", "mudança estrutural da esfera pública"], "publisher": "Tempo Brasileiro", "city": "Rio de Janeiro", "year": "1984"},
    {"keywords": ["weber", "ética protestante"], "publisher": "Companhia das Letras", "city": "São Paulo", "year": "2004"},
    {"keywords": ["weber", "economia e sociedade"], "publisher": "Editora UNB", "city": "Brasília", "year": "1999"},
    {"keywords": ["durkheim", "regras do método sociológico"], "publisher": "Martins Fontes", "city": "São Paulo", "year": "2007"},
    {"keywords": ["durkheim", "divisão do trabalho social"], "publisher": "Martins Fontes", "city": "São Paulo", "year": "1999"},
    {"keywords": ["durkheim", "suicídio"], "publisher": "Martins Fontes", "city": "São Paulo", "year": "2000"},
    {"keywords": ["arendt", "condição humana"], "publisher": "Forense Universitária", "city": "Rio de Janeiro", "year": "2007"},
    {"keywords": ["arendt", "origens do totalitarismo"], "publisher": "Companhia das Letras", "city": "São Paulo", "year": "1989"},
    {"keywords": ["chaui", "convite à filosofia"], "publisher": "Ática", "city": "São Paulo", "year": "2000"},
    {"keywords": ["chaui", "ideologia"], "publisher": "Brasiliense", "city": "São Paulo", "year": "2001"},
    {"keywords": ["holanda", "raízes do brasil"], "publisher": "Companhia das Letras", "city": "São Paulo", "year": "1995"},
    {"keywords": ["freyre", "casa-grande & senzala"], "publisher": "Global Editora", "city": "São Paulo", "year": "2003"},
    {"keywords": ["candido", "formação da literatura brasileira"], "publisher": "Ouro sobre Azul", "city": "Rio de Janeiro", "year": "2006"},
    {"keywords": ["demo", "metodologia científica"], "publisher": "Atlas", "city": "São Paulo", "year": "1995"},
    {"keywords": ["diniz", "código civil"], "publisher": "Saraiva", "city": "São Paulo", "year": "2010"}
]

# Mapeamento de teses e dissertações acadêmicas clássicas para enriquecimento automático de programa/área
FAMOUS_ACADEMIC_WORKS_MAP = [
    {
        "keywords": ["carneiro", "construção do outro como não-ser"],
        "authors": [{"given": "Aparecida Sueli", "family": "CARNEIRO"}],
        "title": "A construção do outro como não-ser como fundamento do ser",
        "degree_type": "Tese (Doutorado em Filosofia da Educação)",
        "institution": "Faculdade de Educação, Universidade de São Paulo",
        "city": "São Paulo",
        "degree_year": "2005",
        "year": "2005"
    },
    {
        "keywords": ["moura", "trabalho e formação docente na educação profissional"],
        "authors": [{"given": "Dante Henrique", "family": "MOURA"}],
        "title": "Trabalho e formação docente na educação profissional",
        "degree_type": "Tese (Doutorado em Educação)",
        "institution": "Centro de Ciências Sociais Aplicadas, Universidade Federal do Rio Grande do Norte",
        "city": "Natal",
        "degree_year": "2003",
        "year": "2003"
    }
]

# Cidades dos EUA e UK que devem receber sigla
US_UK_CITIES_MAP = {
    "thousand oaks": "Thousand Oaks, CA",
    "oxford": "Oxford, UK",
    "cambridge": "Cambridge, UK",
    "london": "London, UK",
    "new york": "New York, NY",
    "boston": "Boston, MA",
    "chicago": "Chicago, IL",
    "san francisco": "San Francisco, CA",
    "washington": "Washington, DC",
    "hoboken": "Hoboken, NJ",
    "birmingham": "Birmingham, UK",
    "los angeles": "Los Angeles, CA",
    "seattle": "Seattle, WA",
    "philadelphia": "Philadelphia, PA"
}

def disambiguate_city(city: str, context: str = "") -> str:
    """Garante que cidades dos EUA e UK recebam sigla de estado/país."""
    if not city or city == "[S. l.]":
        return "[S. l.]"
        
    c_lower = city.lower().strip()
    ctx_lower = context.lower().strip()
    
    city_clean = re.sub(r'\b([A-Z])\.\s*([A-Z])\.\b', r'\1\2', city)
    
    if "," in city_clean:
        return city_clean
        
    if c_lower in US_UK_CITIES_MAP:
        if c_lower == "cambridge" and ("harvard" in ctx_lower or "mit" in ctx_lower or "massachusetts" in ctx_lower):
            return "Cambridge, MA"
        if c_lower == "oxford" and ("ohio" in ctx_lower or "oh" in ctx_lower):
            return "Oxford, OH"
        return US_UK_CITIES_MAP[c_lower]
        
    return city_clean

# Meses ABNT (português)
ABNT_MONTHS_PT = {
    1: "jan.", 2: "fev.", 3: "mar.", 4: "abr.", 5: "maio", 6: "jun.",
    7: "jul.", 8: "ago.", 9: "set.", 10: "out.", 11: "nov.", 12: "dez."
}

# Meses ABNT para obras em Inglês
ABNT_MONTHS_EN = {
    1: "Jan.", 2: "Feb.", 3: "Mar.", 4: "Apr.", 5: "May", 6: "June",
    7: "July", 8: "Aug.", 9: "Sep.", 10: "Oct.", 11: "Nov.", 12: "Dec."
}

def is_english_publication(meta: dict) -> bool:
    """Detecta se uma obra é em inglês. Obras brasileiras/em português retornam False."""
    if not meta:
        return False
        
    lang = meta.get("language", "").lower()
    if lang in ("en", "eng", "english"):
        return True
    if lang in ("pt", "por", "portuguese"):
        return False
        
    title = meta.get("title", "").lower()
    journal = meta.get("journal", "").lower()
    publisher = meta.get("publisher", "").lower()
    city = meta.get("city", "").lower()
    event = meta.get("event_name", "").lower()
    
    # Se contiver instituições, cidades ou vocabulário português -> Português (False)
    pt_keywords = {
        "unicamp", "ufmg", "ufrj", "usp", "ifrn", "ufrn", "uff", "uerj", "ufsc", "ufpr", "ufpe", "ufba", "ufc",
        "galoa", "galoá", "redes", "scielo", "cortez", "vozes", "rio de janeiro", "são paulo", "campinas", "natal",
        "brasília", "brasilia", "porto alegre", "niterói", "niteroi", "brasil", "brazil", "da", "do", "dos", "das",
        "em", "para", "com", "uma", "um", "pesquisa", "educação", "educacao", "ensino", "ciências", "ciencias"
    }
    ctx = f"{title} {journal} {publisher} {city} {event}"
    if any(k in ctx for k in pt_keywords):
        return False

    if any(k in city for k in ("uk", "us", "ny", "ma", "ca", "london", "oxford", "cambridge", "washington")):
        return True
        
    en_keywords = {"the", "and", "of", "in", "for", "on", "with", "journal", "studies", "planning", "review", "international", "urban", "gated", "research", "gated communities"}
    title_words = set(re.sub(r'[^\w\s]', '', title).split())
    journal_words = set(re.sub(r'[^\w\s]', '', journal).split())
    
    if en_keywords.intersection(title_words) or en_keywords.intersection(journal_words):
        return True
        
    return False

def format_date_abnt(year: str, start_month: int = None, end_month: int = None, day: int = None, is_english: bool = False) -> str:
    """Formata data no padrão ABNT (em português ou inglês dependendo do idioma da obra)."""
    if not year:
        return ""
    
    months_dict = ABNT_MONTHS_EN if is_english else ABNT_MONTHS_PT
    
    if day and start_month:
        m1 = months_dict.get(start_month, "")
        return f"{day} {m1} {year}"
    elif start_month and end_month and start_month != end_month:
        m1 = months_dict.get(start_month, "")
        m2 = months_dict.get(end_month, "")
        return f"{m1}/{m2} {year}"
    elif start_month:
        m1 = months_dict.get(start_month, "")
        return f"{m1} {year}"
    return str(year)

def format_date_apa(year: str, start_month: int = None, end_month: int = None, day: int = None) -> str:
    """Formata data no padrão APA em inglês/português (ex: 2014, 15 de dezembro / 2015, Feb./Aug. / 2020)."""
    if not year:
        return "n.d."
    if day and start_month:
        PT_FULL_MONTHS = {
            1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio", 6: "junho",
            7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
        }
        m_full = PT_FULL_MONTHS.get(start_month, "")
        return f"{year}, {day} de {m_full}"
    elif start_month and end_month and start_month != end_month:
        m1 = ABNT_MONTHS_EN.get(start_month, "")
        m2 = ABNT_MONTHS_EN.get(end_month, "")
        return f"{m1}/{m2} {year}"
    elif start_month:
        m1 = ABNT_MONTHS_EN.get(start_month, "")
        return f"{m1} {year}"
    return str(year)

def get_current_abnt_date():
    today = datetime.datetime.now()
    month_str = ABNT_MONTHS_PT.get(today.month, "")
    return f"{today.day} {month_str} {today.year}"
