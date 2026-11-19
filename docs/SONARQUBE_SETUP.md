# SonarQube Community Build instellen

De gezamenlijke analyse draait op `Development` en uploadt naar
`https://sonar-essers.shystack.com`. De server is via Cloudflare Tunnel bereikbaar.

## 1. Project aanmaken

Klik op **Create a local project** in het scherm met de importopties. Dit betekent
dat het Sonar-project handmatig wordt aangemaakt; GitHub Actions kan het daarna
gewoon analyseren. Een GitHub App is voor deze analyse niet nodig.

- Projectnaam: `Essers Mapping`.
- Projectkey: `Bytser-com_Essers_Mapping` (of kies een eigen key en stel die ook in GitHub in).
- Hoofdbranch: `Development`, met dezelfde hoofdletters als in GitHub. Stel dit
  tijdens het aanmaken in als het veld beschikbaar is; controleer de naam daarna
  bij de branchinstellingen van het project.

Gebruik één project voor de frontend en services samen. De workflow verzamelt
hun coverage bij dezelfde commit en publiceert één volledig resultaat.

## 2. Publieke server-URL instellen

Ga naar **Administration > Configuration > General Settings > General** en zet
**Server base URL** op `https://sonar-essers.shystack.com`.

Controleer dat deze URL direct de Sonar-API geeft:

```powershell
Invoke-RestMethod https://sonar-essers.shystack.com/api/system/status
```

De status moet `UP` zijn. Een Cloudflare-loginpagina is geen bruikbaar API-resultaat.
De machine met SonarQube en de tunnel moeten beschikbaar blijven tijdens analyse
en het verwerken van de quality gate.

## 3. Analysetoken maken

Ga naar **My Account > Security** en genereer een **Project Analysis Token** voor
dit project, bijvoorbeeld met naam `github-actions-essers`. Bewaar het token
meteen in GitHub; het wordt niet opnieuw getoond. Gebruik een account met de
vereiste **Execute Analysis**-rechten voor het project.

Gebruik een nieuw token van deze server. Het bestaande SonarCloud-token werkt
niet op de eigen instantie. Zet het token niet in de repository of PR.

## 4. GitHub Actions instellen

Ga in de repository naar **Settings > Secrets and variables > Actions**.

| Tab | Naam | Waarde |
| --- | --- | --- |
| Variables | `SONAR_HOST_URL` | `https://sonar-essers.shystack.com` |
| Variables | `SONAR_PROJECT_KEY` | `Bytser-com_Essers_Mapping`, of de gekozen projectkey |
| Secrets | `SONAR_TOKEN` | Het nieuwe project-analysetoken van deze server |

`SONAR_ORGANIZATION` wordt niet meer gebruikt en kan worden verwijderd.
Deze waarden horen op repositoryniveau, omdat de Sonar-job geen GitHub Environment
selecteert. Er zijn hiervoor geen wijzigingen nodig aan de deployworkflows.

De huidige verbinding bereikt de API rechtstreeks via HTTPS. Als later Cloudflare
Access met een extra login wordt toegevoegd, moet de runner ook door die laag
kunnen authenticeren; alleen `SONAR_TOKEN` volstaat daarvoor niet. Cloudflare
ondersteunt daarvoor onder meer service tokens met een **Service Auth**-policy.
Dat vraagt ook ondersteuning voor die authenticatie in alle scanner- en
quality-gateverzoeken; alleen extra GitHub secrets toevoegen is onvoldoende.

## 5. Eerste scan starten

Zorg dat de workflowwijzigingen op `Development` staan. Kies daarna in GitHub
**Actions > SonarQube > Run workflow > Development**, of push een nieuwe commit
naar `Development`.

De workflow maakt coverage met Vitest, Maven/JaCoCo en pytest, uploadt de analyse
en controleert de quality gate van precies die analyse. Bekijk:

- De job **SonarQube Quality Gate** voor het scanner- en gateresultaat.
- Het project in SonarQube voor issues, coverage en quality-gatevoorwaarden.
- Artifact **sonarqube-reports** voor test- en coveragerapporten en
  `test-results/sonarqube-quality-gate.json`.

Deze migratie behoudt de bestaande CI-afspraak: alleen onvoldoende coverage op
nieuwe code geeft een waarschuwing; andere gatefouten blokkeren. Daardoor kan de
Sonar-gate rood zijn terwijl de GitHub-job groen is. Community Build ondersteunt
eigen gates, dus een gate voor de teamafspraak van 70% totale coverage kan apart
worden ingericht. Dat wordt door deze workflowwijziging niet automatisch ingesteld.

## 6. Branches en pull requests

Community Build ondersteunt één hoofdbranch per project en geen native
pull-requestanalyse. Daarom analyseert deze workflow alleen `Development`.
Laat `Testing`, `main` en featurebranches niet naar dezelfde projectkey uploaden;
anders overschrijven ze het gezamenlijke resultaat.

Maak **SonarQube Quality Gate** niet verplicht voor PR's: die job draait pas na
een push of merge naar `Development`. De bestaande frontend-, Runtime- en
Python-servicechecks blijven de PR-controles.

## Documentatie

- [Sonar-project handmatig aanmaken](https://docs.sonarsource.com/sonarqube-community-build/project-administration/creating-project/creating-manually)
- [GitHub Actions configureren](https://docs.sonarsource.com/sonarqube-community-build/devops-platform-integration/github-integration/adding-analysis-to-github-actions-workflow)
- [Server base URL](https://docs.sonarsource.com/sonarqube-community-build/instance-administration/server-base-url)
- [Ondersteunde Community Build-functies](https://docs.sonarsource.com/sonarqube-community-build/feature-comparison-table)
- [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
