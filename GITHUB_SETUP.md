# ToolCase v3.0 — Aan de slag met GitHub

Dit bestand helpt je om ToolCase aan GitHub te linken.

## Stap 1: Git initialiseren (eenmalig)

Open een terminal in de ToolCase map en voer uit:

```bash
cd D:\ToolCase
git init
git add .
git commit -m "ToolCase v3.0 — 35 tools, self_improve_loop, i18n (EN/NL/DE)"
```

## Stap 2: Repository aanmaken op GitHub

1. Ga naar https://github.com/new
2. Vul een repository naam in (bijv. `ToolCase`)
3. Kies **Public** of **Private** (wat je wilt)
4. **NIET** "Initialize this repository with a README" aanvinken (we hebben er al een)
5. Klik op **Create repository**

## Stap 3: Lokaal koppelen aan GitHub

Na het aanmaken zie je op GitHub een blokje met "…or push an existing repository from the command line".

Kopieer en voer deze commando's uit:

```bash
git remote add origin https://github.com/JOUW_GEBRUIKERSNAAM/ToolCase.git
git branch -M main
git push -u origin main
```

Vervang `JOUW_GEBRUIKERSNAAM` door je echte GitHub gebruikersnaam.

## Stap 4: Verifiëren

```bash
git status
git remote -v
```

Als het goed is zie je:
```
origin  https://github.com/JOUW_GEBRUIKERSNAAM/ToolCase.git (fetch)
origin  https://github.com/JOUW_GEBRUIKERSNAAM/ToolCase.git (push)
```

Daarna kun je `git push` gebruiken om wijzigingen te uploaden.
