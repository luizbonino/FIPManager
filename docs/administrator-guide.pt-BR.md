# Executando o Gerenciador de FIP — Guia para Administradores e Facilitadores

**Gerenciador de FIP** é uma ferramenta pequena e auto-hospedada para criar, comparar e exportar
[GO FAIR](https://www.gofair.foundation/) **Perfis de Implementação FAIR (FIPs)**. Ele é projetado
para ser executado por uma pessoa para uma comunidade ou evento: um facilitador abre uma sessão,
participantes preenchem perfis em seus celulares, e a sala compara os resultados lado a lado
e os exporta como JSON, CSV e RDF.

Este guia é para a pessoa que **gerencia uma instância** — deploy, preparação dos
questionários, facilitação de sessões, administração de usuários e operação posterior. Para
as pessoas que preenchem os formulários, veja o
[Guia para Participantes](participant-guide.pt-BR.md); para o roteiro de 30 minutos do workshop CONFOA, veja
[`workshop/facilitator-script.md`](workshop/facilitator-script.md).

> **Escala e formato.** A stack é FastAPI + SQLAlchemy + SQLite e Vue 3 + Vite. É projetada
> para ser executada a partir de um único container, sobreviver a uma rede de conferência, e
> funcionar off-line a partir de um laptop e um hotspot caso o Wi-Fi do local falhe.

---

## Sumário

1. [As peças e como elas se encaixam](#1-as-peças-e-como-elas-se-encaixam)
2. [Quem pode fazer o quê](#2-quem-pode-fazer-o-quê)
3. [Implantando uma instância](#3-implantando-uma-instância)
4. [Referência de configuração](#4-referência-de-configuração)
5. [Preparando o questionário (modelos de conhecimento)](#5-preparando-o-questionário-modelos-de-conhecimento)
6. [Importando questionários por área a partir de um documento](#6-importando-questionários-por-área-a-partir-de-um-documento)
7. [Executando uma sessão](#7-executando-uma-sessão)
8. [Comparando os resultados](#8-comparando-os-resultados)
9. [O catálogo de FER](#9-o-catálogo-de-fer)
10. [Administração de usuários](#10-administração-de-usuários)
11. [Exportações e RDF](#11-exportações-e-rdf)
12. [Movendo FIPs para uma nova versão de questionário](#12-movendo-fips-para-uma-nova-versão-de-questionário)
13. [O painel](#13-o-painel)
14. [A rede de nanopublicações](#14-a-rede-de-nanopublicações)
15. [Operando a instância](#15-operando-a-instância)
16. [Referência de linha de comando](#16-referência-de-linha-de-comando)
17. [Solução de problemas](#17-solução-de-problemas)

---

## 1. As peças e como elas se encaixam

| Termo | O que é |
|---|---|
| **Modelo de conhecimento** | O questionário em si — seções, perguntas, textos de ajuda, opções sugeridas, em cada idioma. Versionado, e ou um **rascunho** (editável) ou **publicado** (congelado). |
| **Versão** | Um modelo de conhecimento publicado é imutável. Alterações vão para uma nova versão; FIPs existentes permanecem na versão em que foram preenchidos até serem migrados. |
| **FER** (FAIR Enabling Resource) | Uma tecnologia, serviço ou padrão nomeado que pode ser dado como resposta. Vive ou no **catálogo do sistema** (global) ou **inline** em um modelo de conhecimento. |
| **Sessão** | Um exercício facilitado: um código de acesso, um ou mais questionários, e os FIPs produzidos nele. |
| **Área** | Um de vários questionários oferecidos por uma única sessão, para que participantes escolham aquele que corresponde à sua área. |
| **FIP** | As respostas de uma comunidade. Pertence a uma sessão, à área de trabalho de um usuário, ou a nenhuma (independente). |
| **População** | Um conceito do painel: o conjunto de FIPs sobre o qual uma análise é executada — uma sessão, os FIPs públicos desta instância, ou FIPs ingeridos da rede. |

O conteúdo é **dados, não código**: questionários, o catálogo de FER e traduções são JSON
sob `data/`. Alterar as perguntas nunca requer uma alteração de código ou um redeploy da
imagem da aplicação.

---

## 2. Quem pode fazer o quê

| Função | Pode |
|---|---|
| **Visitante anônimo** | Participar de uma sessão e preencher um FIP; criar um FIP independente; navegar por modelos de conhecimento públicos e FIPs públicos; ler o questionário impresso |
| **Usuário cadastrado** | Tudo o acima, mais uma área de trabalho própria de FIPs, sessões e modelos; reivindicar FIPs anônimos; definir visibilidade de FIP; criar e executar sessões; bifurcar e publicar modelos de conhecimento |
| **Admin** | Tudo o acima, mais a página de admin: listar e buscar usuários, emitir senhas temporárias, promover e mesclar FERs pendentes, e editar rascunhos de modelos de conhecimento sem donos |

![A área de trabalho pessoal: meus FIPs, minhas sessões, meus modelos de conhecimento](images/workspace.png)

Não existe uma função separada de "facilitador" — **qualquer usuário cadastrado pode executar uma sessão**. Facilitação
é algo que você faz, não uma permissão que lhe é concedida.

---

## 3. Implantando uma instância

### O caminho rápido

```sh
docker compose up --build
```

### Executando diretamente

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```sh
cd backend
uv sync
cp ../.env.example ../.env    # então edite — veja §4
uv run python -m fipm import-data
uv run python -m fipm serve   # http://localhost:8000
```

Frontend (Node 20):

```sh
cd frontend && npm install && npm run dev
```

`FIPM_DB_PATH` e `FIPM_DATA_DIR` padronizam para `<repo-root>/fipm.db` e `<repo-root>/data`,
resolvidos a partir da localização do próprio módulo de configuração, em vez do diretório de trabalho,
portanto `import-data` e `serve` encontram o `data/` real, independentemente de serem executados
a partir do root do repositório ou de `backend/`.

### Antes de deixar qualquer pessoa entrar

- [ ] **Defina `FIPM_SECRET_KEY`** para um valor aleatório real. O padrão é `dev-secret-change-me`
      e definir `FIPM_ENV=production` se recusa a iniciar com segredos de desenvolvimento no lugar.
- [ ] **Defina `FIPM_BASE_URL`** para a URL HTTPS pública. É usada para construir links de acesso, códigos QR
      e identificadores de FIP — veja o aviso abaixo.
- [ ] **Sirva via HTTPS** e mantenha `FIPM_COOKIE_SECURE=true`.
- [ ] **Crie o usuário admin**: `uv run python -m fipm create-admin --email you@example.org --password '…'`
- [ ] **Carregue o conteúdo**: `uv run python -m fipm import-data`
- [ ] **Defina `FIPM_CONTACT_EMAIL` e `FIPM_HOSTING_ORG`** — eles aparecem no aviso de privacidade,
      que é uma promessa que você está fazendo aos participantes.
- [ ] **Se estiver atrás de um proxy reverso**, defina `FIPM_TRUST_PROXY=true` apenas depois de verificar se
      o proxy realmente define `X-Forwarded-For`. Confiar nele sem verificação permite que clientes falsifiquem
      seu IP e contornem o limite de taxa.

> **`FIPM_BASE_URL` sobrevive ao seu hostname.** Identificadores de FIP são construídos a partir dele,
> então mover a instância para um domínio diferente mais tarde altera a identidade de todos os FIPs já criados.
> Decida a URL pública permanente *antes* que o primeiro FIP real exista, não depois.

---

## 4. Referência de configuração

Todas as configurações são variáveis de ambiente com prefixo `FIPM_`, lidas por `backend/fipm/config.py`;
veja `.env.example` para a lista oficial.

### Identidade e segurança

| Configuração | Padrão | Controles |
|---|---|---|
| `FIPM_BASE_URL` | `http://localhost:8000` | URL pública; links de acesso, códigos QR, identificadores de FIP |
| `FIPM_SECRET_KEY` | `dev-secret-change-me` | Assinatura de sessão — **deve** ser alterada |
| `FIPM_ENV` | `development` | `production` recusa segredos de desenvolvimento |
| `FIPM_COOKIE_SECURE` | `true` | Exige HTTPS para cookies de sessão |
| `FIPM_ALLOWED_ORIGINS` | *(vazio)* | Lista de permissões CORS |
| `FIPM_TRUST_PROXY` | `false` | Confiar em `X-Forwarded-For` — apenas atrás de um proxy verificado |
| `FIPM_MAX_BODY_BYTES` | 2 MiB | Limite de tamanho do corpo da requisição |
| `FIPM_SESSION_TTL_DAYS` | `14` | Expiração de sessão facilitada |

### Armazenamento e conteúdo

| Configuração | Padrão | Controles |
|---|---|---|
| `FIPM_DB_PATH` | `./fipm.db` | Arquivo SQLite |
| `FIPM_DATA_DIR` | `./data` | Modelos de conhecimento e catálogo de FER |
| `FIPM_STATIC_DIR` | `./frontend/dist` | Frontend compilado |
| `FIPM_DEFAULT_LANGUAGE` | `en` | Idioma de fallback |
| `FIPM_ID_PREFIX` | *(vazio)* | Prefixo para IDs gerados |

### Quem pode fazer o quê

| Configuração | Padrão | Controles |
|---|---|---|
| `FIPM_REGISTRATION_OPEN` | `true` | Se qualquer pessoa pode criar uma conta |
| `FIPM_ANONYMOUS_FIPS` | `true` | Se FIPs podem ser criados sem sessão ou conta |
| `FIPM_REQUIRE_EMAIL_VERIFICATION` | `false` | Portão de verificação de e-mail — **desativado** para o workshop |
| `FIPM_FEEDBACK_ENABLED` | `true` | O formulário de feedback |

### Aviso de privacidade

| Configuração | Padrão | Controles |
|---|---|---|
| `FIPM_CONTACT_EMAIL` | `contact@example.org` | Exibido em `/privacy` |
| `FIPM_HOSTING_ORG` | `the FIP Manager operators` | Exibido em `/privacy` |

### E-mail

`FIPM_MAIL_BACKEND` padroniza para `console` (mensagens são registradas, não enviadas). Para e-mail real,
defina-o para `smtp` e configure `FIPM_MAIL_FROM`, `FIPM_SMTP_HOST`, `FIPM_SMTP_PORT`, `FIPM_SMTP_USER`,
`FIPM_SMTP_PASSWORD`, `FIPM_SMTP_TLS`. Os tempos de vida dos tokens são `FIPM_MAIL_TOKEN_TTL_HOURS` (24) e
`FIPM_RESET_TOKEN_TTL_HOURS` (1).

### Integração e rede

| Configuração | Padrão | Controles |
|---|---|---|
| `FIPM_FIODMP_BASE_URL` | `https://fiodmp.fiocruz.br` | Vinculação a DMP |
| `FIPM_EMBED_ALLOWED_ORIGINS` | `https://fiodmp.fiocruz.br` | `frame-ancestors` para a visualização de embed |
| `FIPM_NETWORK_ENABLED` | `true` | Endpoints da rede de nanopublicações |
| `FIPM_NANOPUB_QUERY_URL` | `https://query.knowledgepixels.com` | Serviço de consulta da rede |
| `FIPM_NETWORK_TIMEOUT_SECONDS` | `10.0` | Timeout por requisição |
| `FIPM_NETWORK_CACHE_TTL_SECONDS` | `900` | Cache de resposta |
| `FIPM_NETWORK_MAX_RESPONSE_BYTES` | 8 MiB | Limite de resposta upstream |

### Painel

O painel possui um grande número de configurações de ajuste; as que valem a pena conhecer são:

| Configuração | Padrão | Controles |
|---|---|---|
| `FIPM_DASHBOARD_ENABLED` | `true` | Desativa todo o painel |
| `FIPM_DASHBOARD_MIN_POPULATION` | `5` | Piso de k-anonimidade — contagens são retidas abaixo disso quando a população contém FIPs que o visualizador pode não abrir |
| `FIPM_DASHBOARD_DEFAULT_WEIGHTING` | `principle` | Ponderação de similaridade: `principle`, `question` ou `letter` |
| `FIPM_DASHBOARD_CLUSTER_MIN_SIM` | `0.6` | Limiar de similaridade para desenhar uma aresta de cluster |
| `FIPM_DASHBOARD_SNAPSHOT_TTL_SECONDS` | `3600` | Quanto tempo uma visualização em cache permanece atual |
| `FIPM_DASHBOARD_CSV_MAX_ROWS` | `100000` | Limite de linhas em exportações CSV do painel |
| `FIPM_DASHBOARD_BACKFILL_ON_STARTUP` | `true` | Constrói a projeção na inicialização para instâncias pequenas |

As configurações restantes `FIPM_DASHBOARD_LSH_*`, `_POSTING_*` e `_MAX_CELLS` ajustam o índice de similaridade
e os limites entre os níveis live/snapshot. Deixe-as em paz a menos que esteja executando dezenas de
milhares de FIPs; `FIPM_DASHBOARD_LSH_BANDS × FIPM_DASHBOARD_LSH_ROWS` deve ser igual a
`FIPM_DASHBOARD_LSH_K`.

---

## 5. Preparando o questionário (modelos de conhecimento)

O editor de modelos de conhecimento está na sua área de trabalho. Você pode:

![O catálogo de modelos de conhecimento](images/knowledge-model-catalogue.png)

- **Derivar** um modelo existente — o ponto de partida usual. Você obtém um rascunho editável.
- **Criar do zero**, ou **importar** um modelo exportado em outro lugar.

Dentro de um rascunho sob seu controle, por pergunta:

- **Texto e ajuda**, em cada idioma, em abas de idioma (en, pt-PT, pt-BR, es).
- **Tipo de FER** — que tipo de recurso a pergunta pede. Isso é o que torna uma resposta
  verificável quanto ao tipo, então defina-o deliberadamente.
- **FERs sugeridos** — recursos do catálogo oferecidos como escolhas rápidas (no máximo 16 por pergunta).
- **Frases sugeridas** — textos livres oferecidos como escolhas rápidas, para práticas que não são
  um produto nomeado (no máximo 12 por pergunta). Estas nunca entram no catálogo de FER.
- **Permitir múltiplas** declarações, e **permitir texto livre** (ambos ativos por padrão).
- **Declarações compactas** — recolhe status, nota e sucessor atrás de um alternador "Mais". Isso
  é o que mantém o formulário utilizável em um celular; mantenha-o ativo para modelos de workshop.

Você pode reordenar, ocultar, dividir e adicionar perguntas, e o editor valida o modelo e lista
erros antes que você o publique.

![Um modelo de conhecimento publicado](images/knowledge-model-read.png)

> **Publicar é sem volta.** Uma versão publicada é congelada para que os FIPs preenchidos contra ela
> permaneçam significativos. Correções vão para uma nova versão, com uma entrada no registro de alterações.
> Planeje publicar *antes* do evento, não durante.

Ordem das opções conforme os participantes veem: opções do catálogo, então frases sugeridas, então
**"Outro (especificar)"**.

---

## 6. Importando questionários por área a partir de um documento

`scripts/import-workshop-docx.py` transforma um documento Word de listas de opções por área em um rascunho
de modelo de conhecimento por área:

```sh
uv run --project backend python scripts/import-workshop-docx.py \
    --docx "docs/workshop/PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx" --bump --report -
```

Ele escreve rascunhos `confoa-2026-<area>-<version>.json` mais um relatório de perguntas ausentes e
opções não resolvidas — **leia o relatório**. Opções que nomeiam um recurso do catálogo se tornam
FERs sugeridos; frases descritivas se tornam frases sugeridas; os sentinelas "Outro", "Não se
aplica" e "Ainda não definido" são tratados pela interface em vez de se tornarem opções.

Reexecutar é seguro: um documento alterado produz uma nova versão de rascunho ao lado da antiga,
nunca uma sobrescrita. Use `--overwrite-draft` apenas quando deliberadamente quiser substituir um
rascunho não publicado.

> **Os rascunhos não ficam ativos até que uma pessoa os publique.** Revise cada um no editor —
> especialmente as opções com incompatibilidade de tipo que o relatório sinaliza — e então publique.

---

## 7. Executando uma sessão

**Crie** uma sessão a partir da sua área de trabalho: dê um título a ela, escolha **uma ou mais**
versões de questionário, opcionalmente rotule cada uma como uma área, e defina um idioma padrão.

![Criando uma sessão e escolhendo seus questionários](images/session-new.png)

A página da sessão é o seu console durante o exercício:

![A página da sessão com seu código de acesso e código QR](images/session-detail.png)

- **Código de acesso e QR** — o que os participantes usam para entrar. O **modo de projeção** remove
  os elementos da página para que o código e o QR sejam legíveis do fundo de uma sala.
- **Uma lista ao vivo de FIPs** conforme eles são criados, atualizando sem refresh.
- **Exportações** de todos os FIPs na sessão, juntos.
- **A matriz de comparação** (veja [§8](#8-comparando-os-resultados)).
- **Feche** a sessão para evitar que novos participantes entrem, e **exclua** quando finalizada.

![A lista ao vivo de FIPs em uma sessão](images/session-fip-list.png)

![Modo de projeção, com os elementos da página removidos](images/projector-mode.png)

> **O que a exclusão faz.** Excluir uma sessão remove em cascata os FIPs anônimos criados nela. FIPs
> que os participantes reivindicaram para suas próprias contas são desvinculados e sobrevivem.
> Feche uma sessão quando simplesmente quiser que ela pare de aceitar novas entradas.

Algumas coisas que valem a pena saber antes que a sala encha:

- **Imprima um fallback em papel.** Todo modelo publicado tem um questionário imprimível em
  `/knowledge-models/{id}/{version}/print`, com linhas para preencher. Traga cópias.
- **Participantes não precisam de contas.** Exigir cadastro na porta é a maneira mais fácil de
  perder dez minutos de um exercício de trinta minutos.
- **O link de acesso é `{FIPM_BASE_URL}/join/{joinCode}`.** Se o QR falhar, os participantes podem
  digitar o código na página inicial.

![O questionário de papel impresso](images/questionnaire-print.png)

---

## 8. Comparando os resultados

A **matriz de comparação** em `/sessions/{id}/matrix` é a visualização para colocar no projetor quando o
preenchimento parar. Ela mostra princípio × grupo, atualiza ao vivo conforme os FIPs mudam, pode ser
filtrada para apenas declarações atuais, e imprime. A convergência por princípio mostra onde a sala
concordou e onde não — o que geralmente é a parte mais produtiva da discussão.

![A matriz de comparação: princípios por grupo](images/comparison-matrix.png)

Para análise além de uma sessão, use o [painel](#13-o-painel).

---

## 9. O catálogo de FER

Respostas nomeiam **Recursos de Habilitação FAIR (FERs)**. O catálogo tem dois níveis:

- **Catálogo do sistema** — global, curado, compartilhado entre modelos. Sob `data/`.
- **FERs inline** — definidos dentro de um único modelo de conhecimento, para recursos específicos a ele.

Quando participantes digitam um recurso que não está no catálogo, ele se torna um FER **pendente**.
Na página de admin, você pode:

- **Promover** um FER pendente para o catálogo do sistema, e
- **Mesclar** dois FERs, substituindo todo uso de um pelo outro — a correção para a mesma coisa
  escrita de três maneiras diferentes.

> **Cure após o evento, não durante.** Promover é uma decisão de julgamento sobre se
> algo é um recurso real e nomeável, e mesclar reescreve respostas existentes. Nenhum
> dos dois se beneficia de ser feito às pressas com uma sala esperando.

---

## 10. Administração de usuários

A página de admin (`/admin`, apenas admins) lista usuários com nome, e-mail, função, data de criação
e quantos FIPs, sessões e modelos eles possuem, e permite buscar.

**Redefinição de senha** emite uma senha temporária, mostrada **uma vez** — copie-a antes de fechar
o diálogo. O usuário é forçado a alterá-la no próximo login.

![A página de admin: lista de usuários e FERs pendentes](images/admin-page.png)

Também nesta página: promoção/mesclagem de FER pendente, e rascunhos de modelos de conhecimento sem donos
(por exemplo, aqueles escritos pelo script de importação), que admins podem editar e publicar.

---

## 11. Exportações e RDF

| Escopo | Formatos |
|---|---|
| Um FIP | JSON, CSV, Turtle, JSON-LD |
| Uma sessão inteira | JSON, CSV, Turtle |
| Um questionário | Turtle, JSON-LD, e uma versão impressa em papel |
| Uma visualização do painel | CSV |

RDF segue a **ontologia FIP** (`https://w3id.org/fair/fip/terms/`), então as exportações são utilizáveis
por qualquer ferramenta FAIR, não apenas esta instância. Declarações carregam seu status, então "Planejado"
e "Em uso" permanecem distinguíveis, e `migratedFrom` registra de onde veio uma resposta migrada.

> **Pendente:** o vocabulário de extensão `https://w3id.org/fipm/ns#` usado pela exportação
> **ainda não está registrado** no w3id, e a página de termos ainda não foi publicada. Exportações são
> RDF válido e estável em formato, mas aquele namespace ainda não resolve.

Exportações CSV carregam uma proteção contra injeção de fórmulas, então são seguras para abrir em uma
planilha.

---

## 12. Movendo FIPs para uma nova versão de questionário

Quando você publica uma nova versão de um modelo, os FIPs existentes permanecem na versão antiga.
`/fips/{id}/migrate` caminha com um FIP pela nova versão, mostrando um diff de pergunta antiga →
nova pergunta com o que foi mapeado, adicionado e removido, e sinaliza onde o texto ou o tipo de FER
de uma pergunta mudou. Quando uma pergunta antiga se tornou várias novas, você escolhe como dividir
suas declarações. Exportações registram `migratedFrom`.

**FIPs criados dentro de uma sessão estão vinculados** à versão do questionário dessa sessão e não
podem ser migrados para longe dela — o registro do que um evento realmente usou permanece intacto.
A página de migração mostra um aviso em vez de oferecer a mudança. FIPs independentes, e FIPs que não
estão mais vinculados a uma sessão, migram livremente.

---

## 13. O painel

O painel analisa uma **população** de FIPs — uma sessão, os FIPs públicos desta instância, ou
FIPs ingeridos da rede de nanopublicações — por meio de cinco visualizações:

| Visualização | Respostas |
|---|---|
| **Cobertura** | Quais princípios FAIR esta população realmente aborda |
| **Adoção** | Quais recursos são usados, e quão amplamente |
| **Similaridade** | Quais comunidades se assemelham umas às outras; clusters e vizinhos |
| **Lacunas** | Quais perguntas estão ficando sem resposta |
| **Evolução** | Como o cenário muda com o tempo |

![A visualização de similaridade: clusters e vizinhos](images/dashboard-similarity.png)

Cada visualização exporta para CSV e tem uma folha de estilo para impressão.

![A página inicial do painel com o seletor de população](images/dashboard-home.png)

Dois comportamentos para entender antes de mostrar para qualquer pessoa:

- **k-anonimidade.** Quando uma população é menor que `FIPM_DASHBOARD_MIN_POPULATION` *e*
  contém FIPs que o visualizador pode não abrir individualmente, as contagens são **retidas** em vez de
  mostradas. Uma contagem retida é exibida como tal — não é exibida como zero. Visualizar a própria
  sessão é deliberadamente isenta, para que um facilitador possa sempre ler a sua própria sala pequena.
- **Modo degradado.** Se a projeção subjacente estiver desatualizada ou ausente, o painel informará
  em vez de mostrar números que não pode sustentar. Instâncias pequenas recalculam na hora;
  instâncias maiores mostram um banner e a idade dos dados.

![A visualização de cobertura](images/dashboard-coverage.png)

Mantenha-o atual com `refresh-dashboard`, e reconstrua a projeção com `backfill-declarations`
depois de uma importação em lote. `check-declarations` verifica se a projeção ainda corresponde aos FIPs.

---

## 14. A rede de nanopublicações

Com `FIPM_NETWORK_ENABLED=true`, `/network` navega e busca por comunidades de FIP publicadas como
nanopublicações, mapeia qualquer FIP da rede nas perguntas desta instância (listando perguntas que não
consegue mapear), e oferece **"Usar como ponto de partida"** para pré-preencher um novo FIP, importando
recursos desconhecidos como FERs do catálogo marcados com a origem `network`.

Todo FIP também pode ser baixado como um **zip de nanopublicações não assinadas** — comunidade, uma por
declaração, índice e FIP — no formato do FIP Wizard, com um manifesto do que ainda é necessário para publicação.

> **Esta instância não publicará para a rede e não guardará chaves.** Assinar requer um ORCID, uma
> chave RSA, uma declaração de chave e `nanopub-py` ou `nanopub-java`. O lado de leitura e o lado de
> preparação para exportação estão completos; o lado de publicação deliberadamente não está.

`ingest-network-fips` puxa FIPs da rede como linhas sombras apenas para leitura para análise do painel.
Eles são fatos ingeridos, nunca buscas ao vivo — o painel nunca chama a rede enquanto renderiza.

---

## 15. Operando a instância

**Faça backup do banco de dados.** `scripts/backup-db.sh` faz uma cópia consistente do arquivo SQLite.
Tudo que um participante produziu está lá; `data/` contém apenas o conteúdo que você autorou. Execute
o script antes de qualquer migração ou importação em lote, e em um cronograma assim que estiver ativo.

**Retenção.** FIPs independentes carregam uma promessa de retenção de doze meses no aviso de privacidade.
Nada a aplica automaticamente — nenhum agendador é fornecido com a ferramenta. Execute
`purge-standalone-fips` mensalmente, ou a promessa em `/privacy` não está sendo cumprida.

**Limite de taxa** protege login, feedback, criação de FIPs independentes e populações do painel salvas.
Ele depende de ver os IPs reais dos clientes — veja `FIPM_TRUST_PROXY` em
[§3](#3-implantando-uma-instância).

**Capacidade.** Testado em carga com 40 e 80 participantes concorrentes simulados sem erros e p95
abaixo de 10 ms em escritas, com SQLite no modo WAL. Uma sala de conferência não é um problema de escala;
`scripts/load-test.py` reexecuta a verificação.

**Fallback off-line.** Toda a stack roda a partir de um laptop e um hotspot. Teste isto antes do
evento, com um celular real entrando em um hotspot real — é a contingência mais provável de ser
necessária e menos provável de ter sido testada.

---

## 16. Referência de linha de comando

Execute como `uv run python -m fipm <command>` a partir de `backend/`.

| Comando | Argumentos principais | Faz |
|---|---|---|
| `import-data` | `--force` | Carrega modelos de conhecimento e catálogo de FER de `data/` para o banco de dados. Idempotente; `--force` sobrescreve modelos alterados |
| `create-admin` | `--email`, `--password` | Cria um usuário como admin, ou promove um existente |
| `serve` | `--host`, `--port`, `--reload` | Executa o servidor da API |
| `purge-standalone-fips` | `--older-than-days` (365), `--dry-run` | Exclui FIPs independentes não modificados há N dias. **Sempre faça dry-run primeiro** |
| `backfill-declarations` | `--batch`, `--questionnaire`, `--since`, `--only-stale`, `--dry-run`, `--progress` | Reconstrói a projeção do painel. Idempotente e em lote |
| `check-declarations` | `--sample`, `--all`, `--fix`, `--json` | Verifica se a projeção corresponde aos FIPs |
| `refresh-dashboard` | `--population`, `--all-saved`, `--views`, `--force`, `--json` | Recalcula instantâneos do painel em cache |
| `ingest-network-fips` | `--limit`, `--community`, `--since`, `--json` | Puxa FIPs da rede como linhas sombras apenas para leitura |

---

## 17. Solução de problemas

| Sintoma | Causa e correção |
|---|---|
| **Recusa iniciar em produção** | Segredos de desenvolvimento ainda no lugar. Defina um `FIPM_SECRET_KEY` real. |
| **Links de acesso ou códigos QR apontam para localhost** | `FIPM_BASE_URL` não está definido ou está errado. Ele também está incorporado a identificadores de FIP — corrija antes que dados reais existam. |
| **Participantes não conseguem entrar, mas deveriam poder** | Verifique `FIPM_REGISTRATION_OPEN`, e `FIPM_REQUIRE_EMAIL_VERIFICATION` (que requer um backend de e-mail funcional — o padrão apenas registra). |
| **Nenhum e-mail chega** | `FIPM_MAIL_BACKEND` padroniza para `console`. Defina-o para `smtp` e configure as configurações SMTP. |
| **Limite de taxa bloqueia ou ignora as pessoas erradas** | Os IPs dos clientes estão errados. Defina `FIPM_TRUST_PROXY=true` apenas atrás de um proxy que você verificou. |
| **Perguntas ou traduções não aparecem após editar `data/`** | Execute `import-data` (`--force` se o modelo tiver mudado). |
| **Painel mostra um banner de dados desatualizados** | Execute `backfill-declarations`, depois `refresh-dashboard`. |
| **Painel retém contagens** | k-anonimidade. Esperado para populações pequenas contendo FIPs que o visualizador pode não abrir; não é um erro. |
| **Um FIP não pode ser migrado** | A versão do modelo está fixa. |
| **Um recurso aparece três vezes sob nomes diferentes** | Mescle-os na página de admin. |
| **`/network` está vazio ou desativado** | `FIPM_NETWORK_ENABLED`, ou o serviço de consulta upstream está inacessível. O resto da ferramenta não é afetado. |

---

## Atribuição

Conteúdo do questionário: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna,
Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0. Listas de opções por área adaptadas de "PERFIS DE
IMPLEMENTAÇÃO FAIR 2" (autor a ser confirmado), usadas sob os mesmos termos CC BY-SA 4.0.
