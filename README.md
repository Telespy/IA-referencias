# Brain Format

Corretor local de referencias com API FastAPI, interface web e integracao com
Hermes em Docker. Cada resultado inclui uma proposta ABNT/APA, alteracoes,
fontes consultadas e pendencias de revisao.

O sistema nao promete corrigir qualquer documento sem erros. Uma referencia
incompleta, ambigua ou nao confirmada permanece marcada para revisao. A
formatacao sozinha nao comprova que a obra exista.

## Usar

Abra o [corretor](http://localhost:8000) ou o
[painel do Hermes](http://localhost:9119).
O [guia local](GUIA_LOCAL.md) explica credenciais, inicializacao, Telegram,
limites de cobertura e testes.
A [documentacao completa](DOCUMENTACAO.md) descreve a arquitetura, os fluxos,
o contrato da API, as fontes e a manutencao.

Para iniciar na pasta do projeto:

```powershell
python -m pip install -r requirements.txt
python scripts/setup_local.py
docker compose up -d --build
docker compose exec -T --user hermes hermes hermes plugins enable brain-format --no-allow-tool-override
docker compose exec -T --user hermes hermes hermes config set gateway.multiplex_profiles false
docker compose exec -T --user hermes hermes hermes config set telegram.typing_indicator true
docker compose exec -T --user hermes hermes hermes config set platform_toolsets.telegram '[brain_format]'
docker compose exec -T --user hermes hermes hermes config set platform_toolsets.api_server '[brain_format]'
docker compose exec -T --user hermes hermes hermes config set model.context_length 64000
docker compose exec -T --user hermes hermes hermes config set tools.tool_search.enabled off
docker compose exec -T --user hermes hermes hermes config set agent.reasoning_effort false
docker compose restart hermes
```

O volume existente do Ollama e a pasta de dados do Hermes sao preservados.
O modelo configurado neste computador e `hermes3`, servido por
`http://ollama:11434/v1`. Uma instalacao em outro computador precisa baixar
o modelo e configurar o provider do Hermes conforme o guia.

## Telegram

Depois de criar o bot no BotFather:

```powershell
python scripts/setup_local.py --telegram
docker compose up -d --force-recreate hermes
```

No Windows, cole o token na janela local com campo oculto e informe seu ID numerico.
Em outros sistemas, use o prompt local. Nao envie o token em conversas.
Na conversa privada com o bot, envie `/referencias` e a lista na mesma mensagem.
O comando devolve o relatorio da API, incluindo os avisos. A ferramenta
`corrigir_referencias` tambem fica disponivel para o agente Hermes.

## Correcao e cobertura

- Artigos: consulta por DOI; busca por titulo quando existe contexto suficiente;
  conferencia de autoria, ano e tipo; recusa de correspondencias ambiguas.
  Para registros cobertos, complementacao por Europe PMC/PubMed e XML JATS do PMC:
  volume, numero, localizador, autoria e periodo explicito do fasciculo.
  Local pode ser obtido no NLM Catalog, vinculado por ISSN e intervalo de publicacao,
  entre colchetes; afiliacao do autor nunca e usada como local do periodico.
- Locais brasileiros sao normalizados com uma base local do IBGE: pais
  redundante removido, UF usada para homonimos identificados e colchetes
  preservados. Ambiguidades nao resolvidas impedem aprovacao; qualificadores
  estrangeiros nao sao removidos indiscriminadamente. Veja `data/README.md`.
- Livros: consulta por ISBN validado em Google Books e Open Library;
  consulta alternativa por edicao e equivalencia ISBN-10/13;
  resultados com ISBN de outra edicao sao recusados.
- Titulos isolados: descoberta na Crossref e Open Library, com candidatos no
  JSON e nos relatorios. Correspondencias aproximadas/ambiguas pedem DOI ou
  ISBN. Livros identificados apenas como obra continuam pendentes de edicao;
  ano/editora de edicoes diferentes nunca sao combinados.
- Leis ordinarias e complementares federais: consulta ao cadastro oficial do
  Senado por tipo, numero e ano; recuperacao de ementa, assinatura e publicacao
  original. Secao e paginacao completa do DOU permanecem sinalizadas para
  revisao quando o cadastro so fornece pagina inicial.
- Projetos de lei: consultas oficiais da Camara dos Deputados e Senado Federal,
  com casa explicita. O projeto nunca e apresentado como lei sancionada, e a
  situacao consultada aparece separada da referencia. Nao certifica vigencia.
- Leis estaduais/municipais, atos sem identificacao, outros tipos legislativos,
  capitulos, eventos, teses, patentes e sites: formatacao dos
  elementos identificados e avisos sobre o que ainda nao foi verificado.
- Tipos documentais reconhecidos como fora da cobertura: preservacao da entrada.
- Data de acesso ausente usa o dia da correcao, no fuso America/Sao_Paulo, somente
  apos uma consulta online bem-sucedida. E marcada como gerada, nao como um dado
  bibliografico verificado nem como teste de disponibilidade do link.
  Datas fornecidas sao preservadas e validadas; offline nao se gera acesso.
- Anos, editoras, ementas e periodos nao sao inventados. Conflitos entre fontes
  bloqueiam a aprovacao; falhas de complementacao preservam os dados ja recuperados.
- A fonte de cada campo e as alteracoes ficam no JSON; avisos acompanham
  copias, downloads e respostas do comando Hermes.

A implementacao cobre modelos da familia ABNT NBR 6023 e APA 7, mas nao e uma
certificacao integral da norma ou de toda a diversidade documental.
`fetchers.py` e `config.py` ainda contem rotinas legadas de enriquecimento; a
API atual usa `sources.py`, `article_enrichment.py`, `title_lookup.py`,
`legal_references.py` e `correction.py`, sem aquelas inferencias.

## Titulos, leis e projetos no Telegram

Envie uma unica mensagem, com uma entrada por linha:

```text
/referencias
Titulo: ELMO 1.0: a helmet interface for CPAP and high-flow oxygen delivery
Dom Casmurro
Lei federal 11892/2008
Lei complementar federal 101/2000
Camara dos Deputados. PL 2630/2020
Senado Federal. PL 2338/2023
```

O prefixo `Titulo:` e opcional para titulos simples e recomendado quando ha
pontuacao que possa parecer uma referencia completa. Para livros, reenvie o
ISBN da edicao que voce realmente consultou. Candidatos nao sao uma escolha
automatica e nao sao guardados como estado de conversa.

`Lei 11892/2008` pede confirmacao da jurisdicao; `PL 2630/2020` pede a casa.
Nao ha consulta automatica universal a legislacoes estaduais/municipais ou
busca de leis por apelido. Nesses casos, o sistema informa a limitacao.

Fontes: [Senado - legislacao](https://www12.senado.leg.br/dados-abertos/legislativo/legislacao),
[Camara - Dados Abertos](https://dadosabertos.camara.leg.br/swagger/api.html),
[Open Library - busca](https://openlibrary.org/dev/docs/api/search).
Locais legislativos modernos entre colchetes sao atribuicoes documentadas
pela sede oficial do orgao/veiculo, com `derived: true` na evidencia. Essa
regra nao se estende a revistas, editoras desconhecidas ou documentos antigos.

## API

`POST /api/format`:

```json
{"text": "referencia 1\nreferencia 2", "online": true}
```

Retorna `status`, `approved`, `identity_verified`, `meta`, `issues`,
`corrections`, `provenance`, `sources`, `candidates`, `missing_fields` e relatorios.
`verified` significa conferencia dos campos avaliados nas fontes consultadas;
`needs_review` significa proposta pendente; `error` preserva a entrada.

Limites: 50 referencias, 4000 caracteres por referencia e 512 KB por requisicao.
Com `online: false`, nenhuma consulta bibliografica e realizada.
Em modo online, o modelo continua local, mas os metadados sao consultados na internet.

Documentacao interativa: [API](http://localhost:8000/api/docs).

## Desenvolvimento

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -p "test*.py" -v
node test_frontend.cjs
python scripts/verify_references.py
uvicorn api.index:app --reload --port 8001
```

O formato de resposta da API foi ampliado para incluir evidencias. Os campos
`abnt_full`, `apa_full` e `comp_full` incluem avisos, intencionalmente.
