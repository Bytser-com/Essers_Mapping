# CI/CD uitleg

## Welke bestanden lees je eerst?

- `frontend-ci.yml`: lint, TypeScript, tests, build, browsertests en dependencycheck.
- `runtime-ci.yml`: bepaalt of Runtime gecontroleerd moet worden en roept Java-CI aan.
- `java-service-ci.yml`: Maven-tests, coverage, dependencycheck en containercontrole.
- `mapping-*-ci.yml`: dezelfde opzet voor de toekomstige Python-services.
- `*-cd.yml`: publicatie en deployment na een geslaagde CI-run.

## CI in drie stappen

1. **changes** vergelijkt de gewijzigde bestanden met de vorige commit of PR-basis.
2. **checks** voert de controles uit wanneer de service of gedeelde CI-code verandert.
3. **quality-gate** controleert of wijzigingsdetectie en de benodigde checks geslaagd zijn.

De eindcheck heeft een vaste naam, zoals `Runtime CI Gate`. Die naam kun je verplicht
maken in de branchregels. Een ongewijzigde service mag de controles overslaan;
een fout bij wijzigingsdetectie mag geen groene eindcheck opleveren.

PR's en pushes naar `Development` gebruiken de filters om CI-minuten te besparen.
Een handmatige run controleert alles. Pushes naar `Testing` en `main` controleren
ook alles: CD moet artifacts van de nieuwste releasecommit kunnen downloaden.
Anders zou een nieuwe documentatiecommit een nog wachtende app-deployment kunnen
blokkeren zonder een vervangend build-artifact te maken.

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
7. De Docker-image bouwen en het HTTP-healthendpoint controleren.
8. Rapporten bewaren; de JAR wordt alleen bij succes beschikbaar voor CD.

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
we de Runtime-dependencies (inclusief testdependencies) naar `target/sonar-libraries`.
`sonar-project.properties` verwijst naar die JARs en de gecompileerde productie-
en testklassen. Python wordt als versie 3.12 geanalyseerd, net als in CI.
Het patroon `Mapping_*/coverage.xml` leest bestaande Python-rapporten en verwacht
geen rapport van een service die alleen een README bevat.

Onze teamafspraak is **minstens 70% totale coverage**. Dat is een andere maatstaf
dan de standaard Sonar-gate: die vereist **80% coverage op nieuwe code**.
De workflow neemt de gate over van SonarCloud; het percentage staat niet in YAML.
Een eigen gate met 70% totale coverage vereist in SonarCloud een Team- of
Enterprise-abonnement. De bestaande Sonar-gate blijft actief in SonarCloud.
In GitHub Actions behandelen we alleen een tekort aan coverage op nieuwe code
als waarschuwing. De cloud-gate kan daardoor rood zijn terwijl deze workflow groen
is. Security-, betrouwbaarheids-, onderhoudbaarheids-, duplicatie- en andere
gatefouten blijven de workflow blokkeren. De 70% totale coverage is een teamdoel;
deze wijziging voegt daarvoor geen automatische grens toe.
Let op: Sonars `Coverage` combineert regels en vertakkingen en kan dus lager zijn
dan alleen `Line coverage`. Bekijk voor onze afspraak de totale `Coverage`.

De scan uploadt eerst de analyse zonder zelf op de gate te wachten. Daarna leest
`Scripts/check-sonar-quality-gate.py` het taaknummer uit `.scannerwork/report-task.txt`.
Het script wacht maximaal vijf minuten op die taak en controleert de voorwaarden
van precies die analyse. Alleen `new_coverage` geeft een `::warning::` en exitcode 0.
Andere gefaalde voorwaarden, ontbrekende resultaten, API-fouten en timeouts geven
exitcode 1. Een fout tijdens het scannen zelf blijft ook blokkeren.
Het JSON-gateresultaat staat in het artifact `sonarqube-reports`, onder
`test-results/sonarqube-quality-gate.json`.

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
controleert `service-cd.yml` de bronrepository, releasebranch, succesvolle push-run,
commit en artifacts. Oude commits, PR-runs en forks mogen niet deployen.

Daarna wordt de geteste artifact verpakt, de container gecontroleerd en een image
naar GHCR gepubliceerd. Kubernetes gebruikt de vaste image-digest. Een tweede
commitcontrole na het wachten voorkomt deployment van een achterhaalde image.
Deze controles beschermen de omgeving en blijven behouden.

De bestaande infrastructuurvolgorde is Terraform → Ansible → Kubernetes.
Een wijziging aan alleen service-CI start die infrastructuurketen niet.
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
