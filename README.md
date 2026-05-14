# Entrega 5 - Sistema de Mensagens Distribuído

## 1. Introdução do Projeto
Este projeto implementa um sistema distribuído de mensagens instantâneas inspirado em serviços como BBS e IRC, utilizando ZeroMQ para comunicação entre os componentes e Protocol Buffers para serialização binária das mensagens.

Na **Parte 1**, o sistema foi desenvolvido para permitir que bots clientes realizassem:
- login no serviço;
- listagem de canais disponíveis;
- criação de novos canais.

Na **Parte 2**, o projeto foi expandido para incluir:
- inscrição em canais;
- publicação de mensagens em canais;
- recebimento de mensagens por meio do padrão Publisher-Subscriber;
- persistência das publicações realizadas pelos usuários.

Na **Parte 3**, o sistema foi evoluído para incluir:
- relógio lógico em clientes e servidores;
- relógio lógico nas mensagens trocadas;
- um serviço de referência para rank e lista de servidores;
- heartbeat para monitoramento da disponibilidade dos servidores;
- sincronização do relógio físico dos servidores por meio de offset em nível de aplicação.

Na **Parte 4**, a sincronização do relógio foi modificada para usar um **servidor coordenador**, escolhido por eleição, permitindo que os demais servidores atualizem seus relógios a partir dele.

Na **Parte 5**, foi implementada a **replicação dos dados persistidos**, garantindo que todos os servidores mantenham cópia completa do histórico de logins, canais e publicações.

O projeto foi desenvolvido com:
- **clientes em Java**;
- **servidores em Python**;
- **Docker Compose** para orquestração dos containers.

---

## 2. Escolhas de Arquitetura e Justificativas

### 2.1. Linguagens
Foi utilizada a seguinte divisão:
- **Java** para os clientes;
- **Python** para os servidores;
- **Python** também para o broker Req/Rep, para o proxy Pub/Sub e para o serviço de referência.

Essa escolha atende ao requisito do trabalho de utilizar linguagens diferentes no projeto.

### 2.2. Serialização
Foi escolhido o **Protocol Buffers** como formato de serialização binária. Essa escolha foi feita porque ele:
- atende à exigência de não utilizar JSON, XML ou texto simples na comunicação;
- funciona bem entre Java e Python;
- permite definir com clareza a estrutura das mensagens trocadas.

Todas as mensagens enviadas no sistema possuem:
- **timestamp**;
- **logical_clock**.

### 2.3. Broker Req/Rep
Para as operações de controle da aplicação, foi adotado um **broker ZeroMQ no padrão ROUTER-DEALER**.

Esse broker é responsável por intermediar a comunicação entre clientes e servidores em operações como:
- login;
- listagem de canais;
- criação de canais;
- solicitação de publicação de mensagens.

Nesse fluxo:
- os clientes enviam requisições ao broker;
- o broker encaminha essas requisições aos servidores;
- os servidores processam as operações e retornam as respostas.

### 2.4. Proxy Pub/Sub
Na Parte 2, foi adicionado um **proxy Pub/Sub separado do broker Req/Rep**, conforme pedido no enunciado.

Esse proxy é responsável por intermediar:
- as publicações feitas pelos servidores;
- o recebimento dessas publicações pelos clientes inscritos nos canais.

Foram utilizadas:
- **porta 5557 como XSUB**;
- **porta 5558 como XPUB**.

### 2.5. Serviço de Referência
Na Parte 3, foi adicionado um **serviço de referência** separado do broker e do proxy.

Esse serviço se comunica apenas com os servidores e é responsável por:
- informar o rank do servidor;
- manter o cadastro de servidores;
- fornecer a lista de servidores disponíveis;
- receber mensagens de heartbeat;
- remover servidores indisponíveis da lista.

A partir da Parte 4, esse serviço deixou de ser usado para sincronização da hora, permanecendo apenas com as responsabilidades de rank, heartbeat e controle de disponibilidade.

### 2.6. Persistência
Cada servidor mantém seu próprio arquivo local `state.json`, associado a um volume separado do Docker.

Nesse arquivo são armazenados:
- histórico de logins;
- canais existentes;
- publicações realizadas.

Dessa forma:
- os dados sobrevivem à reinicialização dos containers;
- não há compartilhamento direto de arquivo entre os servidores;
- cada nó mantém sua própria persistência local.

### 2.7. Consistência dos canais
Os canais criados precisam ficar disponíveis para todos os usuários do sistema. Para isso, os servidores mantêm uma sincronização interna dos eventos de criação de canal.

Quando um servidor cria um canal novo:
- ele grava o canal localmente;
- replica esse evento aos demais servidores;
- os outros servidores atualizam seus próprios arquivos locais.

Com isso, os servidores mantêm seus arquivos separados, mas continuam com uma visão consistente dos canais existentes.

### 2.8. Biblioteca Python
Na implementação em Python foi utilizada a biblioteca **pyzmq**, que é a forma correta de uso do ZeroMQ nesse ambiente.

### 2.9. Método de Replicação e Consistência
Na Parte 5, foi implementado um mecanismo de replicação para garantir que todos os servidores mantenham cópia dos dados persistidos pelo sistema.

O método escolhido foi uma **replicação ativa com propagação imediata de atualizações**, complementada por uma **sincronização completa de estado no momento em que um servidor entra no sistema**.

#### Como o método resolve o problema do projeto
O broker da aplicação distribui as requisições entre os servidores em round-robin. Por isso, sem replicação, cada servidor acabaria armazenando apenas parte do histórico de logins, canais e publicações. Se um servidor fosse interrompido, essa parcela do histórico seria perdida. Além disso, qualquer consulta feita a um único servidor retornaria apenas os dados locais daquele nó.

Com a replicação implementada, toda alteração persistente feita em um servidor também é enviada aos demais, garantindo que todos mantenham o mesmo conjunto de dados.

#### Como foi implementado
A implementação foi dividida em duas partes:

1. **Replicação imediata dos eventos**
   - sempre que um servidor registra um login, cria um canal ou persiste uma publicação, ele:
     - salva localmente;
     - gera um evento interno de replicação;
     - publica esse evento no tópico interno `__INTERNAL__`;
     - os demais servidores recebem esse evento e aplicam a mesma alteração em seus próprios arquivos `state.json`.

2. **Sincronização de estado no startup**
   - quando um servidor inicia, ele solicita a outro servidor ativo uma cópia completa do estado atual;
   - ao receber esse estado, faz o merge dos canais, logins e publicações que ainda não possuía;
   - isso permite recuperar atualizações perdidas caso o servidor tenha ficado indisponível temporariamente.

#### Controle de duplicidade
Para evitar que o mesmo evento seja aplicado mais de uma vez, cada alteração replicada recebe um `event_id`. Os servidores mantêm uma lista de identificadores já processados, o que torna a aplicação dos eventos idempotente.

#### Adaptação do método ao projeto
Na teoria, mecanismos de replicação frequentemente usam confirmações explícitas entre réplicas. Neste projeto, a solução foi adaptada para a arquitetura já existente, aproveitando o canal interno Pub/Sub entre servidores para propagar as alterações de forma simples e compatível com o restante da aplicação.

Como complemento, foi adicionada a sincronização completa de estado no startup para reduzir o risco de inconsistência caso algum servidor reinicie depois de perder eventos anteriores.

---

## 3. Funcionalidades Implementadas

### 3.1. Login de usuário
Assim que inicia, o bot realiza login no sistema informando apenas o nome do usuário.

O servidor valida a requisição e responde com sucesso ou erro.

Cada login bem-sucedido é persistido com:
- nome do usuário;
- timestamp;
- identificação do servidor responsável.

A partir da Parte 5, os logins também passam a ser replicados para os demais servidores.

### 3.2. Listagem de canais
O cliente pode solicitar ao servidor a lista de canais disponíveis.

O servidor responde com os nomes de todos os canais conhecidos naquele momento.

### 3.3. Criação de canais
Se necessário, o cliente pode solicitar a criação de um novo canal.

O servidor valida o nome do canal, registra o canal localmente e propaga a criação aos outros servidores.

### 3.4. Inscrição em canais
Na Parte 2, os clientes passaram a se inscrever em canais por meio de uma conexão `SUB`.

Cada bot mantém uma lista local dos canais aos quais já está inscrito. Quando possui menos de 3 inscrições, ele escolhe aleatoriamente um canal ainda não assinado e faz a inscrição nesse tópico.

A partir desse momento, todas as mensagens publicadas naquele canal passam a ser recebidas pelo cliente.

### 3.5. Publicação em canais
Para publicar uma mensagem, o cliente não envia diretamente ao tópico. Em vez disso, ele faz uma requisição ao servidor contendo:
- canal;
- texto da mensagem;
- remetente;
- timestamp;
- logical_clock.

O servidor:
1. valida a publicação;
2. verifica se o canal existe;
3. grava a publicação em disco;
4. publica a mensagem no tópico correspondente;
5. responde ao cliente com status de sucesso ou erro.

Na Parte 5, as publicações persistidas também passam a ser replicadas aos demais servidores.

### 3.6. Recebimento de mensagens
Os clientes inscritos recebem as mensagens publicadas nos canais aos quais assinaram.

No terminal, o cliente exibe:
- nome do canal;
- remetente;
- texto da mensagem;
- timestamp de envio;
- timestamp de recebimento;
- relógio lógico associado à mensagem.

### 3.7. Relógio lógico
Na Parte 3, foi implementado um relógio lógico em clientes, servidores e no serviço de referência.

Cada processo mantém um contador lógico próprio. O funcionamento segue a regra definida no enunciado:
- antes de enviar uma mensagem, o processo incrementa seu contador e envia esse valor junto com a mensagem;
- ao receber uma mensagem, o processo compara seu contador local com o valor recebido e atualiza o contador com o máximo entre os dois.

Com isso, todas as mensagens trocadas pelo sistema carregam, além do timestamp, o valor do relógio lógico do emissor.

### 3.8. Rank e lista de servidores
Ao iniciar, cada servidor se comunica com o serviço de referência para:
- informar seu nome;
- receber seu rank;
- registrar-se no cadastro global do sistema.

Além disso, os servidores podem solicitar ao serviço de referência a lista de servidores disponíveis, contendo nome e rank de cada nó ativo.

### 3.9. Heartbeat
Cada servidor envia mensagens periódicas de heartbeat ao serviço de referência.

No projeto, o heartbeat é enviado periodicamente com base no número de mensagens tratadas pelo servidor. Ao receber o heartbeat, o serviço de referência:
- confirma que o servidor continua ativo;
- atualiza o último instante em que aquele servidor foi visto;
- mantém a lista de servidores disponíveis atualizada.

Caso um servidor deixe de enviar heartbeat dentro do intervalo configurado, ele é removido da lista de servidores disponíveis.

### 3.10. Sincronização do relógio físico
Na Parte 4, a sincronização do relógio físico deixou de depender do serviço de referência e passou a usar um **servidor coordenador**.

O sistema mantém:
- uma variável com o nome do coordenador;
- uma lógica de eleição entre servidores;
- um fluxo de sincronização em que os servidores seguidores solicitam a hora ao coordenador.

Quando o coordenador deixa de responder:
- os servidores iniciam nova eleição;
- o novo coordenador é anunciado internamente;
- os demais passam a sincronizar o relógio a partir dele.

### 3.11. Replicação de estado
Na Parte 5, os servidores passaram a replicar:
- logins;
- canais;
- publicações.

Além da replicação por eventos, também foi adicionada uma sincronização completa de estado na inicialização do servidor, permitindo reconstruir localmente informações que já existiam em outros nós.

---

## 4. Regras de Negócio e Validação
- **Login:** o nome do usuário não pode ser vazio, deve ter entre 3 e 20 caracteres e não pode conter caracteres especiais.
- **Canais:** o nome do canal deve começar com `#` e ter pelo menos 3 caracteres.
- **Canal duplicado:** caso um cliente tente criar um canal que já exista, o servidor responde com erro, sem duplicar o registro.
- **Publicação:** o canal deve existir e a mensagem não pode ser vazia.
- **Persistência:** logins, canais e publicações ficam armazenados em disco no arquivo local de cada servidor.
- **Relógio lógico:** toda mensagem deve carregar o valor do contador lógico do emissor.
- **Heartbeat:** o servidor deve permanecer enviando heartbeat para continuar listado como disponível.
- **Replicação:** toda alteração persistente importante deve ser propagada para os demais servidores.
- **Idempotência:** eventos replicados não devem ser aplicados duas vezes.

---

## 5. Funcionamento dos Bots
Os clientes funcionam como bots automáticos.

Na Parte 1, o fluxo era composto por:
1. login;
2. listagem de canais;
3. criação de canais;
4. nova listagem para conferência.

Na Parte 2, esse comportamento foi ampliado. Ao iniciar, cada bot:
1. realiza login;
2. solicita a lista de canais disponíveis;
3. se existirem menos de 5 canais, cria um novo;
4. se estiver inscrito em menos de 3 canais, inscreve-se em mais um canal;
5. entra em loop infinito;
6. escolhe um canal disponível;
7. envia 10 mensagens automáticas com intervalo de 1 segundo entre elas.

Nas Partes 3, 4 e 5, esse comportamento funcional foi mantido, mas o sistema passou a operar com:
- relógio lógico;
- heartbeat;
- coordenador para sincronização de relógio;
- replicação de estado entre servidores.

Além disso, o cliente permanece ouvindo continuamente os canais assinados para exibir no terminal as mensagens recebidas.

Esse comportamento contínuo está de acordo com o enunciado das partes do trabalho.

---

## 6. Estrutura de Comunicação

### 6.1. Req/Rep
Esse fluxo é usado para:
- login;
- listagem de canais;
- criação de canais;
- solicitação de publicação;
- comunicação entre servidores e serviço de referência;
- comunicação interna entre servidores para eleição, sincronização de relógio e sincronização de estado.

### 6.2. Pub/Sub
Esse fluxo é usado para:
- distribuir mensagens publicadas nos canais;
- permitir que clientes inscritos recebam essas mensagens;
- propagar eventos internos de replicação entre servidores;
- anunciar coordenador no tópico interno `servers`.

O nome do canal é utilizado como **tópico** da mensagem Pub/Sub.

---

## 7. Persistência dos Dados
Cada servidor possui seu próprio arquivo `state.json`, armazenado em volume Docker independente.

Nesse arquivo são mantidos:
- `logins`;
- `channels`;
- `publications`;
- `replication_ids`.

As publicações armazenadas incluem pelo menos:
- canal;
- remetente;
- texto;
- timestamp original;
- timestamp de persistência;
- servidor responsável pelo processamento.

A presença dos `replication_ids` permite evitar duplicidade na aplicação de eventos replicados.

Essa estrutura permite recuperar as informações futuramente, conforme exigido no trabalho.

---

## 8. Logs da Aplicação
Durante a execução, os containers exibem logs que permitem acompanhar o funcionamento do sistema.

Os logs mostram:
- inicialização do broker Req/Rep;
- inicialização do proxy Pub/Sub;
- inicialização do serviço de referência;
- login dos bots;
- listagem e criação de canais;
- replicação de canais, logins e publicações entre servidores;
- inscrições em canais;
- publicações enviadas pelos clientes;
- respostas dos servidores;
- mensagens recebidas pelos clientes inscritos;
- rank atribuído aos servidores;
- heartbeat enviado e recebido;
- lista de servidores disponíveis;
- eleição de coordenador;
- sincronização de relógio;
- sincronização de estado no startup;
- valores de relógio lógico nas mensagens.

Isso facilita a validação do funcionamento distribuído do projeto.

---

## 9. Como Executar
1. Certifique-se de que o Docker está instalado na máquina.
2. Abra o terminal na pasta raiz do projeto.
3. Execute:

```bash
docker compose up --build
```

4. O Docker irá criar as imagens e iniciar:
- o broker Req/Rep;
- o proxy Pub/Sub;
- o serviço de referência;
- os dois servidores;
- os dois clientes.

5. Após a inicialização, os bots começarão a operar automaticamente.

---

## 10. Containers da Aplicação
A aplicação sobe os seguintes containers:
- `broker`: broker do fluxo Req/Rep;
- `pubsub`: proxy do fluxo Pub/Sub;
- `reference`: serviço de referência;
- `server1`: primeiro servidor Python;
- `server2`: segundo servidor Python;
- `client_alfa`: primeiro bot cliente Java;
- `client_beta`: segundo bot cliente Java.

---

## 11. Considerações Finais
A Parte 1 estabeleceu a base do sistema, permitindo login, criação e listagem de canais com persistência e sincronização entre servidores.

A Parte 2 ampliou essa base com o uso do padrão Publisher-Subscriber, permitindo:
- inscrição em canais;
- publicação de mensagens;
- recebimento assíncrono das publicações;
- persistência das mensagens publicadas.

A Parte 3 adicionou mecanismos de controle de tempo e disponibilidade, incluindo:
- relógio lógico nos processos e nas mensagens;
- heartbeat;
- rank dos servidores;
- lista de servidores disponíveis.

A Parte 4 modificou a sincronização do relógio físico, passando a utilizar um servidor coordenador eleito entre os próprios servidores.

Por fim, a Parte 5 resolveu o problema de consistência do histórico entre os servidores, implementando replicação de dados e sincronização de estado.

Com isso, o projeto atende aos requisitos centrais das cinco etapas propostas no trabalho, mantendo a comunicação distribuída entre múltiplos processos, a execução automatizada por bots e a replicação do histórico entre todos os servidores.