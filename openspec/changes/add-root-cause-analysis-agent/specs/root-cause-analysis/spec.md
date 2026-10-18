# Spec Delta

## Purpose

Investigar automaticamente a causa raiz dos eventos Warning coletados, evitando reanálise de eventos já em tratamento e sem permitir que o agente altere o cluster.

## ADDED Requirements

### Requirement: Deduplicação de eventos já em tratamento
O sistema SHALL ignorar eventos cujo `uid` esteja em qualquer relatório com status `EM_ANALISE`, `COMPLETO`, `CORRIGINDO` ou `FALHA_CORRECAO`, avaliando a existência de relatório ativo e nunca o status do relatório mais recente.

#### Scenario: Evento novo
- **WHEN** o lote contém um uid que não consta em nenhum relatório
- **THEN** o evento é analisado

#### Scenario: Evento em tratamento
- **WHEN** o uid consta em um relatório ativo
- **THEN** o evento é ignorado

#### Scenario: Relatório antigo e relatório ativo com o mesmo uid
- **WHEN** o uid consta em um relatório `CORRIGIDO` e também em um relatório `EM_ANALISE`
- **THEN** o evento é ignorado

#### Scenario: Lote parcialmente em tratamento
- **WHEN** parte dos uids do lote já está em tratamento
- **THEN** apenas os eventos novos são analisados

#### Scenario: Todos os eventos já em tratamento
- **WHEN** todos os uids do lote estão em relatórios ativos
- **THEN** nenhuma análise é disparada

### Requirement: Reanálise de reincidência e de análise incompleta
O sistema SHALL reanalisar eventos cujo uid conste somente em relatórios `CORRIGIDO` ou `INCOMPLETO`.

#### Scenario: Reincidência após correção
- **WHEN** um evento reaparece e seu uid só consta em relatório `CORRIGIDO`
- **THEN** o evento é reanalisado e gera novo relatório

#### Scenario: Recorrência após análise incompleta
- **WHEN** um evento reaparece e seu uid só consta em relatório `INCOMPLETO`
- **THEN** o evento é reanalisado

### Requirement: Relatório criado antes da investigação
O sistema SHALL registrar o relatório do lote com status `EM_ANALISE` antes de iniciar a investigação, de modo que lotes concorrentes vejam os eventos como em tratamento.

#### Scenario: Ciclo seguinte durante a análise
- **WHEN** a análise de um lote ainda está em andamento e um novo lote traz os mesmos uids
- **THEN** esses eventos são ignorados pela deduplicação

### Requirement: Investigação por agente com tools somente de leitura
O sistema SHALL investigar a causa raiz com um agente de IA que inspeciona o cluster exclusivamente pelas operações de leitura `kubectl_get`, `kubectl_describe` e `kubectl_logs`. Nenhuma operação de escrita MUST estar disponível ao agente.

#### Scenario: Tools disponíveis ao agente
- **WHEN** o agente é criado
- **THEN** sua lista de tools contém exatamente `kubectl_get`, `kubectl_describe` e `kubectl_logs`

#### Scenario: Tool de escrita exposta pelo servidor
- **WHEN** o servidor MCP expõe tools como `kubectl_apply`, `kubectl_patch` ou `kubectl_delete`
- **THEN** essas tools não são disponibilizadas ao agente

### Requirement: Modelo e limite de iterações configuráveis
O sistema SHALL ler o modelo de `AGENT_MODEL_NAME` (padrão `claude-haiku-4-5`) e o limite de iterações de `AGENT_MAX_ITERATIONS` (padrão 25).

#### Scenario: Limite válido
- **WHEN** `AGENT_MAX_ITERATIONS` é um inteiro positivo
- **THEN** o agente encerra a investigação ao atingir esse número de chamadas ao modelo

#### Scenario: Limite inválido
- **WHEN** `AGENT_MAX_ITERATIONS` é não numérico, zero ou negativo
- **THEN** o sistema usa 25 e registra um warning no log

#### Scenario: Limite atingido sem causa raiz
- **WHEN** o agente atinge o limite sem produzir problemas identificáveis
- **THEN** o relatório do lote termina `INCOMPLETO`

### Requirement: Falhas da análise não afetam o coletor
O sistema SHALL tratar qualquer falha da análise (MCP indisponível, erro da API do Claude após as tentativas, banco indisponível) registrando o erro no log, sem propagá-lo ao coletor.

#### Scenario: MCP Server indisponível
- **WHEN** a conexão com o MCP Server falha
- **THEN** a análise é abortada, o relatório do lote vira `INCOMPLETO` e o erro é registrado

#### Scenario: Erro da API do Claude
- **WHEN** a API do Claude falha mesmo após 3 novas tentativas com backoff
- **THEN** a análise é abortada e o relatório do lote vira `INCOMPLETO`

#### Scenario: Banco indisponível na deduplicação
- **WHEN** a consulta de deduplicação falha
- **THEN** o lote é descartado, o erro é registrado e o coletor não é afetado

#### Scenario: Evento já corrigido entre coleta e análise
- **WHEN** o agente encontra o recurso em estado saudável
- **THEN** o relatório registra o estado saudável
