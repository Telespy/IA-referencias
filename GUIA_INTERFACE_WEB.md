# Interface Web — Referência Certa

## Como abrir

Na pasta do projeto, dê dois cliques em:

`INICIAR_INTERFACE_WEB.bat`

O servidor Python será iniciado e o navegador abrirá automaticamente em:

`http://127.0.0.1:8000`

Enquanto estiver usando a interface, mantenha a janela do servidor aberta.

## Como usar

1. Cole uma ou várias referências.
2. Escolha o modo de entrada:
   - **Uma por linha**: cada referência inteira ocupa uma linha.
   - **Blocos separados**: para referências que possuem quebras internas; deixe uma linha em branco entre cada referência.
3. Deixe **consultar fontes online** marcado para permitir enriquecimento e verificação.
4. Clique em **Corrigir referências**.
5. Consulte o resumo:
   - **Verificadas**: identidade e campos necessários confirmados.
   - **Em revisão**: faltou evidência ou existe alguma pendência.
   - **Erros**: falha de processamento.
6. Na aba **Revisão detalhada**, compare:
   - entrada original;
   - versão ABNT;
   - versão APA;
   - correções;
   - fontes consultadas;
   - proveniência por campo.
7. Use as abas ABNT/APA para copiar individualmente ou copiar todas.
8. Use os botões de download para gerar arquivos Markdown.

## Atalho

`Ctrl + Enter` executa a correção sem precisar clicar no botão.

## Segurança e confiabilidade

A interface não altera a regra do backend: quando não há evidência suficiente, a referência permanece como **Revisão necessária**. O sistema não deve preencher dados apenas para produzir uma saída aparentemente completa.

## Arquitetura

A interface está em:

- `public/index.html`
- `public/style.css`
- `public/app.js`

O backend é FastAPI:

- `api/index.py`

O processamento usa o mesmo pipeline validado pelo restante do projeto.

## Validação realizada

Após a implementação:

- teste de segurança/renderização do frontend: aprovado;
- suíte Python: **180 testes aprovados + 88 subtestes**;
- teste HTTP real da interface/API: **3 referências enviadas, 3 verificadas, 0 erros**.
