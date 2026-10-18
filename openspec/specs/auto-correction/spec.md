# auto-correction Specification

## Purpose

Executar automaticamente, a partir de um relatório de análise, os passos de correção no cluster e verificar se o problema foi resolvido, registrando o resultado no relatório.

## Requirements

### Requirement: Acionamento da correção
O sistema SHALL oferecer `POST /reports/{id}/fix`, que aceita relatórios `COMPLETO` ou `FALHA_CORRECAO`, move o relatório para `CORRIGINDO` antes de responder e redireciona (303) para o detalhe do relatório, executando a correção em segundo plano.

#### Scenario: Relatório COMPLETO
- **WHEN** `POST /reports/{id}/fix` é enviado para um relatório `COMPLETO`
- **THEN** o relatório passa a `CORRIGINDO`, a resposta é 303 para `/reports/{id}` e a correção inicia em segundo plano

#### Scenario: Nova tentativa após falha
- **WHEN** o relatório está `FALHA_CORRECAO`
- **THEN** o relatório passa a `CORRIGINDO` e a correção é reiniciada

#### Scenario: Relatório inexistente
- **WHEN** o `id` não corresponde a nenhum relatório
- **THEN** a resposta é 404

### Requirement: Rejeição por estado inválido
O sistema SHALL responder 409 quando o relatório não estiver `COMPLETO` ou `FALHA_CORRECAO`, reexibindo o detalhe com uma mensagem, sem iniciar correção.

#### Scenario: Correção já em andamento
- **WHEN** o relatório está `CORRIGINDO`
- **THEN** a resposta é 409 com o detalhe e a mensagem "Correção já em andamento"

#### Scenario: Outros status
- **WHEN** o relatório está `EM_ANALISE`, `INCOMPLETO` ou `CORRIGIDO`
- **THEN** a resposta é 409 com uma mensagem informando que o relatório não permite correção, e nenhuma correção inicia

### Requirement: Transição atômica contra concorrência
O sistema SHALL garantir que, para requisições simultâneas sobre o mesmo relatório, apenas uma inicie a correção.

#### Scenario: Duas requisições simultâneas
- **WHEN** duas requisições `POST /reports/{id}/fix` chegam ao mesmo tempo para um relatório `COMPLETO`
- **THEN** uma recebe 303 e dispara um único agente, e a outra recebe 409

### Requirement: Execução da correção pelo agente
O sistema SHALL executar a correção com um agente que recebe o Markdown completo do relatório, interpreta a solução e o comando sugeridos e os executa no cluster por todas as operações disponíveis no MCP Server Kubernetes.

#### Scenario: Agente com acesso completo
- **WHEN** o agente de correção é criado
- **THEN** todas as tools do MCP Server, incluindo as de escrita, estão disponíveis a ele

#### Scenario: Recurso que não existe mais
- **WHEN** um passo referencia um recurso inexistente
- **THEN** o agente registra que o recurso não foi encontrado e segue para os próximos passos

#### Scenario: Correção que introduz novo erro
- **WHEN** a validação mostra que a própria correção deixou o recurso pior
- **THEN** o agente continua corrigindo até o recurso ficar saudável ou o limite de iterações ser atingido

### Requirement: Configuração do agente de correção
O sistema SHALL ler o modelo de `AGENT_MODEL_NAME` (padrão `claude-haiku-4-5`) e o limite de iterações de `CORRECTION_MAX_ITERATIONS` (padrão 25).

#### Scenario: Limite inválido
- **WHEN** `CORRECTION_MAX_ITERATIONS` é não numérico, zero ou negativo
- **THEN** o sistema usa 25 e registra um warning no log

#### Scenario: Limite atingido
- **WHEN** o agente atinge o limite de iterações sem emitir veredito
- **THEN** o relatório termina `FALHA_CORRECAO`

### Requirement: Verificação pós-correção
O sistema SHALL considerar a correção bem-sucedida somente se o agente comprovar que o recurso afetado está saudável (pod Running e Ready, Deployment Available, sem novos erros); caso contrário o resultado MUST ser falha.

#### Scenario: Recurso saudável
- **WHEN** o agente verifica o recurso e o encontra saudável
- **THEN** a resposta traz o veredito `CORRIGIDO:` e o relatório passa a `CORRIGIDO`

#### Scenario: Problema persiste
- **WHEN** o recurso continua quebrado após as tentativas
- **THEN** a resposta traz o veredito `FALHA:` e o relatório passa a `FALHA_CORRECAO`

#### Scenario: Estado ambíguo
- **WHEN** parte dos problemas foi corrigida e parte falhou
- **THEN** o veredito é `FALHA:` e o corpo da resposta detalha o que foi corrigido e o que falhou

### Requirement: Classificação do resultado pelo veredito
O sistema SHALL determinar o status final pelo veredito `CORRIGIDO:` ou `FALHA:` ancorado no início de uma linha da resposta (tolerando marcadores Markdown como `-`, `*`, `#` e `>`), em qualquer posição da resposta. Sem veredito, o resultado MUST ser `FALHA_CORRECAO` com warning no log.

#### Scenario: Veredito após texto em prosa
- **WHEN** a resposta traz um parágrafo e depois a linha `CORRIGIDO: deployment saudável`
- **THEN** o status final é `CORRIGIDO`

#### Scenario: Menção no meio de frase
- **WHEN** a palavra `CORRIGIDO:` aparece no meio de uma frase e não há veredito no início de linha
- **THEN** o resultado é `FALHA_CORRECAO`

#### Scenario: Sem veredito
- **WHEN** a resposta não contém veredito
- **THEN** o status final é `FALHA_CORRECAO` e um warning é registrado

### Requirement: Registro e exibição do resultado
O sistema SHALL persistir a resposta do agente no relatório e exibi-la no detalhe, em uma seção "Resultado da Correção", junto do status atualizado.

#### Scenario: Correção concluída
- **WHEN** a correção termina com qualquer veredito
- **THEN** o detalhe do relatório exibe o novo status e a seção "Resultado da Correção" com a resposta do agente

#### Scenario: Correção ainda não executada
- **WHEN** o relatório nunca foi corrigido
- **THEN** a seção "Resultado da Correção" não é exibida

### Requirement: Falhas de infraestrutura na correção
O sistema SHALL, quando o MCP Server estiver indisponível ou a API do Claude falhar após as tentativas, abortar a correção, registrar o erro e levar o relatório a `FALHA_CORRECAO`.

#### Scenario: MCP Server indisponível
- **WHEN** a conexão com o MCP Server falha durante a correção
- **THEN** o relatório passa a `FALHA_CORRECAO` e o erro é registrado no log

#### Scenario: Erro da API do Claude
- **WHEN** a API do Claude falha mesmo após 3 novas tentativas com backoff
- **THEN** o relatório passa a `FALHA_CORRECAO`

### Requirement: Recuperação de correções interrompidas
O sistema SHALL marcar como `FALHA_CORRECAO` os relatórios `CORRIGINDO` encontrados ao iniciar a aplicação, permitindo nova tentativa pelo botão.

#### Scenario: Restart durante a correção
- **WHEN** a aplicação inicia com um relatório `CORRIGINDO` órfão
- **THEN** ele passa a `FALHA_CORRECAO` e volta a aceitar `POST /reports/{id}/fix`
