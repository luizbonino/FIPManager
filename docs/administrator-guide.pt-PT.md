# Executar o Gestor de FIP — Guia para Administradores e Facilitadores

**Gestor de FIP** é uma ferramenta autoalojada para criar, comparar e exportar
[GO FAIR](https://www.gofair.foundation/) **Perfis de Implementação FAIR (FIPs)**. É concebida
para ser utilizada por uma pessoa para uma comunidade ou evento: um facilitador abre uma sessão,
os participantes preenchem perfis nos seus telemóveis e a sala compara os resultados lado a lado
e exporta-os como JSON, CSV e RDF.

Este guia destina-se à pessoa que **executa uma instância** — implementá-la, preparar os
questionários, facilitar sessões, administrar utilizadores e operá-la posteriormente. Para as
pessoas que preenchem os formulários, veja o [Guia para Participantes](participant-guide.pt-PT.md);
para o guião de 30 minutos do workshop CONFOA, veja
[`workshop/facilitator-script.md`](workshop/facilitator-script.md).

> **Escala e estrutura.** A stack é FastAPI + SQLAlchemy + SQLite e Vue 3 + Vite. É concebida
> para ser executada a partir de um único contentor, para sobreviver a uma rede de conferência
e para funcionar offline a partir de um portátil e de um hotspot se o Wi-Fi do local falhar.

---

## Índice

1. [As peças e como se encadeiam](#1-as-peças-e-como-se-encadeiam)
2. [Quem pode fazer o quê](#2-quem-pode-fazer-o-quê)
3. [Implementar uma instância](#3-implementar-uma-instância)
4. [Referência de configuração](#4-referência-de-configuração)
5. [Preparar o questionário (modelos de conhecimento)](#5-preparar-o-questionário-modelos-de-conhecimento)
6. [Importar questionários por área a partir de um documento](#6-importar-questionários-por-área-a-partir-de-um-documento)
7. [Executar uma sessão](#7-executar-uma-sessão)
8. [Comparar os resultados](#8-comparar-os-resultados)
9. [O catálogo FER](#9-o-catálogo-fer)
10. [Administração de utilizadores](#10-administração-de-utilizadores)
11. [Exportações e RDF](#11-exportações-e-rdf)
12. [Mover FIPs para uma nova versão do questionário](#12-mover-fips-para-uma-nova-versão-do-questionário)
13. [O painel](#13-o-painel)
14. [A rede de nanopublicações](#14-a-rede-de-nanopublicações)
15. [Operar a instância](#15-operar-a-instância)
16. [Referência de linha de comandos](#16-referência-de-linha-de-comandos)
17. [Resolução de problemas](#17-resolução-de-problemas)

---

## 1. As peças e como se encadeiam

| Termo | O que é |
|---|---|
| **Modelo de conhecimento** | O questionário em si — secções, perguntas, textos de ajuda, opções sugeridas, em todos os idiomas. Com versão, e que pode ser um **rascunho** (editável) ou **publicado** (imutável). |
| **Versão** | Um modelo de conhecimento publicado é imutável. As alterações vão para uma nova versão; os FIPs existentes mantêm-se na versão contra a qual foram preenchidos até serem migrados. |
| **FER** (FAIR Enabling Resource) | Uma tecnologia, serviço ou norma nomeados que podem ser dados como resposta. Existem ou no **catálogo do sistema** (global) ou **embutidos** num modelo de conhecimento. |
| **Sessão** | Um exercício facilitado: um código de acesso, um ou mais questionários, e os FIPs produzidos nele. |
| **Área** | Um de vários questionários oferecidos por uma única sessão, para que os participantes escolham o que corresponde à sua área. |
| **FIP** | As respostas de uma comunidade. Pertence a uma sessão, à área de trabalho de um utilizador, ou a nenhum (autónomo). |
| **População** | Um conceito do painel: o conjunto de FIPs sobre o qual uma análise é executada — uma sessão, os FIPs públicos desta instância, ou FIPs ingeridos a partir da rede. |

O conteúdo é **dados, não código**: os questionários, o catálogo FER e as traduções são JSON
sob `data/`. Alterar as perguntas nunca exige uma alteração de código ou uma nova implementação
da imagem da aplicação.

---

## 2. Quem pode fazer o quê

| Função | Pode |
|---|---|
| **Visitante anónimo** | Participar numa sessão e preencher um FIP; criar um FIP autónomo; navegar modelos de conhecimento públicos e FIPs públicos; ler o questionário impresso |
| **Utilizador registado** | Tudo o acima, mais uma área de trabalho própria de FIPs, sessões e modelos; reivindicar FIPs anónimos; definir visibilidade de FIP; criar e executar sessões; bifurcar e publicar modelos de conhecimento |
| **Administrador** | Tudo o acima, mais a página de administração: listar e pesquisar utilizadores, emitir palavras-passe temporárias, promover e fundir FERs pendentes, e editar rascunhos de modelos de conhecimento sem proprietário |

![A área de trabalho pessoal: os meus FIPs, as minhas sessões, os meus modelos de conhecimento](images/workspace.png)

Não existe uma função separada de "facilitador" — **qualquer utilizador registado pode executar uma sessão**. Facilitar é algo que se faz, não uma permissão que é concedida.

---

## 3. Implementar uma instância

### O caminho rápido

```sh
docker compose up --build
```

### Executar diretamente

Backend (Python 3.12, [uv](https://docs.astral.sh/uv/)):

```sh
cd backend
uv sync
cp ../.env.example ../.env    # depois edite-o — veja §4
uv run python -m fipm import-data
uv run python -m fipm serve   # http://localhost:8000
```

Frontend (Node 20):

```sh
cd frontend && npm install && npm run dev
```

`FIPM_DB_PATH` e `FIPM_DATA_DIR` apontam por predefinição para `<repo-root>/fipm.db` e `<repo-root>/data`,
resolvidos a partir da localização do próprio módulo de configuração em vez do diretório de trabalho,
para que `import-data` e `serve` encontrem o `data/` real quer os execute a partir da raiz do repositório quer de
`backend/`.

### Antes de permitir a entrada de alguém

- [ ] **Definir `FIPM_SECRET_KEY`** com um valor aleatório real. O predefinido é `dev-secret-change-me`
      e definir `FIPM_ENV=production` recusa iniciar com segredos de desenvolvimento no lugar.
- [ ] **Definir `FIPM_BASE_URL`** para o URL HTTPS público. É utilizado para construir links de participação, códigos QR
      e identificadores de FIP — veja o aviso abaixo.
- [ ] **Servir por HTTPS** e manter `FIPM_COOKIE_SECURE=true`.
- [ ] **Criar o utilizador administrador**: `uv run python -m fipm create-admin --email you@example.org --password '…'`
- [ ] **Carregar o conteúdo**: `uv run python -m fipm import-data`
- [ ] **Definir `FIPM_CONTACT_EMAIL` e `FIPM_HOSTING_ORG`** — aparecem no aviso de privacidade,
      que é uma promessa que está a fazer aos participantes.
- [ ] **Se por detrás de um proxy inverso**, defina `FIPM_TRUST_PROXY=true` apenas após ter verificado que
      o proxy realmente define `X-Forwarded-For`. Confiar nisso de outra forma permite que os clientes falsifiquem o seu IP
      e contornem o limite de taxa.

> **`FIPM_BASE_URL` sobrevive ao seu nome de domínio.** Os identificadores de FIP são construídos a partir dele,
> pelo que mover a instância para um domínio diferente mais tarde altera a identidade de cada FIP já criado.
> Decida o URL público permanente *antes* de o primeiro FIP real existir, não depois.

---

## 4. Referência de configuração

Todas as definições são variáveis de ambiente com o prefixo `FIPM_`, lidas por `backend/fipm/config.py`; veja
`.env.example` para a lista autoritativa.

### Identidade e segurança

| Definição | Predefinição | Controla |
|---|---|---|
| `FIPM_BASE_URL` | `http://localhost:8000` | URL público; links de participação, códigos QR, identificadores de FIP |
| `FIPM_SECRET_KEY` | `dev-secret-change-me` | Assinatura de sessão — **deve** ser alterada |
| `FIPM_ENV` | `development` | `production` recusa segredos de desenvolvimento |
| `FIPM_COOKIE_SECURE` | `true` | Exige HTTPS para cookies de sessão |
| `FIPM_ALLOWED_ORIGINS` | *(vazio)* | Lista de permissões CORS |
| `FIPM_TRUST_PROXY` | `false` | Confiar em `X-Forwarded-For` — apenas por detrás de um proxy verificado |
| `FIPM_MAX_BODY_BYTES` | 2 MiB | Limite de tamanho do corpo do pedido |
| `FIPM_SESSION_TTL_DAYS` | `14` | Expiração de sessão facilitada |

### Armazenamento e conteúdo

| Definição | Predefinição | Controla |
|---|---|---|
| `FIPM_DB_PATH` | `./fipm.db` | Ficheiro SQLite |
| `FIPM_DATA_DIR` | `./data` | Modelos de conhecimento e catálogo FER |
| `FIPM_STATIC_DIR` | `./frontend/dist` | Frontend compilado |
| `FIPM_DEFAULT_LANGUAGE` | `en` | Idioma de recuo |
| `FIPM_ID_PREFIX` | *(vazio)* | Prefixo para IDs gerados |

### Quem pode fazer o quê

| Definição | Predefinição | Controla |
|---|---|---|
| `FIPM_REGISTRATION_OPEN` | `true` | Se qualquer pessoa pode criar uma conta |
| `FIPM_ANONYMOUS_FIPS` | `true` | Se os FIPs podem ser criados sem sessão ou conta |
| `FIPM_REQUIRE_EMAIL_VERIFICATION` | `false` | Porta de verificação de email — **desativada** para o workshop |
| `FIPM_FEEDBACK_ENABLED` | `true` | O formulário de feedback |

### Aviso de privacidade

| Definição | Predefinição | Controla |
|---|---|---|
| `FIPM_CONTACT_EMAIL` | `contact@example.org` | Mostrado em `/privacy` |
| `FIPM_HOSTING_ORG` | `the FIP Manager operators` | Mostrado em `/privacy` |

### Email

`FIPM_MAIL_BACKEND` por predefinição é `console` (as mensagens são registadas, não enviadas). Para email real defina-o
para `smtp` e configure `FIPM_MAIL_FROM`, `FIPM_SMTP_HOST`, `FIPM_SMTP_PORT`, `FIPM_SMTP_USER`,
`FIPM_SMTP_PASSWORD`, `FIPM_SMTP_TLS`. Os tempos de vida dos tokens são `FIPM_MAIL_TOKEN_TTL_HOURS` (24) e
`FIPM_RESET_TOKEN_TTL_HOURS` (1).

### Integração e rede

| Definição | Predefinição | Controla |
|---|---|---|
| `FIPM_FIODMP_BASE_URL` | `https://fiodmp.fiocruz.br` | Ligação DMP |
| `FIPM_EMBED_ALLOWED_ORIGINS` | `https://fiodmp.fiocruz.br` | `frame-ancestors` para a vista embutida |
| `FIPM_NETWORK_ENABLED` | `true` | Pontos de acesso da rede de nanopublicações |
| `FIPM_NANOPUB_QUERY_URL` | `https://query.knowledgepixels.com` | Serviço de consulta da rede |
| `FIPM_NETWORK_TIMEOUT_SECONDS` | `10.0` | Timeout por pedido |
| `FIPM_NETWORK_CACHE_TTL_SECONDS` | `900` | Cache de resposta |
| `FIPM_NETWORK_MAX_RESPONSE_BYTES` | 8 MiB | Limite de resposta upstream |

### Painel

O painel tem um grande número de definições de ajustamento; as que valem a pena conhecer são:

| Definição | Predefinição | Controla |
|---|---|---|
| `FIPM_DASHBOARD_ENABLED` | `true` | Desativa o painel todo |
| `FIPM_DASHBOARD_MIN_POPULATION` | `5` | Limiar de k-anonimato — as contagens são ocultadas abaixo deste quando a população contém FIPs que o visualizador pode não abrir |
| `FIPM_DASHBOARD_DEFAULT_WEIGHTING` | `principle` | Ponderação de semelhança: `principle`, `question` ou `letter` |
| `FIPM_DASHBOARD_CLUSTER_MIN_SIM` | `0.6` | Limiar de semelhança para desenhar uma aresta de agrupamento |
| `FIPM_DASHBOARD_SNAPSHOT_TTL_SECONDS` | `3600` | Quanto tempo uma vista cacheada permanece atual |
| `FIPM_DASHBOARD_CSV_MAX_ROWS` | `100000` | Limite de linhas nas exportações CSV do painel |
| `FIPM_DASHBOARD_BACKFILL_ON_STARTUP` | `true` | Criar a projeção no arranque para instâncias pequenas |

As definições `FIPM_DASHBOARD_LSH_*`, `_POSTING_*` e `_MAX_CELLS` restantes afinam o índice de semelhança
e os limites dos níveis live/instantâneo. Deixe-as como estão a menos que esteja a executar dezenas de
milhares de FIPs; `FIPM_DASHBOARD_LSH_BANDS × FIPM_DASHBOARD_LSH_ROWS` deve ser igual a
`FIPM_DASHBOARD_LSH_K`.

---

## 5. Preparar o questionário (modelos de conhecimento)

O editor de modelos de conhecimento está na sua área de trabalho. Pode:

![O catálogo de modelos de conhecimento](images/knowledge-model-catalogue.png)

- **Bifurcar** um modelo existente — o ponto de partida habitual. Obtém um rascunho editável.
- **Criar do zero**, ou **importar** um modelo exportado noutro local.

Dentro de um rascunho que controla, por pergunta:

- **Texto e ajuda**, em cada idioma, em separadores de idioma (en, pt-PT, pt-BR, es).
- **Tipo de FER** — que tipo de recurso a pergunta pede. É isto que torna uma resposta
  verificável em termos de tipo, pelo que defina-o deliberadamente.
- **FERs sugeridos** — recursos do catálogo oferecidos como opções rápidas (no máximo 16 por pergunta).
- **Frases sugeridas** — formulações de texto livre oferecidas como opções rápidas, para práticas que não
  são um produto nomeado (no máximo 12 por pergunta). Estas nunca entram no catálogo FER.
- **Permitir várias** declarações, e **permitir texto livre** (ambos ativados por predefinição).
- **Declarações compactas** — oculta estado, nota e sucessor atrás de um alternador "Mais". Isto
  é o que mantém o formulário utilizável num telemóvel; deixe-o ativado para modelos de workshop.

Pode reordenar, ocultar, dividir e adicionar perguntas, e o editor valida o modelo e lista
erros antes de publicar.

![Um modelo de conhecimento publicado](images/knowledge-model-read.png)

> **Publicar é de um só sentido.** Uma versão publicada é imutável para que os FIPs preenchidos contra ela
> permaneçam significativos. As correções vão para uma nova versão, com uma entrada no registo de alterações.
> Planeie publicar *antes* do evento, não durante.

Ordem das opções como os participantes as veem: opções do catálogo, depois frases sugeridas, depois
**"Outro (especificar)"**. 

---

## 6. Importar questionários por área a partir de um documento

`scripts/import-workshop-docx.py` transforma um documento Word de listas de opções por área num rascunho
de modelo de conhecimento por área:

```sh
uv run --project backend python scripts/import-workshop-docx.py \
    --docx "docs/workshop/PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx" --bump --report -
```

Escreve rascunhos `confoa-2026-<area>-<version>.json` mais um relatório de perguntas em falta e
opções não resolvidas — **leia o relatório**. As opções que nomeiam um recurso do catálogo tornam-se
FERs sugeridos; frases descritivas tornam-se frases sugeridas; as sentinelas "Outros", "Não se
aplica" e "Ainda não definido" são tratadas pela UI em vez de se tornarem opções.

Reexecutar é seguro: um documento alterado produz uma nova versão de rascunho ao lado da antiga,
nunca uma sobregravação. Use `--overwrite-draft` apenas quando pretender deliberadamente substituir
um rascunho não publicado.

> **Os rascunhos não estão ativos até que um humano os publique.** Revise cada um no editor —
> especialmente as opções com incompatibilidade de tipo que o relatório assinala — e depois publique.

---

## 7. Executar uma sessão

**Criar** uma sessão a partir da sua área de trabalho: dê-lhe um título, escolha **uma ou mais** versões
de questionário, opcionalmente rotule cada uma como uma área, e defina um idioma predefinido.

![Criar uma sessão e escolher os seus questionários](images/session-new.png)

A página da sessão é a sua consola durante o exercício:

![A página da sessão com o seu código de acesso e código QR](images/session-detail.png)

- **Código de acesso e QR** — o que os participantes utilizam para entrar. O **modo de projeção** remove os elementos
  da página para que o código e o QR sejam legíveis do fundo de uma sala.
- **Uma lista ao vivo de FIPs** à medida que são criados, sem ser necessário recarregar a página.
- **Exportações** de todos os FIPs na sessão, em conjunto.
- **A matriz de comparação** (veja [§8](#8-comparar-os-resultados)).
- **Fechar** a sessão para impedir que novos participantes se juntem, e **eliminar** quando terminada.

![A lista ao vivo de FIPs numa sessão](images/session-fip-list.png)

![Modo de projeção, com os elementos da página removidos](images/projector-mode.png)

> **O que a eliminação faz.** Eliminar uma sessão propaga-se aos FIPs anónimos criados nela. Os FIPs
> que os participantes reivindicaram para as suas próprias contas são desassociados e sobrevivem.
> Feche uma sessão quando simplesmente pretender que esta pare de aceitar adesões.

Algumas coisas que vale a pena saber antes de a sala encher:

- **Imprima um plano B em papel.** Todos os modelos publicados têm um questionário impresso em
  `/knowledge-models/{id}/{version}/print`, com linhas para preencher. Traga cópias.
- **Os participantes não precisam de contas.** Exigir registo à porta é a forma mais fácil de perder dez minutos de um exercício de trinta minutos.
- **A ligação de participação é `{FIPM_BASE_URL}/join/{joinCode}`.** Se o QR falhar, os participantes podem digitar
  o código na página inicial.

![O questionário em papel impresso](images/questionnaire-print.png)

---

## 8. Comparar os resultados

A **matriz de comparação** em `/sessions/{id}/matrix` é a vista para colocar no projetor quando o
preenchimento pára. Mostra princípio × grupo, atualiza ao vivo à medida que os FIPs mudam, pode ser
filtrada para apenas declarações atuais, e imprime. A convergência por princípio mostra onde a sala
concordou e onde não — o que normalmente é a parte mais produtiva da discussão.

![A matriz de comparação: princípios por grupo](images/comparison-matrix.png)

Para análise para além de uma sessão, utilize o [painel](#13-o-painel).

---

## 9. O catálogo FER

As respostas nomeiam **FAIR Enabling Resources (FERs)**. O catálogo tem dois níveis:

- **Catálogo do sistema** — global, curado, partilhado entre modelos. Sob `data/`.
- **FERs embutidos** — definidos dentro de um único modelo de conhecimento, para recursos específicos dele.

Quando os participantes escrevem um recurso que não está no catálogo, este torna-se um FER **pendente**.
Na página de administração pode:

- **Promover** um FER pendente para o catálogo do sistema, e
- **Fundir** dois FERs, substituindo cada utilização de um pelo outro — a correção para a mesma coisa
  escrita de três formas diferentes.

> **Curar após o evento, não durante.** Promover é um julgamento sobre se algo é um recurso real, nomeável,
> e fundir reescreve respostas existentes. Nenhum beneficia de ser feito com pressa com uma sala à espera.

---

## 10. Administração de utilizadores

A página de administração (`/admin`, apenas administradores) lista utilizadores com os seus nomes, email,
função, data de criação e quantos FIPs, sessões e modelos são seus, e permite pesquisar.

**Reposição de palavra-passe** emite uma palavra-passe temporária, mostrada **uma vez** — copie-a antes de
fechar a caixa de diálogo. O utilizador é forçado a alterá-la na próxima entrada.

![A página de administração: lista de utilizadores e FERs pendentes](images/admin-page.png)

Nesta página também: promoção/fusão de FERs pendentes, e rascunhos de modelos de conhecimento sem
proprietário (por exemplo, aqueles escritos pelo script de importação), que os administradores podem
editar e publicar.

---

## 11. Exportações e RDF

| Âmbito | Formatos |
|---|---|
| Um FIP | JSON, CSV, Turtle, JSON-LD |
| Uma sessão toda | JSON, CSV, Turtle |
| Um questionário | Turtle, JSON-LD e uma versão em papel impressa |
| Uma vista do painel | CSV |

RDF segue a **ontologia FIP** (`https://w3id.org/fair/fip/terms/`), pelo que as exportações são utilizáveis
por qualquer ferramenta FAIR, não apenas por esta instância. As declarações transportam o seu estado,
para que Planeado e Em uso permaneçam distinguíveis, e `migratedFrom` regista de onde uma resposta
migrada veio.

> **Em falta:** o vocabulário de extensão `https://w3id.org/fipm/ns#` utilizado pela exportação **ainda não está registado**
> no w3id, e a página de termos ainda não foi publicada. As exportações são RDF válido e estáveis
> em forma, mas aquele espaço de nomes ainda não resolve.

As exportações CSV transportam uma proteção contra injeção de fórmulas, pelo que são seguras para
abrir num programa de folha de cálculo.

---

## 12. Mover FIPs para uma nova versão do questionário

Quando publica uma nova versão de um modelo, os FIPs existentes mantêm-se na antiga.
`/fips/{id}/migrate` move um FIP, mostrando um diff de pergunta antiga → nova pergunta com o que foi
mapeado, adicionado e removido, e assinala onde o texto de uma pergunta ou o tipo FER mudaram.
Onde uma pergunta antiga se tornou em várias novas, escolhe como dividir as suas declarações.
As exportações registam `migratedFrom`.

**Os FIPs criados dentro de uma sessão estão fixos** à versão do questionário daquela sessão e não
podem ser migrados para fora dela — o registo do que um evento realmente utilizou permanece íntegro.
A página de migração mostra um aviso em vez de oferecer a mudança. FIPs autónomos, e FIPs que já não
estão associados a uma sessão, migram livremente.

---

## 13. O painel

O painel analisa uma **população** de FIPs — uma sessão, os FIPs públicos desta instância, ou
FIPs ingeridos a partir da rede de nanopublicações — ao longo de cinco vistas:

| Vista | Respostas |
|---|---|
| **Cobertura** | Quais os princípios FAIR que esta população aborda efetivamente |
| **Adoção** | Quais os recursos utilizados, e com que amplitude |
| **Semelhança** | Quais as comunidades que se assemelham umas às outras; agrupamentos e vizinhos |
| **Lacunas** | Quais as perguntas que estão por responder |
| **Evolução** | Como o panorama muda ao longo do tempo |

![A vista de semelhança: agrupamentos e vizinhos](images/dashboard-similarity.png)

Cada vista exporta para CSV e tem uma folha de estilos de impressão.

![A página inicial do painel com o seletor de população](images/dashboard-home.png)

Dois comportamentos para compreender antes de o mostrar a qualquer pessoa:

- **k-anonimato.** Quando uma população é menor que `FIPM_DASHBOARD_MIN_POPULATION` *e*
  contém FIPs que o visualizador pode não abrir individualmente, as contagens são **ocultadas** em vez de
  mostradas. Uma contagem ocultada exibe-se como tal — não exibe como zero. Ver a sua própria
  sessão está deliberadamente isento, para que um facilitador possa sempre ler a sua própria sala
  pequena.
- **Modo degradado.** Se a projeção subjacente estiver desatualizada ou em falta, o painel diz-o
  em vez de mostrar números que não pode sustentar. Instâncias pequenas recalculam no momento;
  as maiores mostram um banner e a idade dos dados.

![A vista de cobertura](images/dashboard-coverage.png)

Mantenha-o atual com `refresh-dashboard`, e reconstrua a projeção com `backfill-declarations`
após uma importação em massa. `check-declarations` verifica que a projeção ainda corresponde aos FIPs.

---

## 14. A rede de nanopublicações

Com `FIPM_NETWORK_ENABLED=true`, `/network` navega e pesquisa comunidades FIP publicadas como
nanopublicações, mapeia qualquer FIP da rede nas questões desta instância (listando as perguntas
que não consegue mapear), e oferece **"Usar como ponto de partida"** para pré-preencher um novo FIP,
importando recursos desconhecidos como FERs do catálogo marcados com a origem `network`. 

Cada FIP também pode ser descarregado como um **zip de nanopublicações não assinadas** — comunidade,
uma por declaração, índice e FIP — no formato do FIP Wizard, com um manifesto do que a publicação
ainda requer.

> **Esta instância não publica para a rede e não detém nenhuma chave.** Assinar requer um ORCID,
> uma chave RSA, uma declaração de chave e `nanopub-py` ou `nanopub-java`. O lado de leitura e o
> lado de preparação para exportação estão completos; o lado de publicação deliberadamente não.

`ingest-network-fips` traz FIPs da rede como linhas sombra apenas de leitura para análise do painel.
São factos ingeridos, nunca buscas ao vivo — o painel nunca chama a rede enquanto renderiza.

---

## 15. Operar a instância

**Faça backup da base de dados.** `scripts/backup-db.sh` faz uma cópia consistente do ficheiro SQLite.
Tudo o que um participante produziu está lá dentro; `data/` contém apenas o conteúdo que autorou.
Execute-o antes de qualquer migração ou importação em massa, e com uma programação assim que
estiver ativo.

**Retenção.** Os FIPs autónomos transportam uma promessa de retenção de doze meses no aviso de
privacidade. Nada a aplica automaticamente — nenhum agendador é fornecido com a ferramenta.
Execute `purge-standalone-fips` mensalmente, ou a promessa em `/privacy` não está a ser cumprida.

**Limite de taxa** protege a entrada, feedback, criação de FIPs autónomos e populações do painel
guardadas. Depende de ver IPs de cliente reais — veja `FIPM_TRUST_PROXY` em
[§3](#3-implementar-uma-instância).

**Capacidade.** Testado de carga com 40 e 80 participantes concorrentes simulados sem erros e p95
abaixo de 10 ms em escritas, com SQLite em modo WAL. Uma sala de conferência não é um problema
de escala; `scripts/load-test.py` volta a executar a verificação.

**Plano B offline.** Toda a stack funciona a partir de um portátil e de um hotspot. Teste isto antes
do evento, com um telemóvel real a juntar-se a um hotspot real — é a contingência mais provável
de ser necessária e menos provável de ter sido tentada.

---

## 16. Referência de linha de comandos

Execute como `uv run python -m fipm <command>` a partir de `backend/`.

| Comando | Argumentos principais | Faz |
|---|---|---|
| `import-data` | `--force` | Carrega modelos de conhecimento e catálogo FER de `data/` para a base de dados. Idempotente; `--force` sobrescreve modelos alterados |
| `create-admin` | `--email`, `--password` | Cria um utilizador como administrador, ou promove um existente |
| `serve` | `--host`, `--port`, `--reload` | Executa o servidor da API |
| `purge-standalone-fips` | `--older-than-days` (365), `--dry-run` | Elimina FIPs autónomos não tocados há N dias. **Sempre execute dry-run primeiro** |
| `backfill-declarations` | `--batch`, `--questionnaire`, `--since`, `--only-stale`, `--dry-run`, `--progress` | Reconstrói a projeção do painel. Idempotente e em lotes |
| `check-declarations` | `--sample`, `--all`, `--fix`, `--json` | Verifica se a projeção corresponde aos FIPs |
| `refresh-dashboard` | `--population`, `--all-saved`, `--views`, `--force`, `--json` | Recalcula instantâneos do painel em cache |
| `ingest-network-fips` | `--limit`, `--community`, `--since`, `--json` | Traz FIPs da rede como linhas sombra apenas de leitura |

---

## 17. Resolução de problemas

| Sintoma | Causa e solução |
|---|---|
| **Recusa iniciar em produção** | Segredos de desenvolvimento ainda no lugar. Defina uma `FIPM_SECRET_KEY` real. |
| **Links de participação ou códigos QR apontam para localhost** | `FIPM_BASE_URL` não está definido ou está errado. Também está incorporado em identificadores de FIP — corrija antes de existirem dados reais. |
| **Os participantes não conseguem iniciar sessão, mas deviam conseguir** | Verifique `FIPM_REGISTRATION_OPEN`, e `FIPM_REQUIRE_EMAIL_VERIFICATION` (que necessita de um backend de email funcional — o predefinido apenas regista). |
| **Nenhum email chega** | `FIPM_MAIL_BACKEND` por predefinição é `console`. Defina-o para `smtp` e configure as definições SMTP. |
| **O limite de taxa bloqueia ou ignora as pessoas erradas** | Os IPs de cliente estão errados. Defina `FIPM_TRUST_PROXY=true` apenas por detrás de um proxy que tenha verificado. |
| **Perguntas ou traduções não aparecem após editar `data/`** | Execute `import-data` (`--force` se o modelo tiver mudado). |
| **O painel mostra um banner de dados desatualizados** | Execute `backfill-declarations`, depois `refresh-dashboard`. |
| **O painel oculta contagens** | k-anonimato. Esperado para populações pequenas que contenham FIPs que o visualizador pode não abrir; não é um erro. |
| **Um FIP não pode ser migrado** | A sua versão do modelo está fixa. |
| **Um recurso aparece três vezes com nomes diferentes** | Funda-os na página de administração. |
| **`/network` está vazio ou desativado** | `FIPM_NETWORK_ENABLED`, ou o serviço de consulta upstream está inacessível. O resto da ferramenta não é afetado. |

---

## Atribuição

Conteúdo do questionário: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna,
Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0. Listas de opções por área adaptadas de "PERFIS DE
IMPLEMENTAÇÃO FAIR 2" (autor a confirmar), utilizadas nos mesmos termos CC BY-SA 4.0.
