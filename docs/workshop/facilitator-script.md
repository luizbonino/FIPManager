# FIP Manager — CONFOA 2026 Workshop Facilitator Script

30 minutes, ~40 participants in groups of 4–6, one phone or laptop per group. One facilitator leads,
one or two co-facilitators circulate to help groups that get stuck. Faro, 6 Oct 2026.

## Pre-workshop checklist (do this the day before, and again the morning of)

- [ ] **Deploy** the tagged build (`v1.0-confoa`) on the chosen domain, HTTPS working (PLAN §7).
- [ ] **Import the area questionnaires** from the colleague's document: `uv run --project backend python
      scripts/import-workshop-docx.py --docx "docs/workshop/PERFIS DE IMPLEMENTAÇÃO FAIR 2.docx" --bump
      --report -` (docs/specs/08-workshop-picklists.md §4). It writes one draft model per area
      (`confoa-2026-<area>-1.0.0.json`) plus a report of missing questions and unresolved options — read
      the report. Re-run any time the document changes; a changed file gets a new `-1.0.1.json` draft next
      to the old one, never an overwrite.
- [ ] **Review each imported draft in the knowledge-model editor**: check the pt-BR wording, resolve any
      "unresolved option" flagged in the report (fill `ferId` in `data/workshop/option-map.json` and
      re-import, or add it as an inline FER in the editor), and fix the placeholder `en` title if the report
      flagged one.
- [ ] **Publish** each reviewed draft (this promotes its inline FERs into the shared catalogue). As of this
      writing 5 of 11 areas exist: dados ômicos (the demo), biodiversidade, agricultura, saúde pública,
      enfermagem. The other six — ciências sociais, património cultural, astronomia, educação, dados
      ambientais, linguística — have no profile yet; leave them out of the session until they're imported.
- [ ] Sign in as a facilitator account and **create one workshop session** listing every published area
      fork as a labelled questionnaire ref, plus `gofair-fip-mini` v1.0.0 labelled "Outra área / Other" as
      the fallback (see Contingency notes): title "CONFOA 2026", default language `pt-PT` (venue is Faro;
      switch per-group as needed — English and pt-BR both work from the same join code). Short labels, one
      per row: "Dados ômicos", "Biodiversidade", "Agricultura", "Saúde pública", "Enfermagem", "Outra área".
- [ ] Open `/sessions/<id>` and confirm the join code, join URL, QR and the area list render correctly in
      projector mode.
- [ ] **Test joining from an actual phone** on the venue Wi-Fi: join, pick an area, name a test community,
      answer one question, save, reload, confirm the answer survived.
- [ ] **Print the QR code and join code** (A3, large font) as a backup for a bad projector angle, plus
      one copy per table.
- [ ] **Offline fallback**: a facilitator laptop with the container running locally and a Wi-Fi hotspot
      switched on but idle, ready to switch to in under 2 minutes (PLAN §7).
- [ ] **Printed questionnaire** (the 21 questions, one per line, with space for notes) as the last-resort
      fallback if both venue Wi-Fi and the hotspot fail — one per group, one set per available area.
- [ ] Charge the facilitator laptop; confirm the projector shows the join screen, not a login prompt.

## Timeline

### 0–3 min — Welcome and why FIPs

*Say:* "A FAIR Implementation Profile, or FIP, is how a community writes down — precisely, not
aspirationally — which technologies it actually uses to be Findable, Accessible, Interoperable and
Reusable. Today, in your group, you'll declare a FIP for a research area — pick the one closest to your
own work. It takes about fifteen minutes, and at the end we'll compare what everyone in the room chose,
side by side, on the screen behind me."

*pt-PT: "Um FAIR Implementation Profile, ou FIP, é a forma como uma comunidade regista — com precisão, não
como aspiração — que tecnologias utiliza de facto para ser Localizável, Acessível, Interoperável e
Reutilizável. Hoje, no vosso grupo, vão declarar um FIP para uma área de investigação — escolham a que mais
se aproxima do vosso trabalho. Demora cerca de quinze minutos e, no final, vamos comparar as escolhas de
toda a sala, lado a lado, no ecrã atrás de mim."*

### 3–6 min — How to join

Projector shows the session's join code and QR (already created — see checklist). Each group picks
**one** device (phone is fine), **one area**, and **one name** for their community.

*Say:* "Scan the QR code, or type the join code into your browser. First, pick your area from the list —
dados ômicos, biodiversidade, agricultura, saúde pública, enfermagem, or 'outra área' if none of those
fits. Then pick a name for your community — it can be playful, it just needs to be yours for the next
twenty minutes. Start the FIP on one phone per table; the plain link is read-only on other devices, and the
"Edit link" in the Share panel is how you hand it to a teammate if you need to."

*pt-PT: "Digitalizem o código QR, ou introduzam o código de acesso no navegador. Primeiro, escolham a
vossa área na lista — dados ômicos, biodiversidade, agricultura, saúde pública, enfermagem, ou 'outra área'
se nenhuma se aplicar. Depois escolham um nome para a vossa comunidade — pode ser divertido, só precisa de
ser vosso durante os próximos vinte minutos. Quem iniciar o FIP no telemóvel é o único dispositivo que o
pode editar, por isso escolham já um telemóvel por mesa."*

Confirm on the projector (session detail page, live list) that FIPs are appearing as groups join, one per
area.

### 6–20 min — Answering the questionnaire

21 questions in four sections: **F**indable (6), **A**ccessible (5), **I**nteroperable (6), **R**eusable
(4). Most questions repeat once for metadata and once for the data itself. Each area's questionnaire shows
the same 21 questions but with a curated pick-list of options for that field.

**If time is short, prioritise these five in order** — they give one FER per FAIR letter and are enough
for a meaningful comparison even if a group never finishes: **F1** (identifiers), **F2** (metadata
schema), **A1.1** (access protocol), **I1** (knowledge representation language), **R1.1** (licence).
Say this once, plainly, at minute 6.

*Say:* "You won't finish all 21 — that's fine. If you're short on time, do F1, F2, A1.1, I1 and R1.1
first: one from each letter of FAIR. Everything else is a bonus."

*pt-PT: "Não vão terminar as 21 — não faz mal. Se estiverem com pouco tempo, façam primeiro F1, F2, A1.1,
I1 e R1.1: uma por cada letra de FAIR. O resto é um bónus."*

**Using the tool, in plain words:**
- Each question shows a short list of options **for your area**. **Tick** every one your community
  actually uses today — that's it, no extra step. Not on the list? Tick the **"Outro (especificar)"**
  checkbox at the end of the list to open a text box, type what your community uses, then press Enter or
  tap the add button; that's completely normal, especially for local or informal tools.
- Two more choices live on every question: **"Ainda não definido"** if the group hasn't decided (an
  honest answer, not a skip — leave it unticked and move on), and **"Não se aplica"** if the question
  genuinely doesn't apply to this community (a separate toggle on the question, keeps the question
  answered without picking a FER).
- Ticking a box records "currently used" by default. If your choice is only **planned**, **to be
  developed**, **to be replaced**, or you want to add a note, tap **"more"** on that item to open the full
  status control — everything is still there, just tucked away so the checklist stays fast on a phone.
- Saving is automatic — there's no save button. A small indicator at the top shows "Saved" a couple of
  seconds after you stop typing.
- If a group loses its device, they can continue from the **"Edit link"** in the Share panel on any other
  phone or laptop — but never project that link on screen, since anyone who sees it can edit the FIP.

Circulate. Co-facilitators watch for groups stuck on "more" (reassure them it's optional — ticking alone
is a complete, valid answer) and for the "second device is read-only" surprise (the plain FIP link opens a
read-only view on any other phone; only the "Edit link" from the Share panel grants editing, which is by
design — one edit token per FIP, no conflict merging, and two devices editing at once overwrite each other).

**Demo walk-through (on the projector, before groups start):** open the **dados ômicos** FIP live and
answer F1 in front of the room — tick two options, tick **"Outro (especificar)"** once to show the text
box and add a free-text answer, tap "more" on one tick to show the status control, then toggle "Não se
aplica" on a question and off again. That one minute
covers every interaction a group will need.

### 20–27 min — Comparison matrix on the projector

Open the session's comparison matrix (principle × group), now grouped into column blocks by area with a
header row naming each area.

*Say:* "Let's look at the room together. Four questions as we scan this: Where did most groups converge
— the same protocol, the same identifier scheme? Where did we diverge, and does that divergence reflect
a real difference between our communities, or just habit? Which cells are still empty across most
groups — is that a gap worth naming out loud? And look across the area blocks: is there a FER that shows
up in several different areas' columns — biodiversity, health, nursing — even though they picked from
different lists? That convergence, across fields that don't usually talk to each other, is often the most
useful finding of the day."

*pt-PT: "Vamos olhar juntos para a sala. Quatro perguntas enquanto percorremos isto: Onde é que a maioria
dos grupos convergiu — o mesmo protocolo, o mesmo esquema de identificadores? Onde divergimos, e será que
essa divergência reflete uma diferença real entre as nossas comunidades, ou apenas um hábito? Que
células continuam vazias na maioria dos grupos — será um vazio que vale a pena nomear em voz alta? E, a
olhar entre os blocos de área: há algum recurso que apareça em várias áreas diferentes — biodiversidade,
saúde, enfermagem — mesmo tendo escolhido de listas diferentes? Essa convergência, entre campos que
normalmente não conversam entre si, é muitas vezes o achado mais interessante do dia."*

Invite two or three groups to comment on a choice the room finds surprising, a "to be replaced" status
opened via "more", or a cross-area convergence just named — that's usually the most interesting part of
the room's picture.

### 27–30 min — Wrap-up

*Say:* "Your FIP has its own URL — it's in the Share panel of your editor, with a QR code. It stays there
after today. If you'd like to keep working on it, create a free account any time and claim your group's
FIP into your own workspace — the button is right in the editor. You can export your FIP as JSON, CSV or
Turtle right now. And if you have thirty seconds, there's a short feedback form — paper is on the tables
if you'd rather not use a screen again."

*pt-PT: "O vosso FIP tem um URL próprio — está no painel Partilhar do editor, com um código QR. Fica lá
depois de hoje. Se quiserem continuar a trabalhar nele, criem uma conta gratuita a qualquer momento e
reivindiquem o FIP do vosso grupo para o vosso espaço — o botão está mesmo no editor. Podem exportar o
vosso FIP já em JSON, CSV ou Turtle. E, se tiverem trinta segundos, há um pequeno formulário de feedback —
há papel nas mesas se preferirem não usar mais um ecrã."*

Share: the session's export-all link (facilitator downloads JSON + CSV for the whole room right after,
each row carrying its area), and the feedback form/paper.

## Contingency notes

- **Room Wi-Fi fails**: switch to the facilitator laptop's local container + hotspot (already running,
  see checklist). Announce the new join code/QR on the projector; groups that already have a FIP open
  keep their edit token but need the new network to save — ask them to reconnect and confirm "Saved"
  reappears. If the hotspot also fails, hand out the printed questionnaire and collect it on paper; enter
  answers into the tool later.
- **A group loses edit rights** (private browsing, cleared storage, wrong device): they'll see a
  read-only view with no edit controls. If anyone in the group still has the "Edit link", open it on
  another phone and carry on. Otherwise the facilitator (session owner) can still write any FIP in an
  open session from the facilitator account — ask the group for their community name, find their FIP in
  the session list, and continue editing from there, or open it and read the answers back to the group
  to re-enter on a fresh device.
- **A group's area has no profile yet** (one of the six not yet imported): they pick **"Outra área /
  Other"** at join, which uses the generic `gofair-fip-mini` questionnaire already in the session as the
  fallback — same 21 questions, no curated pick-list, free text throughout. Tell them this up front so
  it doesn't read as a bug.
- **The document changed** (colleague sends an updated .docx mid-prep): re-run the importer with
  `--bump`; it never overwrites a published or already-drafted version, it writes a new `-1.0.1.json`
  draft alongside the old one. Review and publish the new draft, then edit the session's questionnaire
  refs to point at it — only possible before any group has joined that area (`PATCH` is blocked with
  `session_has_fips` once a FIP exists), so do this well before doors open.
- **A group finishes early**: invite them to answer the metadata *and* data variant of a question they
  only did once, add notes explaining a "to be replaced" choice, or browse another group's FIP by URL
  (read-only, shared in the room) and compare notes informally before minute 20.

## Attribution (state once, e.g. on the closing slide or handout)

"FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha Schultes / GO FAIR
Foundation, CC BY-SA 4.0." (data/knowledge-models/LICENSE). The area pick-lists are a didactic adaptation
of this questionnaire into "PERFIS DE IMPLEMENTAÇÃO FAIR 2" (author to be confirmed), used under the same
CC BY-SA 4.0 terms. The tool itself is MIT-licensed; exported FIP answers default to CC0 1.0.
