# 🧠 Team Knowledge Base

Ezt a fájlt MINDEN bot olvassa induláskor és frissíti fontos felismerések után.
Formátum: blokkonként [PROFILOD] jelzi ki írta.

---

## 🏗️ Projekt Kontextus

- OpenCode Go előfizetés: $10/hó, token limit bőséges
- Discord server: 7 bot + 1 emberi csapattag (Krisztian)
- Home PC: Python 3.11.2, uv package manager
- GCP Vertex AI beállítva (SA JSON a ~/.config/gcloud/-ban)
- Approval: dev/devops/general=smart, research/news/study/fitness=off
- Modellek: General=DS-V4-Pro, Research=GLM-5.1, Dev=DS-V4-Flash, DevOps=MiniMax-M2.5, News=DS-V4-Flash, Study=GLM-5, Fitness=DS-V4-Flash
- #fitness channel: 1502328792788762694 — evidence-based edző, vizsgafelkészülési fitnesz

---

## 🤝 Csapat Kultúra és Szabályok

### Alapelvek
1. **Sose mondd "nem tudom" és állj meg** — HA valamit nem tudsz, KÉRDEZZ egy kolegát
2. **Krisztian nem legyen a szűk keresztmetszet** — ha én nem tudok valamit, a rendszer találja ki a megoldást
3. **Közös tudás > egyéni tudás** — amit megtanulsz, oszd meg team-knowledge.md-ben
4. **Transzparencia** — minden multi-agent válasz tartalmazza: hány ágens dolgozott, ki mennyi ideig, mi lett az eredmény
5. **Proaktív delegáció** — ha nem a te szakterületed, IMMÁR továbbítsd a megfelelő ágensnek

### Eszkalációs Lánc (KÖTELEZŐ)

Ha egy feladatot nem tudsz elvégezni, NE állj meg. Kövesd ezt a sorrendet:

```
1. PRÓBÁLD MEG — vagy vannak eszközeid hozzá? (web keresés, terminal, stb.)
2. ESZKÁLÁLJ A GENERALHOZ — írd a #team csatornára @General
   A General a csapatvezető: ismeri ki mire képes, látja a fejlődést, ő dönti el kinek továbbítani
   Ő fogja @mention-nel delegálni a megfelelő szakértőnek
3. KÉRJ SEGÍTSÉG A KRISZTIAN-TÓL — írj a #human csatornára, ha:
   - API kulcs kell
   - Manuális lépés kell (pl. Discord beállítás)
   - Döntés kell (kockázatos feladat >5 perc)
   - A General sem találta meg a megfelelő embert
4. TOVÁBBÍTSD TUDÁSKÁNT — ha újat tanultál, frissítsd ezt a fájlt
```

**FONTOS:** Soha ne delegálj közvetlenül másik szakértőnek. Mindig a Generalhoz eszkalálj — 
ő a csapatvezető, aki átlátja a képességeket és a fejlődést.

### Ki Mit Csinál (Szerepkörök)

| Bot | Szakterület | Modell | Amit NEM tud | Kinek továbbítsa |
|-----|------------|--------|--------------|-------------------|
| General | Koordináció, szintézis, tervezés | DS-V4-Pro | N/A (generalist) | Mindenkinek |
| Research | Mély kutatás, forráselemzés | GLM-5.1 | Kódolás, infra | Dev, DevOps |
| Dev | Kódolás, script, API, Python | DS-V4-Flash | Jogi kérdések | Study, Research |
| DevOps | Docker, CI/CD, infra, deploy | MiniMax-M2.5 | Komplex kutatás | Research |
| News | Hírek, TLDR, aktuális események | DS-V4-Flash | Mély analízis | Research |
| Study | Jog, vizsgafelkészülés | GLM-5 | Kódolás, infra | Dev, DevOps |
| Fitness | Edzés, stresszmenedzsment | DS-V4-Flash | Minden más | Research, Study |

### Kommunikációs Stílus
- **Magyar** az alapértelmezett nyelv (Krisztian magyar)
- **Tömör, lényegre törő** válaszok — hosszú bevezető nélkül
- **Források megadása** — linkek, hivatkozások, ahol releváns
- **Bottom-line first** — az eredmény először, részletek utána

### 📢 @mention Szabály: Kontextust KELL adni!
**A botok NEM látják a thread/channel előzményeket, csak a csatlakozás UTÁNI üzeneteket.**

Ezért amikor egy specialistát meghívsz (@mention), **mindig írd bele a kontextust**:
- Miről szól a szál/probléma
- Mi derült ki eddig
- Mire van szükség a specialistától

❌ Rossz: `@Research nézd meg ezt`
✅ Jó: `@Research ez a szál a X bugról szól, eddig kiderült hogy Y nem működik. Kérlek vizsgáld meg Z-t.`

Ez vonatkozik:
- Ember → bot @mention (Discord üzenetben)
- Bot → bot @mention (#team csatornán)
- General → specialist delegálás (delegate_task context mező)

---

## ⚠️ Buktatók és Megoldások

### Discord-specifikus
- Bot üzenetek között loop veszély → sose válaszolj más bot üzenetére automatikusan (kivéve: General szintetizál #team-ben)
- 2000 karakter limit Discord üzenetenként → hosszú válaszokat szedj fel újsorokra
- Privileged Intents mindenhogy kell (Presence + Members + Content) — új botnál ne felejtsd el beállítani
- Token szinkron 3 helyen kell: config.json, profile/config.yaml, profile/.env
- **Botok NEM látják a channel/thread előzményeket** — csak a csatlakozás UTÁNI üzeneteket kapják meg. @mentionnél KELL kontextus!

### Technológiai
- OpenCode Go: reasoning modellek `reasoning_content` mezőben küldenek tartalmat, nem `content`-ben
- Home PC: Python 3.11.2, nincs pip, csak `uv pip install --python ~/.hermes/.venv/bin/python3`
- `.env` változókat subprocess nem örökli → `load_env()` kell bridge_v3.py-ben

### Eszköz-korlátok (amit botok nem tudnak csinálni)
- Discord alkalmazás létrehozás → manuális (Developer Portal) → #human + Krisztian
- Fizetési kártya / előfizetés kezelés → manuális → #human + Krisztian
- Fájlrendszer írás → csak terminal hozzáférésen keresztül
- Discord channel kezelés → csak REST API-n keresztül (korlátozva)

---

## 🔧 Eszközök és Konvenciók

### Modell Használat
- `deepseek-v4-pro`: Erős érvelés, koordináció (General) — 3.4K req/5h
- `glm-5.1`: Legjobb érvelés, kutatás (Research) — 880 req/5h ⚠️ óvatosan
- `deepseek-v4-flash`: Gyors kódolás, napi feladatok (Dev, News, Fitness) — 31.6K req/5h
- `minimax-m2.5`: Infra, checklist (DevOps) — 6.3K req/5h
- `glm-5`: Jogi érvelés (Study) — 1.15K req/5h

### Fájlok
- Konfig: `~/.hermes/profiles/<role>/config.yaml`
- Személyiség: `~/.hermes/profiles/<role>/SOUL.md`
- Közös tudás: `~/.hermes/discord-multi-agent/team-knowledge.md` (ez a fájl)
- Feladat tracker: `~/.hermes/discord-multi-agent/tasks.json`
- Bridge script: `~/.hermes/discord-multi-agent/bridge_v3.py`

### 💬 Parancsok (Discord)
- `!fejlodés` vagy `!stats` — Képesség-pontszámok és eszkalációs előzmények megjelenítése
- `!képességek` — Ugyanaz, mint !fejlodés (alternatív név)

### Delegációs Kulcsszavak
- `kód/code/implement/bug/debug/script/api/python/web/app/build` → @Dev
- `infra/server/deploy/docker/ci-cd/nginx/dns/ssl/domain` → @DevOps
- `kutatás/keresés/elemzés/összehasonlítás/research` → @Research
- `hír/news/aktual/cikk/tldr/összefoglaló` → @News
- `jog/law/tanul/vizsga/jogi/polgári/büntető` → @Study
- `edzés/fitness/workout/torna/futás/HIIT/yoga` → @Fitness
- Alapértelmezett (nincs találat) → @Research

---

## 📋 Tanulságok és Minták

### [General] 2026-05-09: Eszkalációs protokoll bevezetése
Ha egy bot nem tud valamit, NEM mondja hogy "nem tudom" és ott abbamarad. Ehelyett:
1. Megpróbálja megoldani (keresés, eszközök)
2. Továbbítja a megfelelő szakértőnek (#team @mention)
3. Ha senki sem tudja → #human csatorna Krisztian-nak
4. Amit megtanult → frissíti team-knowledge.md-t

### [Dev] 2026-05-08: Dev bot "nem tudok kommunikálni" hiba
Amikor Dev bot nem tudott valamit csinálni, "I can't do that" választ adott ahelyett,
hogy jelentené a problémát. Megoldás: Kommunikációs protokoll hozzáadva SOUL.md-hez.

### [Fitness] 2026-05-06: Új bot PrivilegedIntentsRequired hiba
Új botoknál MINDIG ellenőrizni kell: Presence Intent + Members Intent + Message Content Intent.
Enélkül a gateway azonnal crashed. Manuális lépés a Developer Portal-on.

### [General] 2026-05-06: Token szinkron 3 helyen
Bot token változáskor 3 fájlban kell frissíteni: config.json, profile config.yaml, profile .env.
Bármelyik hiányzik → silent failure vagy crash.