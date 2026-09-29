# Autoridade geografica local

`brazilian_places.json` e um recorte gerado da API de Localidades do IBGE.
Contem identificador, nome e UF dos municipios, nomes das UFs, URLs da fonte e
data de consulta. O arquivo acompanha o Docker e funciona sem rede em cada
correcao. Nao contem uma tabela de sedes de editoras ou revistas.

Para atualizar, na raiz do projeto, em PowerShell 7:

```powershell
./scripts/update_place_authority.ps1
docker compose up -d --build brain-format
```

O importador valida a resposta antes de substituir o arquivo. A API carrega a
base uma vez por processo; reinicie-a apos uma atualizacao fora do Docker.

## Politica de local

- O local vem da obra, da edicao ou de um catalogo vinculado ao documento.
  Conhecer o nome de uma editora nao autoriza atribuir sua sede atual a toda obra.
- Para uma cidade brasileira identificada, remove-se o pais redundante. A UF
  fica quando necessaria para distinguir homonimos; nomes completos de estados
  sao convertidos para a sigla. Colchetes de local identificado externamente
  sao preservados.
- A base detecta homonimos entre municipios brasileiros atuais. Exemplos
  bibliograficos de homonimia historica/internacional complementam a regra
  para Brasilia, Barcelona, Coimbra, Matozinhos e Nazare. Isso nao afirma que
  todas essas homonimias sejam municipios brasileiros atuais.
- Sem UF para um nome ambiguo, nao se escolhe a cidade mais conhecida.
  Nomes historicos, qualificadores contraditorios e multiplos locais pedem revisao.
- Localidades estrangeiras conservam os qualificadores da fonte: o pais pode
  ser necessario, como em Cambridge, United Kingdom ou Toledo, Espanha.
  A base brasileira nao prova ausencia de homonimos no mundo inteiro.
- A normalizacao e registrada separadamente da comprovacao bibliografica,
  em `provenance.city.normalization` (ou `event_city`). O valor original e a
  fonte da obra permanecem auditaveis. Normalizar nao torna uma entrada offline
  verificada.

Fontes das regras: [MORE/UFSC](https://more.ufsc.br/suporte/ajuda),
[Guia de normalizacao UEMG](https://www.mestrados.uemg.br/images/livros-pdf/catalogo-2024/Normalizacao/normalizacao.pdf).
Fonte geografica: [API de Localidades do IBGE](https://servicodados.ibge.gov.br/api/docs/localidades).
