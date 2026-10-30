# Fase 1 — 30 oktober 2026

Deze map staat in .git/info/exclude: ze is alleen lokaal en komt niet op GitHub.

## Wat is er veranderd (in ai_tool/)
1. Verplaatst: scripts/test_core.py -> .revert_backup/2026-10-30_fase1/scripts/test_core.py
2. Hernoemd in data/historical/christeyns/ (data/ staat in .gitignore):
   - "Outbound_Christeyns_002_Converted (3).xml" -> Outbound_Christeyns_002_Converted.xml
   - "Outbound_Christeyns_002_Original (1).xml"  -> Outbound_Christeyns_002_Original.xml
   - "Outbound_Christeyns_003_Converted (1).xml" -> Outbound_Christeyns_003_Converted.xml
3. Nieuw: scripts/__init__.py (leeg)
4. Nieuw: .env (staat in .gitignore)

## Terugzetten
- test_core.py: verplaats het bestand terug naar scripts/
- Hernoemingen: zet de oude namen terug
- __init__.py en .env: verwijderen
