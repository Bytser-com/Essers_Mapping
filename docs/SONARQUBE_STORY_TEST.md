# Acceptatiecontrole SonarQube-integratie

Datum: 19 november 2026. Storystatus: **Testing**; eindcontrole met alle vijf
services na merge van de Version Control-aanvulling staat nog open.

## Bewijs uit Development

De automatische [SonarQube-run op commit cd9a79a](https://github.com/Bytser-com/Essers_Mapping/actions/runs/44544585007)
is geslaagd. Zowel scanner, quality-gatecontrole als rapportupload waren groen.
Het artifact `sonarqube-reports` bevat:

- Frontend: `coverage/lcov.info`.
- Runtime: `target/site/jacoco/jacoco.xml`.
- Mapping_Proposal en Mapping_Converter: `coverage.xml` en pytest-testrapporten.
- `test-results/sonarqube-quality-gate.json`, met `projectStatus.status = OK`.

PR's [#107](https://github.com/Bytser-com/Essers_Mapping/pull/107) en
[#108](https://github.com/Bytser-com/Essers_Mapping/pull/108) zijn gemerged.
De eerdere Cloudflare-fout gaf een falende CI-status en is met de eigen
clientidentificatie verholpen.

## Toetsing van de fitcriteria

| Fitcriterium | Vastgesteld | Nog te controleren |
| --- | --- | --- |
| Automatische gezamenlijke analyse na push/merge op Development, met coverage van alle geïmplementeerde services | De automatische analyse werkt voor vier services. Version_Control was nog uitgesloten; de aanvulling voegt build, bytecode, dependencies, coverage en rapporten toe. | Na merge moet de nieuwe scan alle vijf services bevatten, inclusief Version_Control. |
| Duidelijke CI-status bij fouten en beschikbare rapporten | Scannerfouten blokkeren de job; regressietests controleren API-fouten, timeouts, verkeerde metadata en gatefouten. Alleen onvoldoende nieuwe-codecoverage is adviserend. Het gepubliceerde rapport-artifact en de geslaagde gate zijn gecontroleerd. | Controleer ook het volledige artifact na de aangevulde scan. |
| Gezamenlijke analyse is een gedocumenteerde uitzondering; PR-servicechecks blijven selectief | Gedocumenteerd in de workflow-README. Wijzigingsdetectie wordt getest voor servicewijzigingen, gedeelde wijzigingen en niet-gerelateerde wijzigingen. Bij commit cd9a79a zijn alle vijf zware servicechecks en deployments overgeslagen. | Geen extra wijziging aan selectiviteit nodig voor deze aanvulling. |

Een voorbeeld van selectieve uitvoering is de
[Runtime CI-run](https://github.com/Bytser-com/Essers_Mapping/actions/runs/44544585085):
wijzigingsdetectie en gate geslaagd, servicechecks en deployment overgeslagen.

## Lokaal uitgevoerde controles voor de aanvulling

- Version_Control: **88 tests geslaagd**, geen fouten of overgeslagen tests;
  Maven-build, JaCoCo-rapport en dependency-export geslaagd met Java 21 en
  Maven 3.9.12 op Windows. De Maven-wrapper startte lokaal niet door een ontbrekende
  PowerShell-cmdlet; de geïnstalleerde Maven is rechtstreeks gebruikt.
- Python-pipelinehelpers en Sonar-gatebeleid: **65 tests geslaagd**.
- Node-serviceworkflowselectie: **16 scenario's geslaagd**.
- Alle GitHub-workflows: **actionlint 1.7.12 geslaagd**, met de bestaande
  uitzondering voor de `queue`-property.
- `git diff --check`: geslaagd.

## Eindcontrole vóór Done

- [ ] Aanvulling met Version_Control is gereviewd en gemerged naar Development.
- [ ] De nieuwe automatische SonarQube-run op de mergecommit is geslaagd volgens het gedocumenteerde gatebeleid.
- [ ] SonarQube toont broncode en coverage voor Frontend, Runtime, Version_Control, Mapping_Proposal en Mapping_Converter.
- [ ] Artifact `sonarqube-reports` bevat ook `Version_Control/target/site/jacoco/jacoco.xml` en de Java-testrapporten.
- [ ] Link naar de nieuwe run en het Sonar-project is aan de story toegevoegd.

De bordstatus **Testing** staat los van een deployment naar de Testing-omgeving.
Deze fitcriteria gaan over de CI-integratie op Development; ze vereisen geen
aparte release naar de Git-branch Testing.
