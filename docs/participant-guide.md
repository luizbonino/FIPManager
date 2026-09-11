# Filling in a FIP — A Guide for Participants

**FIP Manager** helps a research community write down, precisely and comparably, which
technologies it actually uses to make its data and metadata **F**indable, **A**ccessible,
**I**nteroperable and **R**eusable. The result is a **FAIR Implementation Profile (FIP)**:
21 short questions, one technology choice per question, exportable as JSON, CSV and RDF.

This guide is for the person **filling in** a FIP — at a workshop, or on your own. It assumes
no technical background and no prior knowledge of FAIR beyond the four letters.

> **Nothing to install.** FIP Manager runs in your phone's or laptop's browser. You do not
> need an account to fill in a FIP, and you do not need to finish in one sitting.

> **Your work saves itself.** There is no "submit" button. Every change is stored a moment
> after you make it — watch for the *Saved* indicator. Closing the tab does not lose your work,
> as long as you keep the link (see [§6](#6-coming-back-later-and-on-another-device)).

If you are at the CONFOA workshop and want a single printable page instead of this guide, use
[`workshop/participant-handout.md`](workshop/participant-handout.md), which covers the same
ground in English and pt-PT on one sheet.

---

## Table of contents

1. [What you are describing (key concepts)](#1-what-you-are-describing-key-concepts)
2. [Three ways to start](#2-three-ways-to-start)
3. [The editor at a glance](#3-the-editor-at-a-glance)
4. [Walkthrough: fill in your first FIP](#4-walkthrough-fill-in-your-first-fip)
   - [Step 1 — Choose your area](#step-1--choose-your-area)
   - [Step 2 — Name your community](#step-2--name-your-community)
   - [Step 3 — Read the question](#step-3--read-the-question)
   - [Step 4 — Tick a suggested option](#step-4--tick-a-suggested-option)
   - [Step 5 — Answer in your own words](#step-5--answer-in-your-own-words)
   - [Step 6 — When the question does not apply](#step-6--when-the-question-does-not-apply)
   - [Step 7 — When it is planned rather than in use](#step-7--when-it-is-planned-rather-than-in-use)
   - [Step 8 — Add more than one answer](#step-8--add-more-than-one-answer)
   - [Step 9 — Watch your progress](#step-9--watch-your-progress)
   - [Step 10 — Share your FIP](#step-10--share-your-fip)
5. [The five kinds of answer](#5-the-five-kinds-of-answer)
6. [Coming back later, and on another device](#6-coming-back-later-and-on-another-device)
7. [Creating an account (optional)](#7-creating-an-account-optional)
8. [Choosing your language](#8-choosing-your-language)
9. [Downloading and sharing your FIP](#9-downloading-and-sharing-your-fip)
10. [Troubleshooting](#10-troubleshooting)
11. [Attribution](#11-attribution)

---

## 1. What you are describing (key concepts)

You are not being asked what you *should* do, or what your institution's policy says. You are
being asked what your community **actually uses today** — and, where relevant, what it plans
to use. An honest "we haven't decided yet" is a better answer than an aspirational one.

| Term | What it means for you |
|---|---|
| **FIP** | The whole profile you are filling in — your community's answers to all 21 questions. |
| **FER** (FAIR Enabling Resource) | The specific technology, service or standard you name as an answer — the thing doing the FAIR-enabling work. **DOI** is a FER; so is **Dublin Core**, **OWL**, or **CC BY 4.0**. |
| **Community** | Whose practice you are describing — a research group, a project, a consortium, an institute. You give it a name at the start. |
| **Question** | One of 21, grouped by the four FAIR letters. Each asks for one kind of resource: "which identifiers for your data?", "which licence for your metadata?" |
| **Declaration** | A single answer on a question: *this* resource, with a status, optionally with a note. A question can carry several declarations. |
| **Status** | Whether the resource is in use now, planned, being developed, or due to be replaced. |
| **Area** | A research-domain flavour of the questionnaire (omics, biodiversity, agriculture, public health, nursing…). Each area suggests a short list of options tuned to that field. |

> **Why "one technology per question" matters.** A FIP is useful because it is comparable.
> When fifty communities each name their actual identifier scheme, you can see convergence and
> divergence at a glance — which is impossible with free-form policy prose.

---

## 2. Three ways to start

| You are… | Do this | Account needed? |
|---|---|---|
| At a workshop, with a code or QR on screen | Scan the QR, or open the site and type the **join code** on the home page | No |
| Working on your own, right now | Open the site and choose **Start a FIP** (or go to `/fips/new`), then pick a questionnaire | No |
| Coming back to work you started | Use your **edit link**, or the **FIPs on this device** list on the home page | No |

![The FIP Manager home page on a phone, with the join-code box](images/home-join-code.png)

All three land you in the same editor. An account is never required to fill in a FIP — it only
becomes useful later, if you want all your FIPs gathered in one workspace
([§7](#7-creating-an-account-optional)).

> **Joining a session vs. starting alone.** A *session* is a facilitated group exercise: the
> facilitator sees the FIPs as they are filled in and can export them together. A *standalone*
> FIP belongs only to you. The questions and the editor are identical.

---

## 3. The editor at a glance

The FIP editor has four parts, top to bottom:

![The FIP editor: community header, progress bar and the four FAIR sections](images/editor-overview.png)

- **The community header** — the name of the community you are describing, plus optional detail.
  You can edit this at any time; it is not locked after creation.
- **A progress bar** — how many of the questions carry at least one answer. It is a guide, not
  a requirement: an unanswered question is a legitimate state.
- **Four collapsible sections** — **F**, **A**, **I** and **R**. The **F** section is open when
  you arrive; tap a heading to open or close a section. Work in any order you like.
- **The action row** — sharing, downloading, and (if you are signed in) visibility controls.

Each question inside a section is a card showing the question text, a short **help** text you
can expand, a **Not applicable** toggle, and the answer area.

![A single question card](images/question-card.png)

> **On a phone**, sections and question cards stack vertically and everything is reachable by
> scrolling — there is no separate mobile version to find.

---

## 4. Walkthrough: fill in your first FIP

### Step 1 — Choose your area

If the facilitator offered several area questionnaires, you choose one when you join. Pick the
area closest to your group's work. If none fits, choose **"Outra área"** (other area) — you get
the generic 21-question list with free text available throughout.

The area determines **which options are suggested**, not which questions are asked. All areas
ask the same 21 questions.

![Choosing a research area when joining a session](images/join-area-choice.png)

> **This choice is made once, at join.** If you picked the wrong area, the fastest fix at a
> workshop is to start a new FIP and choose again — ask the facilitator, who can also remove
> the abandoned one.

### Step 2 — Name your community

Give the community a name people would recognise — "Laboratório de Genômica, Fiocruz" rather
than "our group". This name appears in the comparison matrix the room looks at together, and in
every export.

![Naming the community before starting the FIP](images/join-community-name.png)

### Step 3 — Read the question

Each question names one kind of FAIR-enabling resource. If the wording is unfamiliar, expand
the **help** text: it explains what kind of thing is being asked for, and usually gives an
example.

![A question card with its help text expanded](images/question-help.png)

> **If you genuinely do not know**, leave the question empty and move on. Coming back to it
> after seeing the other questions is often easier, and an empty question is honest.

### Step 4 — Tick a suggested option

Most questions show a short list of suggested options. **Ticking one records that your
community uses it today** — that is the entire action, with no further step.

Suggested options come in two kinds, and both are equally valid answers:

- **Catalogue resources** — recognised, named FERs (DOI, ORCID, Dublin Core…). These are the
  ones that compare cleanly across communities.
- **Suggested phrases** — descriptive wordings for practices that are not a named product
  ("apenas texto não estruturado", "conta do repositório"). These record reality where no
  standard resource exists.

If the list does not show what you need, use the catalogue search to look for a resource by
name, or write your own answer — the next step.

![The suggested options list for a question](images/options-list.png)

### Step 5 — Answer in your own words

At the end of the options list is **"Other (specify)"** — shown as *"Outro (especificar)"* in
Portuguese. Tick it to open a text box, type your own wording, then press Enter or tap the add
button. The declaration row also has a **"Use my own wording"** button that switches the resource
picker from catalogue search to free text for that answer.

A free-text answer is **just as valid** as a listed one. Use it for local tools, in-house
systems, and informal practices — these are exactly the things a fixed list cannot anticipate,
and leaving them out would misrepresent your community.

![Answering in your own words with Other (specify)](images/other-specify.png)

### Step 6 — When the question does not apply

Some questions genuinely do not apply to a given community. Toggle **"Not applicable"** (*"Não se
aplica"*) on the question itself. The tool asks you to confirm, because marking a question not
applicable removes any resources already recorded on it. The comment box then asks *why* it does
not apply — one
short line is enough, and it is worth writing, because "not applicable" and "not answered"
mean very different things to anyone reading your FIP later.

> **"Not applicable" is not a skip.** Use it when the question is genuinely irrelevant to your
> community — not when you are unsure, and not when the answer is simply "none yet". For "we
> haven't decided", leave the question empty instead.

### Step 7 — When it is planned rather than in use

Ticking an option records **currently used**. When that is not the right description, tap
**"more"** on the answer to open the full status control:

| Status | Use it when |
|---|---|
| **Currently used** | In use today. This is what ticking an option records. |
| **Planned** | Decided on, not yet in use. |
| **To be developed** | Being built or adopted right now. |
| **To be replaced** | You use it today, but it is on its way out. Name the successor resource too. |
| **No choice yet** | You want to record explicitly that nothing has been decided, rather than leaving the question blank. |

The same "more" panel holds an optional **note** — a sentence of context — and, where your
instance is linked to a data management plan tool, a way to point at the section of a DMP that
evidences this answer.

![The expanded status control showing the five declaration statuses](images/status-control.png)

### Step 8 — Add more than one answer

Many questions accept several answers: two identifier schemes, a current vocabulary and its
planned replacement. Use **"Add a resource"** to record each one separately, with its own status
and note, rather than cramming them into one free-text box. Separate declarations stay
comparable; a sentence listing three things does not.

### Step 9 — Watch your progress

The progress bar counts questions with at least one answer. There is no minimum and no
validation gate — a FIP with twelve honest answers is more useful than one with 21 guesses.

Saving happens on its own, a moment after you stop typing. The indicator reads **"Saved"** with a
time, and **"Unsaved changes"** while a change is still pending.
If you are about to close the laptop, glance at that indicator first.

![The community header and save indicator](images/save-indicator.png)

### Step 10 — Share your FIP

Open the **Share** panel. It gives you two different things:

- **The FIP link** — a permanent, **read-only** URL for your FIP, plus a QR code. Safe to send
  to anyone; they can read but not change it.
- **The edit link** — a URL that **grants editing**. Anyone holding it can change your FIP, so
  share it only inside your group.

Keep the FIP link. It keeps working after the workshop.

![The Share panel with the FIP link, QR code and edit link](images/share-panel.png)

---

## 5. The five kinds of answer

| Answer | How | What it records |
|---|---|---|
| **Tick an option** | Tap a suggested option | Your community uses it today |
| **Search the catalogue** | Search by name in the picker | Same, for a resource not in the suggestions |
| **"Other (specify)"** | Tick it, type, press Enter | Your own wording — equally valid |
| **"Not applicable"** | Toggle on the question, confirm | The question is irrelevant to your community |
| **Leave it empty** | Move on | Not decided yet — an honest answer, not a failure |

---

## 6. Coming back later, and on another device

Your FIP is **not** tied to the device that created it.

- **Same device** — the home page lists **FIPs on this device**. Tap yours to reopen it.
- **Another phone or laptop** — open the **Share** panel, copy the **edit link**, and open that
  link on the other device. That is the supported way to move between a phone and a laptop, or
  to hand the FIP to a colleague who will continue it.
- **Lost the link entirely** — if you filled it in during a facilitated session, the facilitator
  can still see the FIP and recover its link. If it was standalone and the device list is gone,
  it cannot be recovered — which is the strongest reason to create an account
  ([§7](#7-creating-an-account-optional)) or to save the link somewhere.

![The FIPs on this device list on the home page](images/home-device-fips.png)

> **Treat the edit link like a password.** Anyone with it can edit the FIP. The plain FIP link
> is the one to share widely.

> **Standalone FIPs are not kept forever.** An instance may delete standalone FIPs that have not
> been edited for a long time (twelve months on the CONFOA deployment). FIPs claimed into an
> account are not subject to that.

---

## 7. Creating an account (optional)

You never need an account to fill in a FIP. An account gives you:

- **A workspace** listing all your FIPs, sessions and knowledge models in one place.
- **Claiming** — open a FIP you created anonymously and choose **Claim** to move it into your
  workspace permanently, so it no longer depends on a link kept in a browser.
- **Visibility control** — set each FIP to **private**, **link** (anyone with the link may read)
  or **public**.
- **Running your own sessions**, if you later facilitate an exercise yourself.

You can claim a FIP at any time after creating the account — including one you started at a
workshop months earlier, as long as you still hold its edit link.

---

## 8. Choosing your language

The interface is available in **English**, **European Portuguese (pt-PT)**, **Brazilian
Portuguese (pt-BR)** and **Spanish (es)**. Use the language switcher in the header; if your
browser is already set to one of these, the site opens in it automatically. Portuguese variants
fall back to each other before falling back to English, so you always get Portuguese text where
any Portuguese translation exists.

Switching language changes **the interface and the question texts**. It never changes or
translates **your answers** — what you typed stays exactly as you wrote it.

---

## 9. Downloading and sharing your FIP

From the editor or the read-only view you can download your FIP as:

| Format | What it is for |
|---|---|
| **JSON** | Machine-readable, for reloading or processing |
| **CSV** | A spreadsheet — one row per declaration |
| **Turtle** / **JSON-LD** | RDF following the FIP ontology, for semantic-web tooling and publication |

![Export buttons: JSON, CSV, Turtle and JSON-LD](images/export-buttons.png)

The RDF exports are what make your FIP part of the wider FAIR ecosystem rather than a private
spreadsheet. You do not need to understand them to benefit from them.

---

## 10. Troubleshooting

| Symptom | What to do |
|---|---|
| **The join code is not accepted** | Check for confusable characters, and that the session has not been closed. Ask the facilitator to re-read the code from their screen. |
| **The QR code will not scan** | Type the join code on the home page instead — it is the same thing. |
| **I don't see the "Saved" indicator** | It appears a moment after you stop typing. If it never appears, check your connection; your text stays in the page until it saves. |
| **My option isn't in the list** | Search the catalogue by name, or use **"Outro (especificar)"** and write it yourself. |
| **I ticked the wrong option** | Tap it again to untick, or remove the declaration from the answer row. |
| **I can't edit — everything is read-only** | You are on the plain FIP link, not the edit link. Get the edit link from whoever started the FIP. |
| **I chose the wrong area** | Ask the facilitator. The area is fixed at join; starting again is usually quicker than reworking. |
| **I lost my FIP** | Check **FIPs on this device** on the home page. In a session, the facilitator can find it. |

---

## 11. Attribution

Questionnaire content: FIP mini-questionnaire v2.0.0 © 2023 Erik Schultes, Barbara Magagna,
Jacintha Schultes / GO FAIR Foundation, CC BY-SA 4.0. Area pick-lists adapted from "PERFIS DE
IMPLEMENTAÇÃO FAIR 2" (author to be confirmed), used under the same CC BY-SA 4.0 terms.
