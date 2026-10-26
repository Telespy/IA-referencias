# Fluxo de correção e verificação de referências ABNT

## Objetivo

Este projeto não trata mais a correção bibliográfica como um simples problema de regex ou de formatação. O fluxo foi reorganizado para separar claramente:

1. **entrada original**;
2. **normalização segura**;
3. **classificação documental**;
4. **extração de metadados**;
5. **resolução da identidade da obra**;
6. **enriquecimento por fontes confiáveis**;
7. **proveniência e confiança por campo**;
8. **validação dos elementos obrigatórios**;
9. **formatação ABNT/APA**;
10. **devolução como verificada ou revisão necessária**.

O princípio central é: **o sistema não deve inventar informação para conseguir montar uma referência aparentemente completa**.

---

## 1. Entrada recebida

A referência é recebida exatamente como o usuário a enviou.

Exemplo de entrada com ruído:

```text
AFP. Indústria da música está ameaçada por bandas geradas por IA: 'desafio incomparável'. **O Globo**, 30 jul. 2025.
Disponível em: https\://oglobo.\
&#x20;globo.com/... Acesso em: 16 ago. 2026.
```

O valor original permanece disponível em:

```python
result["raw"]
```

Ele nunca é sobrescrito pela normalização.

---

## 2. Normalização

Arquivo principal:

```text
normalizer.py
```

A função `normalize_reference_input()` cria uma cópia limpa para processamento.

### Tratamentos executados

- normalização Unicode em NFC;
- remoção de caracteres invisíveis;
- decodificação de entidades HTML, como `&#x20;`;
- correção de protocolos escapados, como `https\://`;
- reconstrução de URLs quebradas em linhas;
- remoção de marcação Markdown de apresentação, como `**título**`;
- remoção de continuações com barra invertida;
- normalização de espaços, tabs e quebras de linha.

Cada transformação é registrada em:

```python
result["normalization_steps"]
```

A versão realmente enviada ao parser fica em:

```python
result["normalized_input"]
```

Assim é possível auditar a diferença entre o que foi recebido e o que foi processado.

---

## 3. Classificação documental

Arquivo:

```text
parsers.py
```

A função `detect_reference_type()` decide o tipo documental usando sinais da referência completa.

Tipos atualmente suportados incluem:

- livro;
- capítulo de livro;
- artigo de periódico;
- trabalho em evento/anais;
- tese, dissertação, monografia e TCC;
- legislação;
- projeto de lei;
- jurisprudência;
- artigo de jornal;
- website/documento eletrônico;
- patente;
- documento institucional.

### Mudança importante

**Autor institucional não define mais o tipo do documento.**

Antes, uma obra assinada por ABNT, OMS, IBGE ou WIPO podia ser classificada automaticamente como documento institucional apenas por possuir autor corporativo.

Agora a classificação depende da estrutura e dos sinais documentais.

Exemplos:

- ABNT pode ser autora de um livro;
- OMS pode ser autora de uma página eletrônica;
- WIPO pode ser autora e editora de uma publicação;
- IBGE pode publicar livros, relatórios, datasets ou páginas web.

---

## 4. Extração inicial

Depois da classificação, `parse_raw_citation_text()` extrai somente os elementos que consegue identificar na entrada.

Exemplos de campos:

```text
authors
title
book_title
journal
newspaper
city
publisher
year
volume
issue
page
doi
isbn
url
access_date
institution
degree_type
degree_year
```

O parser não deve inventar valores ausentes.

---

## 5. Resolução da identidade da obra

Arquivo:

```text
resolver_pipeline.py
```

A função central é:

```python
resolve_reference(clean_text, parsed, online=True)
```

Ela tenta determinar se a obra encontrada é realmente a mesma obra informada pelo usuário.

### Hierarquia de resolução

O sistema pode usar:

1. registros de autoridade previamente verificados;
2. identificadores fortes, como DOI e ISBN;
3. metadados da página oficial;
4. bases bibliográficas estruturadas;
5. cadastro de entidades;
6. metadados fornecidos pelo usuário.

Quanto mais baixo nessa lista, menor deve ser a confiança.

---

## 6. Registros de autoridade verificados

Arquivo:

```text
data/verified_records.json
```

Este arquivo funciona como uma cache auditável de registros que já foram conferidos contra uma fonte confiável.

Cada registro contém:

- critérios de correspondência;
- metadados corrigidos;
- fonte usada;
- URL da fonte;
- confiança.

Exemplo conceitual:

```json
{
  "match": {
    "title": "O que é propriedade intelectual?",
    "entity": "WIPO"
  },
  "metadata": {
    "item_type": "book",
    "city": "Genebra",
    "publisher": "WIPO",
    "year": "2021"
  },
  "source_name": "WIPO Publications / TIND",
  "confidence": 1.0
}
```

O objetivo não é criar exceções escondidas no código. O registro fica separado, legível, versionável e auditável.

---

## 7. Cadastro de autoridade institucional

Arquivo:

```text
data/authority_registry.json
```

Este arquivo identifica entidades conhecidas e seus dados institucionais.

Exemplos cadastrados:

- WIPO / OMPI;
- O Globo;
- Fundação Getulio Vargas;
- IBGE;
- OMS.

Um perfil de entidade pode informar:

- aliases;
- nome corporativo;
- cidade institucional;
- editora;
- jornal/site;
- URL oficial da entidade.

### Regra de segurança

**Um perfil institucional sozinho não verifica uma obra.**

Ele pode enriquecer um campo, mas:

```python
_work_verified = False
```

Portanto, o sistema não aprova uma referência apenas porque reconheceu a entidade.

---

## 8. Resolução por página oficial

`resolver_pipeline.py` também possui:

```python
fetch_public_page_metadata(url)
```

Ela pode extrair metadados bibliográficos de páginas públicas por:

- `citation_*`;
- Dublin Core;
- Open Graph;
- JSON-LD.

Campos recuperáveis incluem:

- título;
- autor;
- editora;
- site;
- data;
- periódico;
- URL canônica.

### Segurança contra SSRF

Antes de consultar uma URL, o sistema rejeita:

- `localhost`;
- IP de loopback;
- IP privado;
- IP link-local;
- endereços reservados;
- protocolos diferentes de HTTP/HTTPS;
- hostnames que resolvam para rede privada.

O objetivo é impedir que uma referência maliciosa faça o servidor consultar recursos internos.

---

## 9. Fontes especializadas já existentes

A nova arquitetura preservou as integrações maduras do sistema.

### DOI / artigos

Crossref.

### ISBN / livros

Google Books e Open Library.

### Legislação

Fontes oficiais brasileiras, incluindo Senado/Planalto.

### Jurisprudência

Resolver específico para STF.

### Locais de publicação

Normalização geográfica existente em `publication_places.py`.

---

## 10. Proveniência por campo

Arquivo principal do pipeline:

```text
correction.py
```

Cada campo pode possuir informações como:

```python
result["provenance"]["city"]
```

Exemplo:

```json
{
  "source": "WIPO Publications / TIND",
  "url": "https://tind.wipo.int/record/44584",
  "verified": true,
  "confidence": 1.0
}
```

Isso evita a situação em que uma referência aparece correta sem ser possível saber de onde veio cada informação.

---

## 11. Diferença entre extraído, enriquecido e verificado

### Extraído

Veio somente da entrada do usuário.

Em geral:

```text
verified = false
```

### Enriquecido

Foi complementado por cadastro institucional ou inferência controlada.

Pode possuir confiança alta, porém não necessariamente verifica a identidade completa da obra.

### Verificado

A obra foi identificada por uma fonte adequada e o campo possui evidência.

Exemplo:

```text
verified = true
confidence = 1.0
```

---

## 12. Regra fail closed

O sistema não busca "aprovar tudo".

Existem dois estados principais:

### verified

A identidade foi confirmada, não há pendências bloqueantes e os campos obrigatórios foram validados.

```python
result["approved"] == True
result["status"] == "verified"
```

### needs_review

Falta evidência, existe conflito, falta campo obrigatório ou a fonte não pôde ser consultada.

```python
result["approved"] == False
result["status"] == "needs_review"
```

Esta regra é essencial para precisão elevada.

É preferível devolver:

> revisão necessária

do que inventar cidade, editora, subtítulo, DOI ou autoria.

---

## 13. Validação ABNT

A validação de campos obrigatórios continua centralizada nas regras de `formatters.py` e no pipeline de `correction.py`.

A lista de pendências é devolvida em:

```python
result["missing_fields"]
```

E os alertas em:

```python
result["issues"]
result["warnings"]
```

Exemplo:

```text
Cidade de publicação
Nome da editora
URL oficial
Instituição
Grau acadêmico
Páginas
DOI/URL
```

As exigências variam conforme o tipo documental.

---

## 14. Formatação

Somente depois da resolução e validação os metadados são passados ao formatter.

Arquivo:

```text
formatters.py
```

Funções principais:

```python
format_abnt(meta)
format_apa(meta)
```

O formatter não deve ser responsável por descobrir dados bibliográficos.

A responsabilidade dele é exclusivamente transformar metadados estruturados em texto.

---

## 15. Título e subtítulo

Título e subtítulo são armazenados semanticamente na propriedade `title`, separados por dois pontos quando a fonte oficial assim os apresenta.

Exemplo:

```text
Clareza e legitimidade: como elementos de teoria musical podem iluminar a interpretação jurídica?
```

Na saída ABNT:

```text
**Clareza e legitimidade**: como elementos de teoria musical podem iluminar a interpretação jurídica?
```

O sistema também evita acrescentar ponto artificial depois de `?` ou `!`.

---

## 16. Exemplo real: O Globo

Entrada problemática:

```text
AFP. ... **O Globo**, 30 jul. 2025. Disponível em: https\://oglobo.\
&#x20;globo.com/...
```

Fluxo:

1. Markdown removido;
2. HTML decodificado;
3. URL reconstruída;
4. obra identificada pelo URL/título;
5. veículo confirmado como O Globo;
6. cidade completada como Rio de Janeiro;
7. fonte registrada;
8. referência formatada.

Resultado:

```text
AFP. Indústria da música está ameaçada por bandas geradas por IA: 'desafio incomparável'. **O Globo**, Rio de Janeiro, 30 jul. 2025. Disponível em: [...]. Acesso em: 16 ago. 2026.
```

---

## 17. Exemplo real: FGV

A entrada fornecia apenas:

```text
Clareza e legitimidade
```

O registro verificado recupera:

```text
Clareza e legitimidade: como elementos de teoria musical podem iluminar a interpretação jurídica?
```

Também separa corretamente:

```text
institution = Fundação Getulio Vargas
city = Rio de Janeiro
```

O URL não contamina mais o campo de cidade.

---

## 18. Exemplo real: WIPO

Entrada:

```text
WIPO. O que é propriedade intelectual? WIPO, 2021.
```

O registro oficial permite recuperar:

```text
author = WIPO
city = Genebra
publisher = WIPO
year = 2021
isbn = 9789280532265
doi = 10.34667/tind.44584
```

Assim o sistema não produz mais `[S. l.]: [s. n.]` quando existe evidência confiável.

---

## 19. Como adicionar uma nova entidade

Editar:

```text
data/authority_registry.json
```

Adicionar:

- nome principal;
- aliases;
- cidade;
- editora/site;
- URL institucional.

Nunca marcar automaticamente a obra como verificada apenas por esse cadastro.

---

## 20. Como adicionar um registro já verificado

Editar:

```text
data/verified_records.json
```

Registrar:

1. critérios de match;
2. metadados completos;
3. nome da fonte;
4. URL da fonte;
5. confiança.

Só devem entrar registros conferidos em fonte adequada.

---

## 21. Testes

Arquivos importantes:

```text
test_pipeline_v4.py
test_extreme_abnt.py
test_reference_system.py
test_correction.py
test_title_legal.py
test_case_law.py
test_article_enrichment.py
test_publication_places.py
```

### Resultado após a revisão arquitetural

Suíte completa:

```text
180 passed
88 subtests passed
```

Bateria extrema:

```text
48/48
100.00%
```

Os testes adicionais cobrem:

- URL escapada;
- HTML dentro de URL;
- quebra de URL em linhas;
- Markdown;
- subtítulo recuperado;
- cidade ausente;
- editora institucional;
- DOI/ISBN recuperados;
- proveniência;
- confiança;
- SSRF;
- autor institucional;
- artigos online sem paginação física;
- títulos interrogativos;
- regra de não aprovação baseada somente no perfil institucional.

---

## 22. O que significa "100%"

O resultado de 100% refere-se à suíte adversarial atual.

Nenhum sistema bibliográfico pode garantir matematicamente 100% de acerto sobre qualquer entrada futura, porque:

- fontes podem estar erradas;
- páginas podem desaparecer;
- metadados podem divergir;
- documentos podem estar incompletos;
- duas obras podem possuir títulos muito semelhantes.

Por isso a arquitetura foi desenhada para maximizar **precisão**, não para forçar cobertura.

A regra desejada é:

```text
se tenho evidência suficiente -> devolvo verificada
se não tenho evidência suficiente -> devolvo revisão necessária
```

Essa estratégia é muito mais segura do que preencher lacunas por suposição.

---

## 23. Fluxo resumido

```text
REFERÊNCIA RECEBIDA
        |
        v
NORMALIZAÇÃO
  normalizer.py
        |
        v
CLASSIFICAÇÃO + EXTRAÇÃO
  parsers.py
        |
        v
RESOLUÇÃO DA OBRA
  resolver_pipeline.py
        |
        +--> verified_records.json
        +--> authority_registry.json
        +--> página oficial
        +--> Crossref
        +--> Google Books / Open Library
        +--> fontes jurídicas
        |
        v
PROVENIÊNCIA POR CAMPO
  correction.py
        |
        v
VALIDAÇÃO
  campos obrigatórios
  conflitos
  confiança
  identidade
        |
        +--> insuficiente -> NEEDS_REVIEW
        |
        v
FORMATAÇÃO
  formatters.py
        |
        v
REFERÊNCIA ABNT / APA
        |
        v
VERIFIED
```

---

## 24. Regra para futuras evoluções

Ao encontrar um novo erro real:

1. transformar o caso em teste de regressão;
2. identificar em qual camada ocorreu a falha;
3. corrigir a regra geral nessa camada;
4. evitar exceção hardcoded quando houver uma regra generalizável;
5. quando o dado só puder ser conhecido por uma fonte específica, adicionar um resolver ou registro de autoridade auditável;
6. rodar toda a suíte;
7. não aceitar regressões em tipos já estabilizados.

Esse processo deve ser mantido para aumentar cobertura sem reduzir a precisão.
