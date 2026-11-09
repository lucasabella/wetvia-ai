# Conceptdata voor parlementaire bronanalyse

Datum: 9 november 2026. Alle voorbeelden zijn concept, door een agent samengesteld
en niet door Kamerondersteuners of juristen gereviewd. Dit is geen Wetvia juridische
evaluatieset en geen verzameling werkelijke vragen van Kamerleden.

Het lokale manifest `D:/Wetvia/training-runs/research_sources.json` bevat twaalf
primaire bronidentiteiten, URL, vindplaats, herkomst en hergebruiknotitie. Contexten
zijn korte oorspronkelijke Nederlandse parafrases van de geraadpleegde bronnen.
De bewijszin in het modelantwoord verwijst naar deze meegeleverde parafrase, en is
dus geen geverifieerd letterlijk citaat uit het oorspronkelijke Kamerstuk.
Onderzoek en bronverantwoording staan in
[docs/07](../docs/07-tweede-kamer-ai-trainingsonderzoek.md).

Zes documenten leveren 24 trainingsvoorbeelden, twee documenten acht devvoorbeelden
en vier documenten zestien testvoorbeelden. Iedere bron levert vier taken:
samenvatten, neutrale controlevraag, bewijszin en ontbrekende informatie.
De documentidentiteiten en contexten zijn gescheiden; onderwerpen en sjablonen
kunnen tussen splits overlappen. Daardoor meet dit hoogstens beperkte overdracht
van antwoordgedrag naar andere korte bronnen, geen brede taakgeneralisatie.

De procedurele bronnen dienen als aangeleverde context, niet als actuele kennis
die het model uit het hoofd moet leren. Voorbeelden over veranderende status
vereisen steeds de oorspronkelijke versie en datum. Het manifest bewaart de
raadpleegdatum; het bevat geen volledige, onveranderlijke snapshot van de PDF's.

Doel: korte neutrale Nederlandse antwoorden, broncodes, expliciete onzekerheid en
bewijs uit meegeleverde tekst. Niet afgedekt: zelfstandig juridisch advies,
lange documenten, vertaalnauwkeurigheid, echte beleidsvergelijking, politieke
representativiteit of privacy van toekomstige invoer. Geen private gebruikersdata
of persoonsgegevens als trainingscorpus verzameld.

Maten: volledig JSON-contract, juiste status en broncode, letterlijk aanwezige
bewijszin, completion-NLL op referentieantwoorden, lexicale feitwoorddekking.
De NLL meet voorkeur voor deze specifieke agentgeschreven antwoorden. De
contractscore kan slagen terwijl de antwoordtekst inhoudelijk onjuist is. Een
verandering moet daarom per taak met ruwe antwoorden en menselijke review worden
beoordeeld. Vier testdocumenten zijn onvoldoende voor betrouwbare claims over
productiekwaliteit; dit experiment rapporteert geen statistische significantie.

Na de eindtest mag dezelfde test niet worden gebruikt om verder te optimaliseren.
Een volgend experiment heeft een nieuwe ongeziene test nodig. Er is geen
automatische promotie van de adapter naar het productiemodel.
