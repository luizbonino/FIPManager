# Preencher um FIP — Guia para Participantes

O **Gestor de FIP** ajuda uma comunidade de investigação a registar, de forma precisa e comparável, quais
as tecnologias que utiliza efetivamente para tornar os seus dados e metadados **L**ocalizáveis,
**A**cessíveis, **I**nteroperáveis e **R**eutilizáveis. O resultado é um **Perfil de Implementação FAIR
(FIP)**: 21 perguntas curtas, uma escolha tecnológica por pergunta, exportável como JSON, CSV e RDF.

Este guia é para a pessoa que **preenche** um FIP — num workshop ou por conta própria. Pressupõe
que não tem formação técnica nem conhecimento prévio de FAIR para além das quatro letras.

> **Não é necessário instalar nada.** O Gestor de FIP funciona no navegador do seu telemóvel ou
> portátil. Não precisa de uma conta para preencher um FIP, e não precisa de o concluir de uma vez.

> **O seu trabalho guarda-se automaticamente.** Não existe um botão "enviar". Todas as alterações
> são guardadas um momento após as fazer — observe o indicador *Guardado*. Fechar o separador não
> faz perder o seu trabalho, desde que guarde a ligação (veja [§6](#6-voltar-mais-tarde-e-noutro-dispositivo)).

Se estiver no workshop CONFOA e preferir uma única página impressa em vez deste guia, utilize
o [`workshop/participant-handout.md`](workshop/participant-handout.md), que cobre o mesmo
terreno em Inglês e pt-PT numa só folha.

---

## Índice

1. [O que está a descrever (conceitos-chave)](#1-o-que-está-a-descrever-conceitos-chave)
2. [Três formas de começar](#2-três-formas-de-começar)
3. [O editor à primeira vista](#3-o-editor-à-primeira-vista)
4. [Guia passo a passo: preencher o seu primeiro FIP](#4-guia-passo-a-passo-preencher-o-seu-primeiro-fip)
   - [Passo 1 — Escolher a sua área](#passo-1--escolher-a-sua-área)
   - [Passo 2 — Dar nome à sua comunidade](#passo-2--dar-nome-à-sua-comunidade)
   - [Passo 3 — Ler a pergunta](#passo-3--ler-a-pergunta)
   - [Passo 4 — Selecionar uma opção sugerida](#passo-4--selecionar-uma-opção-sugerida)
   - [Passo 5 — Responder com as suas próprias palavras](#passo-5--responder-com-as-suas-próprias-palavras)
   - [Passo 6 — Quando a pergunta não se aplica](#passo-6--quando-a-pergunta-não-se-aplica)
   - [Passo 7 — Quando está planeado em vez de em uso](#passo-7--quando-está-planeado-em-vez-de-em-uso)
   - [Passo 8 — Adicionar mais do que uma resposta](#passo-8--adicionar-mais-do-que-uma-resposta)
   - [Passo 9 — Acompanhar o seu progresso](#passo-9--acompanhar-o-seu-progresso)
   - [Passo 10 — Partilhar o seu FIP](#passo-10--partilhar-o-seu-fip)
5. [Os cinco tipos de resposta](#5-os-cinco-tipos-de-resposta)
6. [Voltar mais tarde e noutro dispositivo](#6-voltar-mais-tarde-e-noutro-dispositivo)
7. [Criar uma conta (opcional)](#7-criar-uma-conta-opcional)
8. [Escolher o seu idioma](#8-escolher-o-seu-idioma)
9. [Transferir e partilhar o seu FIP](#9-transferir-e-partilhar-o-seu-fip)
10. [Resolução de problemas](#10-resolução-de-problemas)
11. [Atribuição](#11-atribuição)

---

## 1. O que está a descrever (conceitos-chave)

Não está a ser questionado sobre o que **deveria** fazer, ou sobre o que diz a política da sua
instituição. Está a ser questionado sobre o que a sua comunidade **utiliza efetivamente hoje** — e,
quando relevante, o que planeia utilizar. Um "ainda não decidimos" honesto é uma resposta melhor
do que uma aspiracional.

| Termo | O que significa para si |
|---|---|
| **FIP** | Todo o perfil que está a preencher — as respostas da sua comunidade a todas as 21 perguntas. |
| **FER** (FAIR Enabling Resource) | A tecnologia, serviço ou norma específica que indica como resposta — a coisa que realiza o trabalho de tornar FAIR. **DOI** é um FER; **Dublin Core**, **OWL** ou **CC BY 4.0** também são. |
| **Comunidade** | De quem está a descrever as práticas — um grupo de investigação, um projeto, um consórcio, um instituto. Dá-lhe um nome no início. |
| **Pergunta** | Uma de 21, agrupadas pelas quatro letras FAIR. Cada uma pede um tipo de recurso: "que identificadores para os seus dados?", "que licença para os seus metadados?" |
| **Declaração** | Uma única resposta a uma pergunta: *este* recurso, com um estado, opcionalmente com uma nota. Uma pergunta pode ter várias declarações. |
| **Estado** | Se o recurso está em uso agora, planeado, a ser desenvolvido, ou a ser substituído. |
| **Área** | Um sabor específico de um domínio de investigação do questionário (ómicas, biodiversidade, agricultura, saúde pública, enfermagem…). Cada área sugere uma lista curta de opções ajustadas a esse domínio. |

> **Porque é que "uma tecnologia por pergunta" é importante.** Um FIP é útil porque é comparável.
> Quando cinquenta comunidades indicam os seus esquemas de identificadores reais, é possível ver
> convergências e divergências de relance — o que é impossível com uma prosa de política livre.

---

## 2. Três formas de começar

| Está… | Faça isto | Conta necessária? |
|---|---|---|
| Numa sessão de workshop, com um código ou QR no ecrã | Digitalize o QR, ou abra o site e introduza o **Código de Acesso** na página inicial | Não |
| A trabalhar por conta própria, agora | Abra o site e escolha **Começar um FIP** (ou vá a `/fips/new`), depois selecione um questionário | Não |
| A regressar a um trabalho que começou | Use a sua **Ligação de edição**, ou a lista **FIPs neste dispositivo** na página inicial | Não |

![A página inicial do Gestor de FIP num telemóvel, com a caixa de código de acesso](images/home-join-code.png)

As três opções levam-no ao mesmo editor. Uma conta nunca é necessária para preencher um FIP —
só se torna útil mais tarde, se quiser ter todos os seus FIPs reunidos num só espaço de trabalho
([§7](#7-criar-uma-conta-opcional)).

> **Participar numa sessão vs. começar sozinho.** Uma *sessão* é um exercício de grupo facilitado:
> o facilitador vê os FIPs à medida que são preenchidos e pode exportá-los em conjunto. Um FIP
> *independente* pertence apenas a si. As perguntas e o editor são idênticos.

---

## 3. O editor à primeira vista

O editor de FIP tem quatro partes, de cima para baixo:

![O editor de FIP: cabeçalho da comunidade, barra de progresso e as quatro secções FAIR](images/editor-overview.png)

- **O cabeçalho da comunidade** — o nome da comunidade que está a descrever, mais detalhes opcionais.
  Pode editar isto a qualquer momento; não fica bloqueado após a criação.
- **Uma barra de progresso** — quantas das perguntas têm pelo menos uma resposta. É um guia, não
  um requisito: uma pergunta sem resposta é um estado legítimo.
- **Quatro secções recolhíveis** — **L**, **A**, **I** e **R**. A secção **L** está aberta quando
  chega; toque num cabeçalho para abrir ou fechar uma secção. Trabalhe pela ordem que preferir.
- **A linha de ações** — partilha, transferência, e (se tiver sessão iniciada) controlos de visibilidade.

Cada pergunta dentro de uma secção é um cartão que mostra o texto da pergunta, um texto de **ajuda**
curto que pode expandir, um interruptor **Não se aplica**, e a área de resposta.

![Um cartão de pergunta individual](images/question-card.png)

> **Num telemóvel**, as secções e os cartões de perguntas empilham-se verticalmente e tudo é acessível
> por deslocamento — não existe uma versão móvel separada.

---

## 4. Guia passo a passo: preencher o seu primeiro FIP

### Passo 1 — Escolher a sua área

Se o facilitador ofereceu vários questionários de área, escolhe um quando se junta. Escolha a
área mais próxima do trabalho do seu grupo. Se nenhuma se adequar, escolha **"Outra área"** —
obtém a lista genérica de 21 perguntas com texto livre disponível em todo o lado.

A área determina **quais as opções sugeridas**, não quais as perguntas feitas. Todas as áreas
fazem as mesmas 21 perguntas.

![Escolher uma área de investigação ao juntar-se a uma sessão](images/join-area-choice.png)

> **Esta escolha é feita uma vez, ao juntar-se.** Se escolheu a área errada, a correção mais rápida
> num workshop é começar um novo FIP e escolher novamente — peça ao facilitador, que também pode
> remover o que foi abandonado.

### Passo 2 — Dar nome à sua comunidade

Dê à comunidade um nome que as pessoas reconheceriam — "Laboratório de Genómica, Fiocruz" em vez
de "o nosso grupo". Este nome aparece na matriz de comparação que a sala observa em conjunto, e em
todas as exportações.

![Dar nome à comunidade antes de começar o FIP](images/join-community-name.png)

### Passo 3 — Ler a pergunta

Cada pergunta nomeia um tipo de recurso que possibilita FAIR. Se a formulação não for familiar,
expanda o texto de **ajuda**: explica que tipo de coisa está a ser pedida, e normalmente dá um
exemplo.

![Um cartão de pergunta com o texto de ajuda expandido](images/question-help.png)

> **Se realmente não souber**, deixe a pergunta em branco e avance. Voltar a ela
> após ver as outras perguntas muitas vezes é mais fácil, e uma pergunta em branco é honesta.

### Passo 4 — Selecionar uma opção sugerida

A maioria das perguntas mostra uma lista curta de opções sugeridas. **Selecionar uma opção regista
que a sua comunidade a utiliza hoje** — essa é toda a ação, sem mais passos.

As opções sugeridas vêm em dois tipos, e ambos são respostas igualmente válidas:

- **Recursos de catálogo** — FERs reconhecidos e nomeados (DOI, ORCID, Dublin Core…). Estes são
  os que se comparam facilmente entre comunidades.
- **Frases sugeridas** — formulações descritivas para práticas que não são um produto nomeado
  ("apenas texto não estruturado", "conta do repositório"). Estas registam a realidade quando não
  existe um recurso padrão.

Se a lista não mostrar o que precisa, use a pesquisa do catálogo para procurar um recurso por
nome, ou escreva a sua própria resposta — o próximo passo.

![A lista de opções sugeridas para uma pergunta](images/options-list.png)

### Passo 5 — Responder com as suas próprias palavras

No final da lista de opções está **"Outro (especificar)"**. Selecione-o para abrir uma caixa de texto, digite a sua própria formulação, depois prima
Enter ou toque no botão de adição. A linha da declaração também tem um botão **"Usar as minhas próprias
palavras"** que comuta o seletor de recurso da pesquisa no catálogo para texto livre para essa resposta.

Uma resposta de texto livre é **tão válida** como uma listada. Use-a para ferramentas locais,
sistemas internos, e práticas informais — estas são exatamente as coisas que uma lista fixa não
consegue antecipar, e omiti-las poderia não representar a sua comunidade.

![Responder com as suas próprias palavras com Outro (especificar)](images/other-specify.png)

### Passo 6 — Quando a pergunta não se aplica

Algumas perguntas realmente não se aplicam a uma determinada comunidade. Ative **"Não se aplica"**
na própria pergunta. A ferramenta pede-lhe que confirme, porque marcar uma pergunta como não
aplicável remove todos os recursos já registados nela. A caixa de comentário pergunta então *porque é
que* não se aplica —
uma linha curta é suficiente, e vale a pena escrever, porque "não se aplica" e "sem resposta"
têm significados muito diferentes para qualquer pessoa que ler o seu FIP mais tarde.

> **"Não se aplica" não é uma opção para saltar.** Use-a quando a pergunta for verdadeiramente
> irrelevante para a sua comunidade — não quando não tiver a certeza, e não quando a resposta for
> simplesmente "ainda não". Para "ainda não decidimos", deixe a pergunta em branco.

### Passo 7 — Quando está planeado em vez de em uso

Selecionar uma opção regista **Em uso**. Quando essa não for a descrição correta, toque
**"mais"** na resposta para abrir o controlo de estado completo:

| Estado | Use-o quando |
|---|---|
| **Em uso** | Em uso hoje. Isto é o que selecionar uma opção regista. |
| **Planeado** | Decidido, mas ainda não em uso. |
| **Em desenvolvimento (planeado)** | A ser construído ou adotado agora. |
| **Substituição planeada** | Utiliza-o hoje, mas está a ser eliminado. Indique também o recurso substituto. |
| **Nenhum** | Quer registar explicitamente que nada foi decidido, em vez de deixar a pergunta em branco. |

O mesmo painel "mais" contém uma **nota** opcional — uma frase de contexto — e, quando a sua
instância está ligada a uma ferramenta de planos de gestão de dados, uma forma de apontar para a
secção de um DMP que fundamenta esta resposta.

![O controlo de estado expandido que mostra os cinco estados de declaração](images/status-control.png)

### Passo 8 — Adicionar mais do que uma resposta

Muitas perguntas aceitam várias respostas: dois esquemas de identificadores, um vocabulário atual
e o seu substituto planeado. Use **"Adicionar um recurso"** para registar cada um separadamente,
com o seu próprio estado e nota, em vez de os forçar numa única caixa de texto livre. Declarações
separadas mantêm-se comparáveis; uma frase que lista três coisas não.

### Passo 9 — Acompanhar o seu progresso

A barra de progresso conta as perguntas com pelo menos uma resposta. Não há mínimo nem porta
de validação — um FIP com doze respostas honestas é mais útil do que um com 21 palpites.

Guardar acontece automaticamente, um momento após parar de digitar. O indicador diz **"Guardado"**
com uma hora, e **"Alterações não guardadas"** enquanto uma alteração ainda estiver pendente.
Se estiver prestes a fechar o portátil, olhe para esse indicador primeiro.

![O cabeçalho da comunidade e o indicador de guardar](images/save-indicator.png)

### Passo 10 — Partilhar o seu FIP

Abra o painel **Partilhar**. Este fornece-lhe duas coisas diferentes:

- **A ligação do FIP** — um URL permanente, **apenas de leitura** para o seu FIP, mais um código QR.
  Seguro para enviar a qualquer pessoa; podem ler, mas não alterar.
- **A Ligação de edição** — um URL que **permite editar**. Qualquer pessoa que o detiver pode
  alterar o seu FIP, por isso partilhe-o apenas dentro do seu grupo.

Guarde a ligação do FIP. Esta continua a funcionar após o workshop.

![O painel Partilhar com a ligação do FIP, código QR e Ligação de edição](images/share-panel.png)

---

## 5. Os cinco tipos de resposta

| Resposta | Como | O que regista |
|---|---|---|
| **Selecionar uma opção** | Toque numa opção sugerida | A sua comunidade a utiliza hoje |
| **Pesquisar no catálogo** | Pesquise por nome no seletor | O mesmo, para um recurso não nas sugestões |
| **"Outro (especificar)"** | Selecione-o, digite, prima Enter | A sua própria formulação — igualmente válida |
| **"Não se aplica"** | Ative na pergunta, confirme | A pergunta é irrelevante para a sua comunidade |
| **Deixar em branco** | Avançar | Ainda não decidido — uma resposta honesta, não uma falha |

---

## 6. Voltar mais tarde e noutro dispositivo

O seu FIP **não** está ligado ao dispositivo que o criou.

- **Mesmo dispositivo** — a página inicial lista **FIPs neste dispositivo**. Toque no seu para o reabrir.
- **Outro telemóvel ou portátil** — abra o painel **Partilhar**, copie a **Ligação de edição**, e abra
  essa ligação no outro dispositivo. Esta é a forma suportada de passar de um telemóvel para um
  portátil, ou de entregar o FIP a um colega que o continuará.
- **Perdeu a ligação completamente** — se a preencheu durante uma sessão facilitada, o facilitador
  ainda pode ver o FIP e recuperar a sua ligação. Se era um FIP independente e a lista do dispositivo
  desapareceu, não pode ser recuperado — o que é a razão mais forte para criar uma conta
  ([§7](#7-criar-uma-conta-opcional)) ou para guardar a ligação em algum lugar.

![A lista FIPs neste dispositivo na página inicial](images/home-device-fips.png)

> **Trate a Ligação de edição como uma palavra-passe.** Qualquer pessoa com ela pode editar o FIP.
> A ligação simples do FIP é a que deve ser partilhada amplamente.

> **Os FIPs independentes não são guardados para sempre.** Uma instância pode eliminar FIPs
> independentes que não foram editados há muito tempo (doze meses na implementação CONFOA).
> FIPs reivindicados para uma conta não estão sujeitos a isso.

---

## 7. Criar uma conta (opcional)

Nunca precisa de uma conta para preencher um FIP. Uma conta dá-lhe:

- **Uma área de trabalho** que lista todos os seus FIPs, sessões e modelos de conhecimento num só lugar.
- **Reivindicação** — abra um FIP que criou anonimamente e escolha **Guardar este FIP na minha área de trabalho** para o mover permanentemente para a sua área de trabalho, para que já não dependa de uma ligação guardada num navegador.
- **Controlo de visibilidade** — defina cada FIP como **Privado**, **Link** (qualquer pessoa com a ligação pode ler) ou **Público**.
- **Executar as suas próprias sessões**, se mais tarde facilitar um exercício.

Pode reivindicar um FIP a qualquer momento após criar a conta — incluindo um que começou num
workshop meses antes, desde que ainda tenha a Ligação de edição.

---

## 8. Escolher o seu idioma

A interface está disponível em **Inglês**, **Português (Portugal)**, **Português (Brasil)** e
**Espanhol**. Use o seletor de idioma no cabeçalho; se o seu navegador já estiver definido para
um destes, o site abre automaticamente nele. As variantes de Português recuam uma para a outra
antes de recuar para Inglês, por isso sempre obtém texto em Português onde existir qualquer
tradução para Português.

Mudar de idioma altera **a interface e os textos das perguntas**. Nunca altera nem traduz
**as suas respostas** — o que digitou permanece exatamente como escreveu.

---

## 9. Transferir e partilhar o seu FIP

A partir do editor ou da vista apenas de leitura, pode transferir o seu FIP como:

| Formato | Para que serve |
|---|---|
| **JSON** | Legível por máquina, para recarregar ou processar |
| **CSV** | Uma folha de cálculo — uma linha por declaração |
| **Turtle** / **JSON-LD** | RDF segundo a ontologia FIP, para ferramentas de web semântica e publicação |

![Botões de exportação: JSON, CSV, Turtle e JSON-LD](images/export-buttons.png)

As exportações RDF são o que tornam o seu FIP parte do ecossistema FAIR mais amplo em vez de uma
folha de cálculo privada. Não precisa de as perceber para beneficiar delas.

---

## 10. Resolução de problemas

| Problema | O que fazer |
|---|---|
| **O código de acesso não é aceite** | Verifique se há caracteres confusos e se a sessão não foi fechada. Peça ao facilitador para ler o código do ecrã dele novamente. |
| **O código QR não digitaliza** | Introduza o código de acesso na página inicial — é a mesma coisa. |
| **Não vejo o indicador "Guardado"** | Aparece um momento após parar de digitar. Se nunca aparecer, verifique a sua ligação; o seu texto permanece na página até ser guardado. |
| **A minha opção não está na lista** | Pesquise no catálogo por nome, ou use **"Outro (especificar)"** e escreva-a. |
| **Selecionou a opção errada** | Toque nela novamente para desmarcar, ou remova a declaração da linha de resposta. |
| **Não consigo editar — tudo é apenas de leitura** | Está na ligação simples do FIP, não na Ligação de edição. Obtenha a Ligação de edição de quem começou o FIP. |
| **Escolhi a área errada** | Peça ao facilitador. A área é fixada ao juntar-se; começar de novo é normalmente mais rápido do que refazer. |
| **Perdi o meu FIP** | Verifique **FIPs neste dispositivo** na página inicial. Num workshop, o facilitador pode encontrá-lo. |

---

## 11. Atribuição

Conteúdo do questionário: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna,
Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0. Listas de opções de área adaptadas de "PERFIS DE
IMPLEMENTAÇÃO FAIR 2" (autor a confirmar), usadas nos mesmos termos CC BY-SA 4.0.
