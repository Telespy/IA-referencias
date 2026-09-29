# Documentacao do Brain Format

Este documento descreve o sistema publicado neste repositorio: finalidade,
componentes, instalacao, caminhos de uso, regras de verificacao, limites e
manutencao. Para instrucoes curtas, consulte [README.md](README.md). Para
detalhes da configuracao desta maquina, consulte [GUIA_LOCAL.md](GUIA_LOCAL.md).

## 1. Finalidade e principio de funcionamento

O Brain Format recebe uma referencia, identificador ou titulo e produz uma
proposta de referencia ABNT e APA. Ele tambem devolve as correcoes efetuadas,
as fontes consultadas, a origem de cada campo e os dados que precisam de
conferencia. Processa ate 50 entradas por chamada da API.

A API faz a busca bibliografica e a formatacao. O Hermes e uma interface
opcional para conversar com o sistema; o comando `/referencias` chama a API
diretamente e devolve seu relatorio. O modelo local nao substitui a consulta
as fontes e nao precisa reescrever a referencia. Nao ha RAG, fine-tuning nem
banco de dados proprio de referencias nesta implementacao.

`approved: true` indica somente que as verificacoes implementadas nao
identificaram pendencias nos campos avaliados. Nao certifica conformidade
integral com a ABNT, exatidao das fontes externas ou vigencia de uma norma.

## 2. Arquitetura

```text
Navegador (localhost:8000) ────────┐
                                    ├──> FastAPI /api/format
Telegram ──> Hermes ──> plugin ─────┘          │
             │                                 ├──> parser e identificacao
             └──> Ollama/hermes3               ├──> consultas externas
                  (conversa opcional)           ├──> confronto de identidade
                                                ├──> correcoes com proveniencia
                                                └──> ABNT, APA e avisos
```

| Componente | Responsabilidade |
| --- | --- |
| `api/index.py` | Endpoint, validacao dos lotes, limites, erros por entrada e interface estatica. |
| `main.py` | Liga o fluxo de correcao aos conectores. |
| `parsers.py` | Extrai campos e classifica a referencia informada. |
| `correction.py` | Consulta, compara, corrige, registra evidencias e decide pendencias. |
| `reference_validation.py` | Compara titulos, autoria, ano e tipo antes de aceitar um registro. |
| `sources.py` | Crossref, Google Books e Open Library por DOI/ISBN; transporte HTTP com limites. |
| `title_lookup.py` | Busca por titulo na Crossref e Open Library e lista candidatos. |
| `article_enrichment.py` | Complementa artigos com Europe PMC, XML do PMC e NLM Catalog. |
| `legal_references.py` | Leis federais no Senado e projetos de lei nas duas casas. |
| `publication_places.py` | Normaliza localidades brasileiras sem atribuir uma editora/revista a sua sede. |
| `formatters.py` | Monta as saidas ABNT e APA e identifica elementos ausentes. |
| `public/` | Interface web e visualizacao de avisos, fontes e candidatos. |
| `integrations/hermes/brain-format/` | Comando `/referencias` e ferramenta `corrigir_referencias`. |
| `data/brazilian_places.json` | Instantaneo local de municipios e unidades federativas do IBGE. |
| `scripts/` | Configuracao, inicializacao, atualizacao de localidades e verificacoes. |

`Dockerfile` empacota a API. `docker-compose.yml` inicia os servicos
`brain-format`, `ollama` e `hermes`. O volume `ollama-data` guarda os modelos;
`hermes-data/` guarda a configuracao local do Hermes. Nenhum desses dados
precisa ser enviado ao GitHub.

`config.py`, `fetchers.py`, `app.py`, `run.py` e `vercel.json` sao arquivos
anteriores/auxiliares. O fluxo principal em Docker utiliza os modulos da
tabela acima. A configuracao atual de publicacao e a do Docker Compose.

## 3. Requisitos e instalacao

Requisitos: Docker Desktop com Compose, Python 3 para os scripts de
configuracao, acesso a internet para baixar imagens/modelo e consultar
fontes, e um bot criado no BotFather caso queira Telegram. A API usa Python
3.11 dentro do container. Sem internet, a entrada pode ser formatada, mas
nao recebe confirmacao bibliografica externa.

No PowerShell, clone o repositorio e entre na pasta:

```powershell
git clone https://github.com/Telespy/IA-referencias.git
Set-Location IA-referencias
```

Dentro da pasta clonada:

```powershell
python -m pip install -r requirements.txt
python scripts/setup_local.py
docker compose up -d --build
docker compose exec ollama ollama pull hermes3
```

O ultimo comando e necessario em uma instalacao nova. Nesta maquina o modelo
ja pode existir no volume Docker. Para ativar o plugin e a configuracao usada
na integracao local, execute:

```powershell
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

O script `scripts/start.ps1` executa a inicializacao local e essas etapas
depois de preparadas as dependencias. Para usar a conversa por IA em uma
instalacao nova, configure o provider `custom` do Hermes para o modelo
`hermes3` em `http://ollama:11434/v1`; consulte [GUIA_LOCAL.md](GUIA_LOCAL.md)
e a documentacao do Hermes indicada ao fim deste arquivo. A correcao via
interface web funciona sem o modelo estar pronto.

Enderecos publicados somente no computador local:

| Endereco | Uso |
| --- | --- |
| `http://localhost:8000` | Corretor web. |
| `http://localhost:8000/api/docs` | Esquema e testes interativos da API. |
| `http://localhost:8000/api/health` | Saude do servico. |
| `http://localhost:9119` | Painel do Hermes. |
| `http://localhost:8642` | Servidor de API do Hermes. |
| `http://localhost:11434` | Ollama. |

O usuario padrao do painel local e `referencias`. A senha e gerada em
`hermes-dashboard.local.env` na primeira inicializacao. Nao publique esse
arquivo nem o token do bot.

## 4. Telegram e Hermes

1. Crie o bot pelo `@BotFather` e obtenha o ID numerico da sua conta.
2. Execute `python scripts/setup_local.py --telegram` na pasta do projeto.
3. Cole o token no campo oculto e informe o ID da sua conta, sem `@`.
4. Execute `docker compose up -d --force-recreate hermes`.
5. Abra a conversa privada com o bot e envie `/referencias` e a lista na
   mesma mensagem, uma entrada por linha.

O cadastro valida o token com `getMe` e grava `telegram.local.env`, ignorado
pelo Git. O Hermes responde somente aos IDs permitidos na configuracao.
Durante o processamento, o comando tenta confirmar o recebimento e o Hermes
pode mostrar o indicador de digitacao. O comando `/stop` interrompe a tarefa
no agente; uma chamada HTTP ja iniciada pode terminar no servidor.

Exemplo:

```text
/referencias
Titulo: ELMO 1.0: a helmet interface for CPAP and high-flow oxygen delivery
Dom Casmurro
Lei federal 11892/2008
Lei complementar federal 101/2000
Camara dos Deputados. PL 2630/2020
Senado Federal. PL 2338/2023
```

O comando devolve o relatorio da API. O Hermes tambem registra a ferramenta
`corrigir_referencias` para conversas em linguagem natural. Nesse segundo
caminho, o modelo escolhe chamar a ferramenta e pode resumir a resposta;
use o comando direto ou a interface web quando precisar do texto integral.
Anexos PDF/DOCX/TXT nao sao lidos automaticamente pelo comando.

## 5. Entradas aceitas e fontes

| Entrada | Busca e comportamento |
| --- | --- |
| DOI | Consulta Crossref e verifica a identidade da obra. |
| Artigo com titulo/autoria/ano | Busca Crossref, compara candidatos e complementa quando possivel. |
| Titulo isolado | Busca Crossref e Open Library; para artigo selecionado, reconfirma o DOI na Crossref antes de usar os metadados. Candidatos ambiguos sao exibidos. |
| ISBN | Confere digito verificador e consulta Google Books/Open Library. |
| Lei federal ordinaria | Confere numero, ano, data e ementa na pagina oficial do Planalto (atos desde 2003). Se indisponivel, tenta o cadastro do Senado. |
| Lei complementar federal | Consulta o cadastro de normas do Senado por tipo, numero e ano. |
| PL com casa identificada | Consulta processos do Senado ou proposicoes da Camara. |
| Outros tipos reconhecidos | Formata os elementos informados e indica os nao verificados. |

Artigos identificados podem receber volume, numero, pagina/localizador,
periodo e autoria de Europe PMC/PMC. Quando Europe PMC falha, o ISSN da
Crossref pode identificar um registro unico no NLM Catalog. O local da
revista so e atribuido quando ISSN, ano e intervalo da sede editorial
concordam; mudancas de sede com data explicita sao respeitadas. A base
do IBGE padroniza nomes de cidades brasileiras e preserva qualificadores
necessarios. A sede atual de revista/editora nao comprova, por si so, o
local da publicacao citada.

Titulo de livro costuma identificar a obra, mas nao a edicao utilizada.
Nesse caso, informe o ISBN da edicao. `Lei 11892/2008` sem jurisdicao pede
esclarecimento; `PL 2630/2020` sem casa legislativa tambem. Projetos sao
referenciados como projetos, com a situacao informada separadamente e datada.

Quando a pagina do Planalto e conferida, a lei usa titulo em negrito, ementa,
`Brasilia, DF: Presidencia da Republica, ano`, URL oficial e data de acesso.
Exemplo: `Lei federal 12503/2011`. O local decorre da data e local indicados
no proprio ato; a consulta nao comprova vigencia. Se o Planalto nao responder,
o sistema nao atribui essa URL sem conferencia. Para leis, o cadastro do Senado pode fornecer apenas a pagina inicial do
Diario Oficial da Uniao. Secao e paginacao completa ficam pendentes quando
nao aparecem na fonte. A consulta bibliografica nao determina vigencia,
revogacao total nem texto consolidado. Leis estaduais e municipais e busca
por apelido ainda nao possuem consulta automatica abrangente. Teses,
capitulos, congressos, patentes e paginas podem ser formatados, mas dados
ausentes ou sem fonte permanecem em revisao.

Uma URL comum informada pelo usuario e preservada, mas nao e rastreada
arbitrariamente. URLs DOI seguras podem ser usadas para recuperar o DOI.
As consultas a legislacao usam dominios oficiais fixos. Falhas de conexao,
respostas inconsistentes e correspondencias multiplas viram avisos.

## 6. API e contrato de resposta

`POST /api/format` recebe JSON:

```json
{
  "text": "Lei federal 11892/2008\nSenado Federal. PL 2338/2023",
  "online": true,
  "input_format": "lines"
}
```

`input_format: "lines"` usa cada linha como uma referencia. Para referencias
com quebras internas, use `"blocks"` e separe blocos por uma linha vazia.
`online: false` impede consultas bibliograficas externas. Limites atuais:
50 referencias, 4.000 caracteres por referencia e 512 KB por requisicao.
Ha limite de 60 chamadas por minuto por IP, em memoria do processo da API.

A resposta inclui `results`, `summary`, `abnt_full`, `apa_full` e `comp_full`.
Cada item em `results` contem:

| Campo | Significado |
| --- | --- |
| `raw`, `meta`, `item_type` | Entrada, campos usados e tipo de documento. |
| `abnt`, `apa` | Texto proposto nos dois estilos. |
| `status`, `approved` | `verified`/`true` somente sem pendencia bloqueante; `needs_review` ou `error` nos demais casos. |
| `identity_verified` | Uma obra compativel foi encontrada; outros campos ainda podem faltar. |
| `issues`, `warnings`, `missing_fields` | Problemas, avisos e elementos a conferir. |
| `corrections` | Campo alterado, antes/depois e fonte da alteracao. |
| `provenance`, `sources` | Fonte por campo e fontes consultadas; `derived` indica valor atribuido. |
| `candidates` | Obras alternativas apresentadas quando o titulo nao basta. |
| `unverified_fields`, `verification_scope` | Campos sem prova e alcance da conferencia. |

O acesso ausente e preenchido com a data da correcao no fuso
`America/Sao_Paulo` quando houve consulta online bem-sucedida e existe DOI
ou URL. Isso aparece como dado gerado e nao comprova que o link foi aberto.
Datas fornecidas sao preservadas e avaliadas; uma data futura vira aviso.
Sem fonte, o sistema preserva a entrada e nao declara verificacao.

Exemplo no PowerShell:

```powershell
$body = @{ text = 'Lei federal 11892/2008'; online = $true } | ConvertTo-Json
Invoke-RestMethod 'http://localhost:8000/api/format' -Method Post -ContentType 'application/json' -Body $body
```

## 7. Seguranca e dados locais

`scripts/setup_local.py` cria `hermes-dashboard.local.env` e
`telegram.local.env`. O `.gitignore` exclui `*.local.env`, `hermes-data/`,
`artifacts/`, caches e ambientes virtuais. `.dockerignore` evita inserir
esses dados na imagem da API. `telegram.env.example` contem apenas campos
vazios. O bot e o painel continuam dependendo do computador e do Docker
ligados. As portas no Compose estao ligadas a `127.0.0.1`.

As consultas HTTP nao seguem redirecionamentos arbitrarios; ha limites de
tempo e tamanho de resposta. A API nao deve ser publicada diretamente na
internet sem um controle de acesso e limites adequados a esse ambiente.

## 8. Testes e manutencao

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -p 'test*.py' -q
node test_frontend.cjs
python scripts/verify_references.py
docker compose ps
```

Os testes unitarios cobrem parsing, identidade, alteracoes, conflitos,
proveniencia, artigos, locais, titulos, normas e API. `test_frontend.cjs`
verifica exibicao segura e preservacao de avisos. `scripts/verify_references.py`
exercita a API com entradas reais e sinteticas, salvando resultados em
`artifacts/reference-verification.md` e `.json`; falhas externas nao devem
ser confundidas com aprovacao. `scripts/verify_ui.cjs` e
`scripts/verify_title_legal_ui.cjs` fazem verificacoes visuais quando
Playwright e um navegador compativel estao disponiveis.

Para testar a integracao interna sem enviar mensagens ao Telegram, consulte
`scripts/verify_telegram.py` e [GUIA_LOCAL.md](GUIA_LOCAL.md). Enviar uma
mensagem real ao bot e a forma de testar o fluxo completo do Telegram.

Para atualizar o instantaneo de localidades brasileiras no PowerShell 7,
execute `pwsh -File scripts/update_place_authority.ps1`.
O script consulta o IBGE, valida a quantidade e os IDs antes de substituir
`data/brazilian_places.json`. Consulte [data/README.md](data/README.md) para
a politica de normalizacao e origem dos dados.

Para aplicar mudancas na API:

```powershell
docker compose up -d --build brain-format
```

Mudancas no plugin exigem `docker compose restart hermes`. Para investigar
problemas: `docker compose ps`, `docker compose logs --tail=100 brain-format`
e `docker compose logs --tail=100 hermes`. Nao publique logs que contenham
dados privados de conversas ou URLs de autenticacao.

## 9. Limites conhecidos e caminhos de evolucao

- Metadados externos podem estar incompletos ou divergentes; a API pode ficar
  temporariamente indisponivel. O resultado deve mostrar a pendencia.
- A busca por titulo nao garante que todos os catalogos ou edicoes estejam
  representados. DOI ou ISBN identificam melhor a obra/edicao.
- A cobertura legal automatica se concentra em normas federais e projetos
  das duas casas; outras jurisdicoes exigem conectores e regras proprias.
- A referencia bibliografica de uma lei nao representa sua situacao juridica
  atual. Vigencia, alteracoes e texto consolidado exigem verificacao separada.
- O sistema implementa regras de formatacao da familia ABNT NBR 6023 e APA 7,
  mas nao possui certificacao normativa nem cobre todos os tipos documentais.
- As imagens Docker usam a tag `latest`. Para reproducibilidade de producao,
  fixe versoes depois de validar a combinacao de Hermes e Ollama desejada.

Fontes tecnicas: [API Dados Abertos da Camara](https://dadosabertos.camara.leg.br/swagger/api.html),
[Legislacao no Senado](https://www12.senado.leg.br/dados-abertos/legislativo/legislacao),
[Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/),
[Open Library Search API](https://openlibrary.org/dev/docs/api/search),
[IBGE Localidades](https://servicodados.ibge.gov.br/api/docs/localidades),
[Hermes Docker](https://hermes-agent.nousresearch.com/docs/user-guide/docker).
