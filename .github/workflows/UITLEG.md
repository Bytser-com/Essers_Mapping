# CI/CD uitleg

## Welke bestanden lees je eerst?

- `frontend-ci.yml`: lint, TypeScript, tests, build, browsertests en dependencycheck.
- `runtime-ci.yml`: bepaalt of Runtime gecontroleerd moet worden en roept Java-CI aan.
- `java-service-ci.yml`: Maven-tests, coverage, dependencycheck en containercontrole.
- `mapping-*-ci.yml`: dezelfde opzet voor de Python-services.
- `service-cd.yml`: publicatie en deployment na een geslaagde CI-run.
- De losse servicebestanden `*-cd.yml`: handmatig een deployment opnieuw proberen.

## CI in drie stappen

1. **changes** vergelijkt de gewijzigde bestanden met de vorige commit of PR-basis.
2. **checks** voert de controles uit wanneer de service of gedeelde CI-code verandert.
3. **quality-gate** controleert of wijzigingsdetectie en de benodigde checks geslaagd zijn.

De eindcheck heeft een vaste naam, zoals `Runtime CI Gate`. Die naam kun je verplicht
maken in de branchregels. Een ongewijzigde service mag de controles overslaan;
een fout bij wijzigingsdetectie mag geen groene eindcheck opleveren.

PR's en pushes gebruiken filters om CI-minuten te besparen, ook op `Testing` en
`main`. Een handmatige CI-run controleert de gekozen service altijd. Als een nieuwe
commit een wachtende deployment inhaalt, weigert CD de oude commit. Start dan de
service-CI handmatig op de nieuwste `Testing`-commit om opnieuw te bouwen en deployen.

`Scripts/detect-service-changes.py` bevat deze Git-logica. De regressietests maken
echte tijdelijke Git-commits om onder meer verplaatste bestanden en snelle
opeenvolgende pushes te controleren.

## Wat doet Java-CI?

1. Java 21 installeren en Maven-dependencies cachen.
2. `mvn clean verify` uitvoeren: compileren, tests draaien en een JAR bouwen.
   Surefire, Failsafe en JaCoCo staan geconfigureerd in `Runtime/pom.xml`.
3. Controleren of het JaCoCo XML-rapport bestaat.
4. Met Maven de daadwerkelijk gekozen dependencyversies exporteren, ook testdependencies.
5. Die lijst met `dependency-inventory.py` omzetten naar het OSV-formaat.
6. OSV laten controleren op bekende kwetsbaarheden.
7. De Docker-image bouwen en het HTTP-healthendpoint controleren; op `main` wordt
   deze image niet opnieuw gebouwd.
8. Rapporten en de JAR bewaren. Alleen geslaagde Testing-CI bewaart ook de geteste
   container voor CD.

Een lang Maven- of pytest-commando bevat vooral opties. `run: >-` vouwt de regels
samen tot één commando. `run: |` voert meerdere shellregels uit. De workflow houdt
tests, coveragecontrole, dependency-export en audit als afzonderlijke stappen zichtbaar.

## Python en SonarQube

De gedeelde action `setup-python-service` controleert eerst of de service bestaat.
Een map met alleen een README wordt zichtbaar uitgesteld. Zodra er Python-code
staat, zijn een manifest (`requirements.txt` of `pyproject.toml`) en `tests/` vereist.
Pytest faalt als er geen tests gevonden worden.

Elke geïmplementeerde service krijgt een eigen virtualenv. CI en SonarQube gebruiken
dezelfde setup, zodat ze dezelfde afhankelijkheden en testtools installeren.
SonarQube draait één gezamenlijke analyse op `Development` en verzamelt daarvoor
opnieuw coverage van alle geïmplementeerde services.

De losse Sonar-scanner kent de Maven-classpath niet automatisch. Daarom kopiëren
we voor Runtime en Version_Control de dependencies (inclusief testdependencies)
naar hun eigen `target/sonar-libraries`. Beide Java-services worden gebouwd en
getest; hun JaCoCo-rapporten worden samen met frontend- en Python-coverage ingelezen.
`sonar-project.properties` verwijst naar die JARs en de gecompileerde productie-
en testklassen. Python wordt als versie 3.12 geanalyseerd, net als in CI.
Het patroon `Mapping_*/coverage.xml` leest bestaande Python-rapporten en verwacht
geen rapport van een service die alleen een README bevat.

Onze teamafspraak is **minstens 70% totale coverage**. Dat is een andere maatstaf
dan de standaard Sonar-gate: die vereist **80% coverage op nieuwe code**.
De workflow neemt de gate over van onze eigen SonarQube Community Build;
het percentage staat niet in YAML. Community Build ondersteunt eigen quality
gates, dus 70% totale coverage kan op de server worden ingesteld. Deze migratie
verandert het bestaande gatebeleid niet.
In GitHub Actions behandelen we alleen een tekort aan coverage op nieuwe code
als waarschuwing. De server-gate kan daardoor rood zijn terwijl deze workflow groen
is. Security-, betrouwbaarheids-, onderhoudbaarheids-, duplicatie- en andere
gatefouten blijven de workflow blokkeren. De 70% totale coverage is een teamdoel;
deze wijziging voegt daarvoor geen automatische grens toe.
Let op: Sonars `Coverage` combineert regels en vertakkingen en kan dus lager zijn
dan alleen `Line coverage`. Bekijk voor onze afspraak de totale `Coverage`.

De server staat op `https://sonar-essers.shystack.com`. Stel in GitHub de variable
`SONAR_HOST_URL` in op die URL en `SONAR_PROJECT_KEY` op de projectkey van deze
server. Vervang secret `SONAR_TOKEN` door een nieuw project-analysetoken van deze
instantie. `SONAR_ORGANIZATION` wordt niet meer gebruikt. De volledige
[instelhandleiding](../../docs/SONARQUBE_SETUP.md) beschrijft ook de eerste scan.
Community Build analyseert alleen de hoofdbranch van het Sonar-project; bij ons
is dat `Development`. PR-analyse wordt niet ondersteund. De gewone service-CI
blijft de controles voor pull requests uitvoeren.

De scan uploadt eerst de analyse zonder zelf op de gate te wachten. Daarna leest
`Scripts/check-sonar-quality-gate.py` het taaknummer uit `.scannerwork/report-task.txt`.
Het script wacht maximaal vijf minuten op die taak en controleert de voorwaarden
van precies die analyse. Gefaalde voorwaarden (inclusief `new_coverage`), ontbrekende resultaten, API-fouten en timeouts geven
exitcode 1. Een fout tijdens het scannen zelf blijft ook blokkeren.
Het JSON-gateresultaat staat in het artifact `sonarqube-reports`, onder
`test-results/sonarqube-quality-gate.json`.
De waarschuwingen en fouten bevatten een link naar de bijbehorende analyse op
SonarQube. De samenvatting van de Actions-run toont die link ook, naast het exacte
gateresultaat en het projectdashboard. Dat dashboard toont altijd de nieuwste
analyse. Als de analysehistoriek niet beschikbaar is, verwijst de analyselink
naar het exacte gateresultaat als JSON; de regels voor slagen of falen blijven gelijk.

De scanner controleert bij de installatie een GPG-handtekening. We bewaren de
geverifieerde scanner in een cache, ook als de analyse vervolgens een rode gate
oplevert. Zonder cache begrenst `Scripts/sonar-gpg.sh` ieder GPG-commando tot
30 seconden (met maximaal 5 seconden om te stoppen), zodat de action bij een
vastlopende keyserver zijn andere keyserver kan proberen. De handtekeningcontrole
blijft verplicht; een mislukte verificatie laat de workflow falen.

## Rapporten en dependencychecks

OSV vergelijkt de dependencyversies met bekende kwetsbaarheden. Een gevonden
kwetsbaarheid of scanfout laat CI falen. Dat is geen bewijs dat de applicatie al
misbruikt wordt; de bevinding moet wel worden opgelost of inhoudelijk onderzocht.
Base images en OS-pakketten vallen buiten deze package-audit.

Tests draaien vóór de audit, zodat een kwetsbare dependency de coverageverzameling
niet verhindert. Playwright ruimt alleen `test-results/playwright/` op; de
Vitest- en auditrapporten blijven behouden. Rapporten worden ook na een fout bewaard.

## Waarom is CD uitgebreider?

CD heeft rechten om images te publiceren en Kubernetes aan te passen. Daarom
controleert `service-cd.yml` de repository, releasebranch, geslaagde CI-checks,
commit en artifacts. Oude commits, PR-runs en forks mogen niet deployen.

## Een keer bouwen, dezelfde image doorzetten

1. Merge `Development` naar `Testing`: CI test de gewijzigde services, bouwt hun
   containers en controleert het healthendpoint.
2. Testing-CD publiceert precies die containers naar GHCR en deployt ze met een
   vaste image-digest. Na een geslaagde rollout bewaart CD per service een klein
   `release.json`-bestand met de digest en de broncodeversie.
3. Test de applicatie op Testing. Er wordt niets automatisch naar productie
   doorgezet. Daarvoor moet iemand apart `Testing` naar `main` mergen.
4. Main-CD zoekt de geslaagde Testing-release voor dezelfde servicecode en
   gebruikt dezelfde digest. Er wordt geen nieuwe productie-image gebouwd.

Mergecommits kunnen andere commitnummers hebben. Daarom vergelijkt het script
de Git-hash van de servicemap: gelijke inhoud geeft dezelfde hash. De download
komt alleen uit een geslaagde, vertrouwde Testing-workflow. Ontbreekt die release,
dan stopt productie. Er is geen terugval naar opnieuw bouwen.

De container wordt 7 dagen bewaard als CI-artifact; het kleine releasebestand
90 dagen. GHCR bewaart de image zelf. Na verlopen artifacts draai je Testing-CI
opnieuw. Bij de eerste ingebruikname moet elke gewenste productierelease dus
eerst met deze nieuwe flow succesvol op Testing draaien.

Testing en productie hebben elk hun eigen pods, instellingen, Secrets en opslag.
Alleen de image wordt hergebruikt. De frontend gebruikt relatieve API-paden;
Kubernetes levert de proxyconfiguratie en omgevingsinstellingen tijdens het draaien.
Zet dus geen vaste Testing-URL of echte `.env` in de image.
Testing publiceert alleen een commit-tag en `:testing`; het gedeelde `:latest`
wordt niet bijgewerkt. Zo verandert een Testing-build ook geen oude bootstrap-tag
waar een productiepod mogelijk nog naar verwijst. Deployments gebruiken de digest.

`Scripts/select-service-release.cjs` kiest de vertrouwde run en artifacts.
`publish-service-image.sh` publiceert de bestaande container; `service-release.py`
schrijft of controleert het releasebestand. De workflows houden die stappen apart
zichtbaar. Een tweede commitcontrole na wachten op de omgeving blijft behouden.

De bestaande infrastructuurvolgorde is Terraform → Ansible → Kubernetes.
Een wijziging aan alleen service-CI start die infrastructuurketen niet.
Voor infrastructuurchecks bij een PR zijn alleen `Development → Testing` en
`Testing → main` toegestaan. Een feature-PR naar `main` of `Testing` slaat de
infrastructuurjobs meteen over, voordat er een eigen runner wordt aangevraagd.
GitHub kan de workflow nog wel tonen; er start dan geen Terraform-job.

`PR Branch Policy` meldt een verkeerde doelbranch met een rode check. Die check
draait ook opnieuw wanneer iemand de doelbranch corrigeert. Voeg na de eerste
GitHub-run `Check PR branch direction` toe aan de vereiste checks van `main` en
`Testing` om ook het mergen van verkeerd gerichte PR's te blokkeren.
Branch protection alleen voorkomt niet dat iemand zo'n PR opent.

PR-validaties hebben een eigen wachtrij per PR en blokkeren geen live deployment.
Een nieuwe PR-update annuleert de oudere validatie voor diezelfde PR.
Live deployments blijven hun bestaande gedeelde lock gebruiken en annuleren
elkaar niet. Handmatig starten van de infrastructuurketen blijft mogelijk.

De Proxmox-voorcontrole kijkt alleen of de vereiste VM's bestaan en draaien;
die controle maakt geen infrastructuur aan.
De hulptests draaien in `Pipeline Validation`, niet opnieuw bij elke deployment.
Bij een eerste installatie moet de infrastructuurketen klaar zijn vóór service-CD;
draaiende VM's betekenen nog niet dat Ansible en Kubernetes al klaar zijn.

Live Kubernetes-deployments vereisen `GHCR_USERNAME` en `GHCR_TOKEN`, zodat een
ontbrekende instelling geen werkend image-pull-secret met voorbeeldwaarden vervangt.
De validatiemodus heeft die credentials niet nodig.

Voor Gemini gebruikt iedere ontwikkelaar een eigen key in
`Mapping_Proposal/.env`. `.env.example` blijft een leeg voorbeeld.
Voor CD stel je één gedeeld repository-secret `GEMINI_API_KEY` in op GitHub.
Je kunt per environment (`Testing` / `Production`) een eigen waarde instellen.
CD schrijft die naar de Kubernetes Secret `gemini-api`;
alleen Mapping Proposal leest hem als omgevingsvariabele. CI gebruikt mocks en
heeft geen echte key nodig. Service-CD herstart Mapping Proposal om een nieuwe
key in te lezen; kies bij volledige Kubernetes-CD `restart` voor een keywijziging.
