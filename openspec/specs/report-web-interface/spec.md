# report-web-interface Specification

## Purpose

Permitir que o operador consulte pelo navegador os relatórios de análise de causa raiz e acione a correção de um relatório elegível, sem acessar o banco de dados.

## Requirements

### Requirement: Listagem de relatórios
O sistema SHALL oferecer a página `/reports` com todos os relatórios, do mais recente para o mais antigo por data de criação, exibindo ID, data de criação, status e severidade de cada um.

#### Scenario: Relatórios existentes
- **WHEN** o usuário acessa `/reports` e há relatórios no banco
- **THEN** todos são listados ordenados por data de criação decrescente, cada um com ID, data, status e severidade

#### Scenario: Severidade do problema
- **WHEN** o Markdown do relatório contém `**Severidade:** ALTO`
- **THEN** a listagem exibe a severidade ALTO

#### Scenario: Relatório sem severidade identificável
- **WHEN** o Markdown não contém o campo de severidade (por exemplo, um lote `INCOMPLETO`)
- **THEN** a listagem exibe um indicador de severidade ausente, sem erro

#### Scenario: Item clicável
- **WHEN** o usuário clica em um item da lista
- **THEN** é levado à página de detalhe daquele relatório

#### Scenario: Nenhum relatório
- **WHEN** não há relatórios no banco
- **THEN** a página exibe a mensagem "Nenhum relatório encontrado"

### Requirement: Badge de status
O sistema SHALL exibir o status de cada relatório como um badge com estilo próprio por status.

#### Scenario: Mapeamento de estilos
- **WHEN** um relatório é exibido na listagem ou no detalhe
- **THEN** `EM_ANALISE`, `COMPLETO`, `INCOMPLETO`, `CORRIGINDO`, `CORRIGIDO` e `FALHA_CORRECAO` usam respectivamente os estilos `badge-processing`, `badge-complete`, `badge-incomplete`, `badge-executing`, `badge-executed` e `badge-execution-failed`

### Requirement: Detalhe do relatório
O sistema SHALL oferecer a página `/reports/{id}`, onde `id` é um UUID, exibindo o status e o conteúdo Markdown completo do relatório renderizado em HTML.

#### Scenario: Relatório existente
- **WHEN** o usuário acessa o detalhe de um relatório existente
- **THEN** a página exibe o status e o Markdown renderizado (títulos, listas, tabelas e blocos de código)

#### Scenario: Markdown malformado
- **WHEN** o Markdown do relatório está malformado
- **THEN** a página é exibida com o HTML parcial resultante, sem erro

#### Scenario: Relatório inexistente
- **WHEN** o usuário acessa o detalhe de um UUID que não existe
- **THEN** a resposta é 404 com uma mensagem informativa

#### Scenario: ID que não é UUID
- **WHEN** o usuário acessa `/reports/abc`
- **THEN** a requisição é rejeitada como inválida, sem consultar o banco

### Requirement: Conteúdo renderizado é seguro
O sistema MUST sanitizar o HTML gerado a partir do Markdown, removendo scripts, manipuladores de eventos e URLs executáveis, pois o conteúdo deriva de texto do cluster processado por um LLM.

#### Scenario: Markdown com HTML ativo
- **WHEN** o Markdown contém `<script>`, `onerror=` ou um link `javascript:`
- **THEN** o HTML exibido não contém esses elementos nem atributos

#### Scenario: Formatação legítima preservada
- **WHEN** o Markdown contém tabelas, listas, código e links `https`
- **THEN** a formatação é preservada

### Requirement: Botão de correção condicional ao status
O sistema SHALL exibir no detalhe o botão "Executar correção", que envia `POST /reports/{id}/fix`, somente quando o status for `COMPLETO` ou `FALHA_CORRECAO`.

#### Scenario: Relatório COMPLETO
- **WHEN** o detalhe de um relatório `COMPLETO` é exibido
- **THEN** o botão "Executar correção" é exibido

#### Scenario: Nova tentativa após falha
- **WHEN** o detalhe de um relatório `FALHA_CORRECAO` é exibido
- **THEN** o botão "Executar correção" é exibido

#### Scenario: Outros status
- **WHEN** o status é `EM_ANALISE`, `INCOMPLETO`, `CORRIGINDO` ou `CORRIGIDO`
- **THEN** o botão não é exibido

### Requirement: Correção já em andamento
O sistema SHALL, quando a solicitação de correção for rejeitada por conflito de estado, reexibir o detalhe do relatório com a mensagem "Correção já em andamento".

#### Scenario: Conflito na solicitação
- **WHEN** a rota de correção responde com conflito (409) para um relatório
- **THEN** o usuário vê o detalhe do relatório com a mensagem "Correção já em andamento"

### Requirement: Banco indisponível
O sistema SHALL responder 503 com a mensagem "Banco de dados indisponível, tente novamente em instantes" quando o banco falhar ao atender a listagem ou o detalhe.

#### Scenario: Erro de conexão na listagem
- **WHEN** a consulta da listagem falha por erro do banco
- **THEN** a página de erro é exibida com status 503 e a mensagem informada

#### Scenario: Erro de conexão no detalhe
- **WHEN** a consulta do detalhe falha por erro do banco
- **THEN** a página de erro é exibida com status 503 e a mensagem informada

### Requirement: Navegação para a listagem
O sistema SHALL exibir o link "Relatórios" no cabeçalho comum a todas as páginas.

#### Scenario: Link no cabeçalho
- **WHEN** qualquer página é exibida
- **THEN** o cabeçalho contém o link "Relatórios" apontando para `/reports`
