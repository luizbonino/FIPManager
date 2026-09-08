# FIP Manager — CONFOA 2026 Workshop Facilitator Script

30 minutes, ~40 participants in groups of 4–6, one phone or laptop per group. One facilitator leads,
one or two co-facilitators circulate to help groups that get stuck. Faro, 6 Oct 2026.

## Pre-workshop checklist (do this the day before, and again the morning of)

- [ ] **Deploy** the tagged build (`v1.0-confoa`) on the chosen domain, HTTPS working (PLAN §7).
- [ ] Sign in as a facilitator account and **create the workshop session** in advance: title
      "CONFOA 2026", questionnaire `gofair-fip-mini` v1.0.0, default language `pt-PT` (venue is Faro;
      switch per-group as needed — English and pt-BR both work from the same join code).
- [ ] Open `/sessions/<id>` and confirm the join code, join URL and QR render correctly in projector mode.
- [ ] **Test joining from an actual phone** on the venue Wi-Fi: join, name a test community, answer one
      question, save, reload, confirm the answer survived.
- [ ] **Print the QR code and join code** (A3, large font) as a backup for a bad projector angle, plus
      one copy per table.
- [ ] **Offline fallback**: a facilitator laptop with the container running locally and a Wi-Fi hotspot
      switched on but idle, ready to switch to in under 2 minutes (PLAN §7).
- [ ] **Printed questionnaire** (the 21 questions, one per line, with space for notes) as the last-resort
      fallback if both venue Wi-Fi and the hotspot fail — one per group.
- [ ] Charge the facilitator laptop; confirm the projector shows the join screen, not a login prompt.

## Timeline

### 0–3 min — Welcome and why FIPs

*Say:* "A FAIR Implementation Profile, or FIP, is how a community writes down — precisely, not
aspirationally — which technologies it actually uses to be Findable, Accessible, Interoperable and
Reusable. Today, in your group, you'll declare a FIP for a community you know: your project, your
repository, your research group. It takes about fifteen minutes, and at the end we'll compare what
everyone in the room chose, side by side, on the screen behind me."

*pt-PT: "Um FAIR Implementation Profile, ou FIP, é a forma como uma comunidade regista — com precisão, não
como aspiração — que tecnologias utiliza de facto para ser Localizável, Acessível, Interoperável e
Reutilizável. Hoje, no vosso grupo, vão declarar um FIP para uma comunidade que conhecem: o vosso
projeto, o vosso repositório, o vosso grupo de investigação. Demora cerca de quinze minutos e, no final,
vamos comparar as escolhas de toda a sala, lado a lado, no ecrã atrás de mim."*

### 3–6 min — How to join

Projector shows the session's join code and QR (already created — see checklist). Each group picks
**one** device (phone is fine) and **one name** for their community.

*Say:* "Scan the QR code, or type the join code into your browser. Pick a name for your community — it
can be playful, it just needs to be yours for the next twenty minutes. Whoever starts the FIP on their
phone is the only device that can edit it, so pick one phone per table now."

*pt-PT: "Digitalizem o código QR, ou introduzam o código de acesso no navegador. Escolham um nome para a
vossa comunidade — pode ser divertido, só precisa de ser vosso durante os próximos vinte minutos. Quem
iniciar o FIP no telemóvel é o único dispositivo que o pode editar, por isso escolham já um telemóvel por
mesa."*

Confirm on the projector (session detail page, live list) that FIPs are appearing as groups join.

### 6–20 min — Answering the questionnaire

21 questions in four sections: **F**indable (6), **A**ccessible (5), **I**nteroperable (6), **R**eusable
(4). Most questions repeat once for metadata and once for the data itself.

**If time is short, prioritise these five in order** — they give one FER per FAIR letter and are enough
for a meaningful comparison even if a group never finishes: **F1** (identifiers), **F2** (metadata
schema), **A1.1** (access protocol), **I1** (knowledge representation language), **R1.1** (licence).
Say this once, plainly, at minute 6.

*Say:* "You won't finish all 21 — that's fine. If you're short on time, do F1, F2, A1.1, I1 and R1.1
first: one from each letter of FAIR. Everything else is a bonus."

*pt-PT: "Não vão terminar as 21 — não faz mal. Se estiverem com pouco tempo, façam primeiro F1, F2, A1.1,
I1 e R1.1: uma por cada letra de FAIR. O resto é um bónus."*

**Using the tool, in plain words:**
- For each question, either **pick a resource from the list** (start typing to filter it — e.g. "DOI",
  "ORCID", "Dublin Core") **or** tap "use my own wording" and type what your community actually uses.
  Neither is more correct; free text is completely normal, especially for local or informal tools.
- Then choose one of five statuses: **Currently used** (we do this today), **Planned** (we intend to
  start), **To be developed** (the resource itself doesn't exist yet and someone has to build it), **To
  be replaced** (we use it now but plan to move away — if you pick this, add a second entry for what
  replaces it), and **No choice yet** (an honest answer, not a skip — it means "we haven't decided", and
  it still counts as answered).
- Saving is automatic — there's no save button. A small indicator at the top shows "Saved" a couple of
  seconds after you stop typing.
- Encourage groups to write a short **note** when a choice needs explaining ("why Zenodo and not our own
  repository") — that note travels with the answer into every export.

Circulate. Co-facilitators watch for groups stuck on wording (redirect them to free text — there is no
wrong answer) and for the "second device is read-only" surprise (only the phone that started the FIP can
edit it; a teammate opening the same link on their own phone will see a read-only view, which is by
design — one edit token per FIP, no conflict merging).

### 20–27 min — Comparison matrix on the projector

Open the session's comparison matrix (principle × group). Walk the room through it live.

*Say:* "Let's look at the room together. Three questions as we scan this: Where did most groups converge
— the same protocol, the same identifier scheme? Where did we diverge, and does that divergence reflect
a real difference between our communities, or just habit? And which cells are still empty across most
groups — is that a gap worth naming out loud?"

*pt-PT: "Vamos olhar juntos para a sala. Três perguntas enquanto percorremos isto: Onde é que a maioria
dos grupos convergiu — o mesmo protocolo, o mesmo esquema de identificadores? Onde divergimos, e será que
essa divergência reflete uma diferença real entre as nossas comunidades, ou apenas um hábito? E que
células continuam vazias na maioria dos grupos — será um vazio que vale a pena nomear em voz alta?"*

Invite two or three groups to comment on a choice the room finds surprising or a status of "to be
replaced" — that's usually the most interesting part of the room's picture.

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

Share: the session's export-all link (facilitator downloads JSON + CSV for the whole room right after),
and the feedback form/paper.

## Contingency notes

- **Room Wi-Fi fails**: switch to the facilitator laptop's local container + hotspot (already running,
  see checklist). Announce the new join code/QR on the projector; groups that already have a FIP open
  keep their edit token but need the new network to save — ask them to reconnect and confirm "Saved"
  reappears. If the hotspot also fails, hand out the printed questionnaire and collect it on paper; enter
  answers into the tool later.
- **A group loses edit rights** (private browsing, cleared storage, wrong device): they'll see a
  read-only view with no edit controls. The facilitator (session owner) can still write any FIP in an
  open session from the facilitator account — ask the group for their community name, find their FIP in
  the session list, and continue editing from there, or open it and read the answers back to the group
  to re-enter on a fresh device.
- **A group finishes early**: invite them to answer the metadata *and* data variant of a question they
  only did once, add notes explaining a "to be replaced" choice, or browse another group's FIP by URL
  (read-only, shared in the room) and compare notes informally before minute 20.

## Attribution (state once, e.g. on the closing slide or handout)

"FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna, Jacintha Schultes / GO FAIR
Foundation, CC BY-SA 4.0." (data/knowledge-models/LICENSE). The tool itself is MIT-licensed; exported FIP
answers default to CC0 1.0.
