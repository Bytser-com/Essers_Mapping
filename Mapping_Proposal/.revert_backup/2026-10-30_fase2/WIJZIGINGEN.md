# Fase 2 — 30 oktober 2026 (branch Feature/AIToolV2)

Branch Feature/AIToolV2 is aangemaakt vanaf Feature/ProposalOverview.
Kopieën van alle originele bestanden staan in deze map (main.py, README.md, scripts/).

## Nieuw
- scripts/config.py, scripts/errors.py, scripts/models.py, scripts/pipeline.py

## Aangepast
- main.py: alleen nog opdrachtregel; logica verhuisd naar scripts/pipeline.py
- scripts/mapping_validator.py: needs_repair uit main.py hierheen (find_proposals_needing_retry); één gedeelde controle
- scripts/readprompt.py: instellingen via config.py, logging i.p.v. print, duidelijke foutmeldingen
- scripts/excel_generator.py: tekst als tekst opslaan (geen apostrof meer), kolommen niet meer hardgecodeerd, logging
- README.md: structuur en .env-instructies

## Terugzetten
- Alles: originele bestanden uit deze map terugkopiëren en de 4 nieuwe bestanden verwijderen
  (of: git checkout -- ai_tool en de nieuwe bestanden verwijderen, of de branch verwijderen)
