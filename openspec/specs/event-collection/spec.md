# event-collection Specification

## Purpose

Coletar automaticamente os eventos Warning do cluster Kubernetes em intervalos regulares e entregá-los em lote, em um contrato estável, ao pipeline de análise, sem exigir que o operador consulte o cluster manualmente.

## Requirements

### Requirement: Coleta periódica de eventos Warning
O sistema SHALL coletar, a cada intervalo configurado, os eventos do tipo Warning de todos os namespaces do cluster. Eventos de outros tipos MUST ser ignorados.

#### Scenario: Apenas Warning é coletado
- **WHEN** o cluster contém eventos Normal e Warning em vários namespaces
- **THEN** somente os eventos Warning, de todos os namespaces, são incluídos na coleta

#### Scenario: Nenhum Warning no intervalo
- **WHEN** não há eventos Warning elegíveis em um ciclo
- **THEN** nada é despachado ao handler e o sistema aguarda o próximo ciclo

#### Scenario: Volume alto de eventos
- **WHEN** um ciclo encontra muitos eventos Warning elegíveis
- **THEN** todos são coletados e entregues em um único lote, sem limite de quantidade

### Requirement: Intervalo de coleta configurável
O sistema SHALL ler o intervalo de coleta, em minutos, da variável de ambiente `EVENT_COLLECTION_INTERVAL_MINUTES`, com padrão de 3 minutos.

#### Scenario: Valor válido
- **WHEN** `EVENT_COLLECTION_INTERVAL_MINUTES` é um número positivo
- **THEN** o ciclo de coleta usa esse intervalo

#### Scenario: Valor inválido
- **WHEN** a variável é não numérica, negativa ou zero
- **THEN** o sistema usa 3 minutos e registra um warning no log

### Requirement: Coleta imediata no startup
O sistema SHALL executar a primeira coleta imediatamente ao iniciar, sem aplicar marca d'água, considerando todos os eventos Warning ainda existentes no cluster.

#### Scenario: Restart com eventos antigos ainda no cluster
- **WHEN** a aplicação inicia e há eventos Warning mais antigos que o intervalo configurado ainda presentes no cluster
- **THEN** esses eventos são incluídos no primeiro lote, sem aguardar o primeiro intervalo

#### Scenario: Ciclos seguintes usam marca d'água
- **WHEN** a primeira coleta é concluída com sucesso
- **THEN** os ciclos seguintes consideram apenas eventos mais recentes que a marca d'água

### Requirement: Filtro de recência por marca d'água
O sistema SHALL, após a primeira coleta, considerar apenas eventos cuja recência seja posterior à última coleta bem-sucedida. A recência MUST ser determinada pela precedência `series.lastObservedTime`, depois `eventTime`, depois `deprecatedLastTimestamp`.

#### Scenario: Evento recorrente com series
- **WHEN** um evento tem `series.lastObservedTime` posterior à marca d'água e `eventTime` anterior a ela
- **THEN** o evento é coletado, com `series.lastObservedTime` como recência

#### Scenario: Evento de controller legado
- **WHEN** um evento não tem `series` nem `eventTime`, mas tem `deprecatedLastTimestamp`
- **THEN** `deprecatedLastTimestamp` é usado como recência e como `timestamp` de saída

#### Scenario: Evento sem nenhum timestamp
- **WHEN** um evento não tem `series.lastObservedTime`, `eventTime` nem `deprecatedLastTimestamp`
- **THEN** o evento é descartado e um warning é registrado no log

### Requirement: Avanço da marca d'água
O sistema SHALL avançar a marca d'água a cada coleta bem-sucedida, independentemente do resultado do processamento pelo handler.

#### Scenario: Handler falha
- **WHEN** o handler lança erro ao processar um lote
- **THEN** a marca d'água já avançou e o erro não é propagado ao coletor

#### Scenario: Coleta falha
- **WHEN** a listagem de eventos falha em um ciclo
- **THEN** a marca d'água não avança e a mesma janela é reconsultada no próximo ciclo bem-sucedido

### Requirement: Contrato de saída dos eventos
O sistema SHALL entregar cada evento como um dicionário com os campos `uid`, `type`, `reason`, `message`, `namespace`, `involved_object` (`kind`, `name`, `namespace`) e `timestamp` em ISO 8601. O contrato MUST usar nomes próprios, independentes do SDK.

#### Scenario: Mapeamento a partir da API de eventos
- **WHEN** um evento é transformado
- **THEN** `message` vem de `note` e `involved_object` vem de `regarding`

#### Scenario: Recurso cluster-scoped
- **WHEN** o evento refere-se a um recurso sem namespace, como um Node
- **THEN** `involved_object.namespace` é uma string vazia

### Requirement: Despacho assíncrono ao handler
O sistema SHALL despachar cada lote de eventos ao handler de forma fire-and-forget, sem aguardar sua conclusão. O handler MUST capturar suas próprias exceções.

#### Scenario: Ciclo não bloqueia no handler
- **WHEN** o handler demora mais que o intervalo de coleta
- **THEN** o coletor segue para o próximo ciclo sem aguardá-lo

#### Scenario: Handler placeholder
- **WHEN** um lote é despachado e nenhuma análise real está implementada
- **THEN** o handler imprime os eventos recebidos no stdout

#### Scenario: Shutdown da aplicação
- **WHEN** a aplicação é encerrada com despachos em andamento
- **THEN** as tarefas pendentes são canceladas e o loop de coleta é encerrado

### Requirement: Resiliência a falhas do cluster
O sistema SHALL registrar falhas de coleta no log e continuar o loop, sem interrompê-lo.

#### Scenario: Cluster inacessível
- **WHEN** o cluster não responde durante a coleta
- **THEN** o erro é registrado e a coleta é tentada novamente no próximo ciclo

#### Scenario: Permissão RBAC insuficiente
- **WHEN** a listagem de eventos retorna erro de autorização
- **THEN** o log indica a permissão necessária e o loop continua

### Requirement: Autenticação com o cluster
O sistema SHALL autenticar usando a configuração in-cluster quando disponível e, caso contrário, o kubeconfig local.

#### Scenario: Execução dentro do cluster
- **WHEN** a aplicação roda em um pod com service account
- **THEN** a configuração in-cluster é utilizada

#### Scenario: Execução local
- **WHEN** a configuração in-cluster não está disponível
- **THEN** o kubeconfig local é utilizado
