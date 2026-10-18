# Spec Delta

## Purpose

Persistir o diagnóstico de cada problema identificado como relatório estruturado, com ciclo de vida de status e recuperação de análises estagnadas ou interrompidas.

## ADDED Requirements

### Requirement: Estrutura do relatório
O sistema SHALL gerar a análise em Markdown com resumo de contagem por severidade e, para cada problema, severidade (`CRITICO`, `ALTO`, `MEDIO` ou `BAIXO`), namespace, recursos afetados, eventos, causa raiz, evidências, solução recomendada e comando sugerido.

#### Scenario: Resposta no formato esperado
- **WHEN** o agente responde com um resumo e dois blocos `## Problema N`
- **THEN** a resposta é reconhecida com dois problemas, cada um com seus campos

#### Scenario: Resposta sem problemas identificáveis
- **WHEN** a resposta é vazia ou não contém blocos de problema
- **THEN** a análise é considerada inconclusiva

### Requirement: Um relatório por problema
O sistema SHALL persistir cada problema como um relatório próprio, com ID único e os `event_uids` listados no campo **Eventos** daquele problema.

#### Scenario: Lote com dois problemas independentes
- **WHEN** o agente identifica dois problemas com uids distintos
- **THEN** dois relatórios `COMPLETO` são criados, cada um com seus uids

#### Scenario: Evento não referenciado
- **WHEN** um uid do lote não aparece no campo **Eventos** de nenhum problema
- **THEN** um warning é registrado e o evento fica sem relatório próprio

### Requirement: Campos do relatório persistido
O sistema SHALL armazenar para cada relatório: `id` (UUID), conteúdo Markdown, status, `event_uids` (lista de texto) e os timestamps `created_at` e `updated_at`, com consulta eficiente por uid.

#### Scenario: Persistência completa
- **WHEN** um relatório é criado
- **THEN** ele possui ID único, Markdown, status, uids e timestamps de criação e atualização

### Requirement: Ciclo de vida do status
O sistema SHALL restringir o status a `EM_ANALISE`, `COMPLETO`, `INCOMPLETO`, `CORRIGINDO`, `CORRIGIDO` e `FALHA_CORRECAO`. A análise MUST levar `EM_ANALISE` a `COMPLETO` (análise concluída) ou `INCOMPLETO` (inconclusiva ou abortada).

#### Scenario: Análise concluída
- **WHEN** o agente identifica ao menos um problema
- **THEN** o relatório do lote é substituído pelos relatórios por problema com status `COMPLETO`

#### Scenario: Análise inconclusiva ou abortada
- **WHEN** a análise é abortada ou não identifica problemas
- **THEN** o relatório do lote permanece e passa a `INCOMPLETO`, com os uids do lote

### Requirement: Substituição condicional ao status
O sistema SHALL substituir o relatório `EM_ANALISE` do lote pelos relatórios por problema na mesma transação, somente se ele ainda estiver `EM_ANALISE`.

#### Scenario: Relatório ainda em análise
- **WHEN** a análise termina e o relatório do lote está `EM_ANALISE`
- **THEN** ele é removido e os relatórios por problema são criados na mesma transação

#### Scenario: Relatório já tornado INCOMPLETO
- **WHEN** a análise termina mas o relatório do lote já foi marcado `INCOMPLETO` (estagnação ou startup)
- **THEN** o resultado do agente é descartado e nenhum relatório é criado

### Requirement: Recuperação de análises estagnadas
O sistema SHALL marcar como `INCOMPLETO` os relatórios `EM_ANALISE` há mais de `ANALYSIS_STALE_TIMEOUT_MINUTES` minutos (padrão 30), durante a consulta de deduplicação.

#### Scenario: Relatório estagnado
- **WHEN** a deduplicação encontra um relatório `EM_ANALISE` mais antigo que o timeout
- **THEN** ele passa a `INCOMPLETO` e seus eventos podem ser reanalisados

### Requirement: Recuperação no startup
O sistema SHALL marcar como `INCOMPLETO` todos os relatórios `EM_ANALISE` encontrados ao iniciar a aplicação.

#### Scenario: Restart durante análise
- **WHEN** a aplicação inicia com um relatório `EM_ANALISE` órfão
- **THEN** ele passa a `INCOMPLETO`, liberando seus eventos para reanálise

### Requirement: Falha ao persistir o relatório
O sistema SHALL tentar novamente a persistência com backoff e, esgotadas as tentativas, registrar o erro com o conteúdo Markdown gerado, sem fallback em arquivo e sem propagar o erro ao coletor.

#### Scenario: Banco indisponível na persistência
- **WHEN** a gravação dos relatórios falha após as tentativas
- **THEN** o log traz o erro e o Markdown gerado, e o relatório `EM_ANALISE` fica para a recuperação por estagnação ou startup
