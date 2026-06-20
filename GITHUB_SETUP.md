# ToolCase v5.1 publiceren op GitHub

De map is voorbereid voor publicatie als `SmokerGreenOG/ToolCase`.

## 1. Eerste commit maken

De lokale repository staat al op branch `main`, de GitHub-remote is ingesteld
en alle publiceerbare bestanden zijn gestaged. Stel eerst je Git-identiteit in
als die nog ontbreekt:

```powershell
git config --global user.name "SmokerGreenOG"
git config --global user.email "JOUW_GITHUB_EMAIL"
git commit -m "release: ToolCase v5.1.0"
```

Controleer eventueel vóór de commit met `git status` dat `.env`, caches,
backups en rapporten niet in de staginglijst staan.

## 2. Lege GitHub-repository maken

Maak op GitHub een lege repository met de naam `ToolCase`. Voeg via GitHub geen
README, licentie of `.gitignore` toe; deze bestanden bestaan lokaal al.

## 3. Uploaden

```powershell
git push -u origin main
```

## 4. Release taggen

```powershell
git tag -a v5.1.0 -m "ToolCase v5.1.0"
git push origin v5.1.0
```

Maak daarna op GitHub een release vanaf tag `v5.1.0` en gebruik de sectie
`5.1.0` uit `CHANGELOG.md` als release notes.

## 5. Lokale verificatie

```powershell
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONDONTWRITEBYTECODE="1"
python improve.py --verify-install
python -m unittest discover -s tests
python config_validator.py --json
python license_checker.py --json
python self_improve_loop.py . --dry-run --json --no-report
```
