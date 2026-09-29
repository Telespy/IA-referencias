# Brain Format, Hermes e Telegram

O projeto esta nesta pasta. O processamento e a IA rodam no computador pelo Docker.
As consultas bibliograficas usam a internet (Crossref, Europe PMC, NLM Catalog,
Google Books e Open Library).
Mensagens do bot passam pelo Telegram. Modo local nao significa funcionamento totalmente offline.

## Abrir agora

- Corretor de referencias: http://localhost:8000
- Documentacao JSON da API: http://localhost:8000/api/docs
- Painel web do Hermes: http://localhost:9119
- Usuario do painel: `referencias`.
- Senha: campo `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` de `hermes-dashboard.local.env`.

Os arquivos `*.local.env` e `hermes-data/` ficam fora do Git e da imagem da API.
Nao publique esses arquivos. Os servicos sao expostos apenas no localhost.

## Inicializar novamente

No PowerShell, dentro da pasta do projeto:

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

Ou execute `powershell -ExecutionPolicy Bypass -File scripts/start.ps1`.
O modelo `hermes3` ja esta no volume existente do Ollama. Em outro computador,
baixe-o com `docker compose exec ollama ollama pull hermes3` e configure o Hermes
para provider `custom`, modelo `hermes3`, base URL `http://ollama:11434/v1`.

## Conectar ao Telegram

1. Crie um bot em https://t.me/BotFather com `/newbot` e guarde o token.
2. Obtenha seu ID numerico do Telegram, por exemplo com `@userinfobot`.
   Use o ID da sua conta, nao o nome `@usuario` e nao o ID do bot.
3. Na pasta do projeto, execute:

```powershell
python scripts/setup_local.py --telegram
```

No Windows, o programa abre uma janela para colar o token com Ctrl+V; os caracteres
aparecem como asteriscos. Depois, outra janela pede seu ID numerico. Copie somente
o token do BotFather, sem a mensagem que o acompanha. O programa valida o token com
`getMe` e grava `telegram.local.env`. Ele nao envia mensagens.
Em outros sistemas a entrada continua no terminal; no Windows, esse modo tambem
esta disponivel com `--telegram-terminal`. Cancelar a janela preserva o cadastro anterior.

Se aparecer "Formato de token invalido", o texto nao tem a estrutura de um token:
numeros, dois-pontos e codigo. Nao use o ID, API hash ou @usuario no campo do token.
"O Telegram recusou o token" significa que a consulta chegou ao Telegram, mas a
credencial nao foi aceita. Erros de conexao ou certificado sao informados separadamente.

4. Aplique a configuracao:

```powershell
docker compose up -d --force-recreate hermes
```

5. Abra a conversa privada com seu bot, toque em Iniciar e envie o comando e a lista
na MESMA mensagem:

```text
/referencias
HOLANDA, M. A. et al. Elmo-CPAP 1.0: a helmet interface for CPAP and high-flow oxygen delivery. Jornal Brasileiro de Pneumologia, v. 47, n. 3, e20200590, 2021. DOI: https://doi.org/10.1590/S1807-59322021000000001. Acesso em: 22 ago. 2026.
```

O Hermes chama a API e devolve o relatorio na conversa de origem, incluindo avisos.
Ao receber `/referencias` com uma lista, o bot envia uma confirmacao de processamento.
O indicador "digitando" e mantido pelo Hermes enquanto prepara o resultado.
Este Docker usa um unico perfil. `gateway.multiplex_profiles` deve ficar `false`:
o isolamento de varios perfis pode ignorar a autorizacao vinda de `telegram.local.env`.
O aviso de recebimento confirma que o comando chegou ao corretor, nao que a correcao terminou.
O comando `/referencias` nao depende de o modelo decidir chamar uma ferramenta nem
de reescrever a bibliografia. A ferramenta `corrigir_referencias` tambem esta registrada
para uso pelo agente. Os toolsets do painel e do Telegram foram limitados a essa ferramenta;
o terminal interativo do Hermes mantem sua configuracao original.
O esquema da ferramenta e fornecido diretamente ao modelo (Tool Search desativado),
e o parametro de raciocinio foi desativado porque Hermes 3 nao o suporta.
No Telegram e no terminal Hermes, o comando entrega o relatorio diretamente.
No chat do painel web, solicite a correcao em linguagem natural; ali o modelo decide
chamar a ferramenta. Para retorno fiel sem reescrita pela IA, prefira `/referencias`
no Telegram ou a interface do corretor em `http://localhost:8000`.

O Ollama esta configurado para contexto de 64000 tokens, minimo exigido pela versao
instalada do Hermes, com uma requisicao de inferencia por vez e cache KV q8_0.
A execucao sem GPU pode
demorar, especialmente na primeira resposta. O comando direto do Telegram nao
executa inferencia e nao sofre esse custo.

Telegram limita o tamanho de uma mensagem de entrada. Envie listas longas em lotes;
a interface web aceita ate 50 referencias por lote, com 4000 caracteres por referencia.
O comando recebe texto; anexos PDF/DOCX/TXT nao sao interpretados por ele automaticamente.
Mantenha Docker Desktop e o computador ligados para o bot responder.

## Interpretar o resultado

- `verified`: campos avaliados conferidos na fonte consultada, sem pendencias detectadas.
- `needs_review`: proposta de formatacao com dados ausentes, ambiguidades ou campos sem confirmacao.
- `error`: falha de processamento; a entrada e preservada.

`identity_verified` informa se foi encontrada uma obra compativel; nao significa
que todos os campos estao completos. `approved` so fica verdadeiro sem pendencias.
Isso nao e uma garantia de ausencia de erros na fonte ou de cobertura de toda a norma.
`corrections` registra antes/depois; `provenance` registra a fonte por campo.
Copias e downloads incluem os avisos, para nao apresentar rascunhos como resultados finais.

Titulos isolados tambem sao aceitos, com o prefixo opcional `Titulo:`. O sistema
busca Crossref e Open Library, devolve candidatos quando ha ambiguidade e pede o
identificador da obra/edicao correta. Titulo de livro nao determina sua edicao;
o sistema nao escolhe um ano ou uma editora entre edicoes diferentes.

Exemplo de mensagem para o bot:

```text
/referencias
Titulo: ELMO 1.0: a helmet interface for CPAP and high-flow oxygen delivery
Lei federal 11892/2008
Camara dos Deputados. PL 2630/2020
Senado Federal. PL 2338/2023
```

Leis ordinarias e complementares federais sao consultadas no Senado, por tipo,
numero e ano. Projetos usam os dados oficiais da casa indicada. A referencia
ao projeto nao e transformada em referencia a uma lei sancionada. A situacao
de tramitacao aparece como informacao da fonte, com sua data, nao como atestado
de vigencia. Leis estaduais/municipais e leis por apelido ainda requerem revisao.
Na publicacao de leis, o cadastro nem sempre informa secao e paginacao completa
do Diario Oficial; essa limitacao fica explicita no resultado.

Artigos podem ser buscados por DOI ou por titulo, autoria e ano. Livros usam ISBN com
digito verificador e correspondencia no catalogo (incluindo ISBN-10/13 equivalentes).
Se Google Books ou a API de livros da Open Library estiverem indisponiveis, o sistema
tenta o registro de edicao por ISBN da Open Library. Dados incompletos continuam pendentes.
Teses, capitulos, congressos,
outros atos legislativos, patentes e paginas podem ser formatados a partir dos dados fornecidos; quando
nao ha fonte estruturada confirmada, exigem revisao. Links comuns nao sao rastreados
automaticamente. Jurisprudencia, material audiovisual e outros formatos fora dos
modelos implementados sao preservados para revisao manual.

Artigos identificados sao complementados com Europe PMC/PubMed e XML do PMC,
quando disponiveis. O periodo vem do fasciculo, nunca e calculado pelo numero da
edicao nem confundido com o dia de publicacao online. A autoria estruturada pode
corrigir a separacao entre sobrenome e prenome quando os nomes completos coincidem.
O NLM Catalog pode fornecer o local, entre colchetes, apos conferir ISSN e anos
de publicacao; registros com multiplos locais historicos ficam pendentes.

O local agora e normalizado com uma base local do IBGE. Exemplos:
`[Brasilia, DF, Brasil]` vira `[Brasilia, DF]` (com acento na saida);
`Sao Paulo, SP, Brasil` vira `Sao Paulo` (com a grafia oficial);
`Vicosa, Minas Gerais, Brasil` vira `Vicosa, MG` (com a grafia oficial).
Sem UF para uma cidade homonima, o sistema pede revisao. Colchetes sao mantidos
quando o local foi identificado fora do documento. Em cidades estrangeiras,
o pais pode ser necessario para desambiguar e nao e apagado automaticamente.
A fonte bibliografica original permanece no JSON; a consulta geografica nao
comprova que uma obra foi publicada na sede atual de uma editora ou revista.
Cobertura e atualizacao da base: `data/README.md`.

Data de acesso ausente usa o dia da correcao (America/Sao_Paulo) quando ha consulta
online confirmada. O JSON identifica a data como gerada, e o relatorio avisa que
isso nao atesta disponibilidade do link. Datas fornecidas sao preservadas; nao se
gera data em modo offline ou quando a obra nao foi localizada.
Nao se inventam editora, ementa ou ano. A falta desses elementos aparece como
pendencia. As regras de formatacao cobrem um subconjunto da NBR 6023;
o projeto nao certifica conformidade integral de qualquer tipo documental.

## API e testes

```json
{"text": "referencia 1\nreferencia 2", "online": true}
```

Envie por POST a `/api/format`. Com `online: false`, todas as referencias ficam
sem verificacao externa e nenhuma consulta bibliografica e realizada.
Por padrao, uma referencia por linha, ignorando linhas vazias. Para referencias
com quebras internas, envie `input_format: "blocks"` no JSON: cada bloco separado
por uma linha vazia sera interpretado como uma referencia. Esse modo e explicito
para evitar que referencias diferentes sejam unidas por engano.

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -p "test*.py" -v
node test_frontend.cjs
docker compose exec -T --user hermes hermes hermes plugins doctor /opt/data/plugins/brain-format --ci
docker compose ps
```

Para testar a API em execucao com 22 cenarios de artigos, livros, teses, leis,
congressos, capitulos e entradas invalidas:

```powershell
python scripts/verify_references.py
```

O relatorio fica em `artifacts/reference-verification.md` e `.json`. As consultas
online dependem das fontes: uma indisponibilidade aparece como falha de verificacao
e deve ser distinguida de uma referencia aprovada. Os dados sinteticos sao identificados.

Para verificar a autorizacao do Telegram com o proprio Hermes, substitua `SEU_ID`
pelo ID cadastrado. Sem `--send-test`, este comando nao envia mensagens:

```powershell
Get-Content scripts/verify_telegram.py -Raw | docker compose exec -T --user hermes hermes python - --chat-id SEU_ID
```

Acrescente `--send-test` para processar duas referencias de teste e enviar a confirmacao
e o relatorio ao ID autorizado. Esse teste simula a entrada localmente, sem iniciar
outro consumidor de atualizacoes. Para confirmar o recebimento real, envie uma nova
mensagem `/referencias` pelo aplicativo Telegram e confira a resposta.

Se a instalacao Python do Windows tiver erro de certificados, use a API no Docker
ou configure um arquivo de autoridades confiaveis por `REQUESTS_CA_BUNDLE`.
A verificacao TLS nao e desativada automaticamente.

## Documentacao oficial

- Docker e dashboard: https://hermes-agent.nousresearch.com/docs/user-guide/docker
- Telegram: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram
- Plugins e comandos: https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
- Crossref: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- Open Library: https://openlibrary.org/dev/docs/api/books
