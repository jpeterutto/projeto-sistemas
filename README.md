# Entrega 1 - Sistema de Mensagens Distribuído

## 1. Introdução do Projeto
Este projeto corresponde à primeira entrega de um sistema distribuído de mensagens instantâneas inspirado em serviços como BBS e IRC. Nesta etapa, o foco está na comunicação entre clientes, desenvolvidos em Java, e servidores, desenvolvidos em Python, utilizando ZeroMQ para troca de mensagens e Protocol Buffers para serialização binária.

## 2. Escolhas de Arquitetura e Justificativas
Para a arquitetura do sistema, foi adotado um broker ZeroMQ no padrão ROUTER-DEALER, responsável por intermediar a comunicação entre os clientes e os servidores.

- **Linguagens**: o cliente foi desenvolvido em Java, utilizando jeromq, e o servidor foi desenvolvido em Python. O broker também foi implementado em Python.
- **Serialização**: foi escolhido o Protocol Buffers, por ser um formato binário leve, estruturado e compatível entre Java e Python, atendendo à exigência do trabalho de não utilizar JSON, XML ou texto simples na comunicação.
- **Topologia com broker**: os clientes se conectam ao broker por meio de um socket REQ, e o broker distribui as requisições entre os servidores, que respondem utilizando o fluxo definido pela aplicação.
- **Persistência**: cada servidor mantém seu próprio arquivo state.json, armazenado em um volume separado do Docker. Dessa forma, os dados permanecem salvos entre execuções sem que haja compartilhamento direto de arquivo entre os servidores.
- **Histórico de logins**: os logins são registrados como uma lista de eventos, contendo nome do usuário, timestamp e identificação do servidor responsável. Assim, todos os logins realizados ficam armazenados, sem sobrescrever os anteriores.
- **Consistência dos canais**: para garantir que os canais criados fiquem disponíveis para todos os usuários, foi implementado um mecanismo de replicação entre os servidores usando ZeroMQ no padrão PUB/SUB. Quando um servidor cria um novo canal, esse evento é enviado aos demais, que atualizam seus próprios arquivos locais. Com isso, cada servidor mantém seu arquivo independente, mas todos permanecem com a mesma visão dos canais existentes.
- **Biblioteca Python**: na implementação em Python foi utilizada a biblioteca pyzmq, que é a forma correta de uso do ZeroMQ nesse ambiente.

## 3. Funcionamento dos Bots
Os clientes funcionam como bots e executam automaticamente o fluxo da Parte 1:

- conectam-se ao sistema e tentam realizar o login;
- caso o login falhe, aguardam alguns segundos e tentam novamente;
- solicitam a lista de canais disponíveis;
- tentam criar canais predefinidos caso eles ainda não existam;
- solicitam novamente a lista de canais para verificar o resultado das operações.

Todo esse processo acontece sem necessidade de interação manual do usuário.

## 4. Regras de Negócio e Validação

- **Login**: o nome do usuário não pode ser vazio, deve ter entre 3 e 20 caracteres e não pode conter caracteres especiais.
- **Canais**: o nome do canal deve começar com # e ter pelo menos 3 caracteres.
- **Canal duplicado**: caso um cliente tente criar um canal que já exista, o servidor responde com erro, sem duplicar o registro.
- **Persistência**: tanto os logins quanto os canais ficam armazenados em disco no arquivo local de cada servidor.

## 5. Como Executar

Certifique-se de que o Docker está instalado na máquina.

Abra o terminal na pasta raiz do projeto.

Execute o comando:

```bash
docker compose up --build
```

O Docker irá criar as imagens, iniciar os containers e executar automaticamente os bots, os servidores e o broker.

Durante a execução, os logs no terminal mostrarão as operações de login, listagem de canais, criação de canais e replicação entre os servidores.
