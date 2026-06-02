# 🧠 Team Knowledge Base v4

Ezt a fájlt MINDEN bot olvassa induláskor és frissít fontos felismerések után.
Formátum: blokkonként [PROFILOD] jelzi ki írta.

---

## 🏗️ Projekt Kontextus

- 4-ágenses rendszer: General (coordinator), Dev, Research, Study
- Telegram: KIZÁRÓLAG General profil (allowed_chats: 717405081)
- Discord: Minden ágens saját bottal, külön csatornákon
- Modellek: General=GLM-5.1, Dev=big-pickle, Research=GLM-5.1, Study=big-pickle
- Provider: OpenCode Go ART (GLM-5.1, MiniMax), OpenCode Zen ART (big-pickle)
- Marveen Message Bus: inter-ágens kommunikáció SQLite WAL-mode
- Hermes Mnemosyne: megosztott memória (sqlite-vec + FTS5)
- Home PC: Python 3.11.2, uv package manager, Hermes Agent vLatest
- Approval: dev/devops/general=smart, research/study=off

---

## 🤝 Csapat Kultúra és Szabályok

### Alapelvek
1. **Sose mondd "nem tudom" és állj meg** — HA valamit nem tudsz, KÉRDEZZ egy kolegát
2. **Krisztian nem legyen a szűk keresztmetszet** — a rendszer találja ki a megoldást
3. **Közös tudás > egyéni tudás** — amit megtanulsz, oszd meg team-knowledge.md-ben
4. **Transzparencia** — minden multi-agent válasz tartalmazza ki dolgozott, mennyi ideig, mi lett az eredmény
5. **Proaktív delegáció** — ha nem a te szakterületed, IMMÁR továbbítsd a megfelelő ágensnek

### Eszkalációs Lánc (KÖTELEZŐ)

```
1. PRÓBÁLD MEG — vannak eszközeid hozzá? (web keresés, terminal, stb.)
2. ESZKÁLÁLJ A GENERALHOZ — agent_send_message(to_agent="general", content="...")
   A General a csapatvezető: ismeri ki mire képes, ő dönti el kinek továbbítani
3. KÉRJ SEGÍTSÉG A KRISZTIAN-TÓL — #human csatorna, ha:
   - API kulcs kell
   - Manuális lépés kell (pl. Discord beállítás)
   - Döntés kell (kockázatos feladat >5 perc)
4. TOVÁBBÍTSD TUDÁSKÁNT — ha újat tanultál, frissítsd team-knowledge.md-t
```

### Ki Mit Csinál (Szerepkörök)

| Ágens | Szakterület | Modell | Amit NEM tud | Kinek továbbítsa |
|-------|------------|--------|--------------|-------------------|
| General | Koordináció, szintézis, tervezés, Telegram | GLM-5.1 | Mély kódolás | Dev, Research, Study |
| Dev | Kódolás, script, API, debug | big-pickle | Jogi kérdések | Study, Research |
| Research | Mély kutatás, forráselemzés | GLM-5.1 | Kódolás, infra | Dev |
| Study | Vizsgafelkészítés, jog, DevOps, fitness | big-pickle | Mély kódolás | Dev, Research |

### Kommunikációs Stílus
- **Magyar** az alapértelmezett nyelv
- **Tömör, lényegre törő** válaszok
- **Források megadása** — linkek, hivatkozások
- **Bottom-line first** — eredmény először, részletek utána

---

## 📬 Marveen Message Bus

### MCP Tool-ok
- `agent_send_message(to_agent, content, priority)` — üzenet küldése
- `agent_read_messages(status, limit, mark_read)` — bejövő üzenetek olvasása
- `agent_mark_done(message_id, result)` — feladat befejezése
- `agent_discover(task, top_k)` — legjobb ágens keresése
- `agent_list_cards()` — regisztrált ágensek listája
- `autonomy_get_levels()` / `autonomy_set_level()` — autonómia szintek
- `marveen_status()` — rendszer státusz

### Állapotciklus
`pending` → `delivered` → `read` → `done` / `failed`

### Prioritás
- 0 = normál
- 1 = magas
- 2 = sürgős

---

## 🧠 Mnemosyne Memory

### Scope-ok
- **Global** (`scope="global"`) — minden ágens olvassa (preferenciák, konvenciók)
- **Session** (`scope="session"`) — beszélgetés-specifikus kontextus

### Knowledge Graph
- Tényhárlok: `(subject, predicate, object)` formátumban
- Keresés: `hermes_triple_query(subject, predicate, object)`

---

## ⚠️ Buktatók és Megoldások

### Discord-specifikus
- Bot üzenetek között loop veszély → sose válaszolj más bot üzenetére automatikusan
- 2000 karakter limit Discord üzenetenként → hosszú válaszokat szedd fel
- Privileged Intents kötelezőek (Presence + Members + Content)
- Token szinkron: config.yaml és .env fájlban is kell legyen

### Telegram-specifikus
- Csak a General profilnak van Telegram hozzáférése
- `allowed_chats: '717405081'` — csak Krisztian privát DM-je
- Reactions letiltva: `reactions: false`

### Technológiai
- OpenCode Go: reasoning modellek `reasoning_content` mezőt használnak
- Home PC: Python 3.11.2, nincs pip, csak `uv pip install`
- `.env` változókat subprocess nem örökli

---

## 🔧 Delegációs Kulcsszavak

- `kód/code/implement/bug/debug/script/api/python` → **Dev**
- `infra/server/deploy/docker/ci-cd/nginx` → **Dev** (via Study devops skill)
- `kutatás/keresés/elemzés/összehasonlítás/research` → **Research**
- `jog/law/tanul/vizsga/jogi/büntető/polgári` → **Study**
- `edzés/fitness/workout/torna/HIIT/yoga` → **Study** (fitness skill)
- Alapértelmezett (nincs találat) → **General**

---

## 📋 Tanulságok és Minták

### [General] 2026-06-02: v4 architektúra
A 4-ágenses rendszer (General/Dev/Research/Study) lecserélte a 7-ágenses rendszert.
A News és DevOps ágensek dekomisszionálva. A Study ágens átvevelte a DevOps és Fitness szerepköröket.
A Fitness ágens külön profil marad (nem fut gateway-ben, csak cronként).

### [General] 2026-06-02: Telegram exkluzivitás
A Telegram hozzáférés KIZÁRÓLAG a General profilnak van.
Minden más ágens csak Discordon keresztül kommunikál.
Ez biztosítja, hogy Krisztian DM-je mindig a koordinátorhoz érkezik.

### [General] 2026-06-02: Marveen MCP natív integráció
A bridge_v3.py és hermes_bus.py lecserélve Hermes-native MCP tool-okra.
A Marveen Message Bus most már MCP server formájában fut,不只 standalone script.
A Hermes Mnemosyne memory MCP szintén natív integráció.