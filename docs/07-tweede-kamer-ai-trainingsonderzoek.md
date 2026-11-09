# 07. Tweede Kamer: AI-gebruik en een klein trainingsexperiment

Onderzocht op 9 november 2026. Dit is een verkennende onderbouwing voor lokale
fine-tuning, geen behoefteonderzoek onder alle Kamerleden en geen juridische
kwaliteitsverklaring.

## Wat de primaire bronnen aantonen

Het Presidium beschreef in mei 2025 ambtelijke proeven met Copilot en ChatGPT voor
samenvatting, documentvergelijking, verslaglegging en metadata. Bestaande modellen
werden gebruikt; een eigen model ontwikkelen op Kamerdata behoorde niet tot die
experimenten. Copilot zou op aanvraag beschikbaar worden met voorafgaande
instructie. Dit is een beschrijving van de proeven toen, geen inventarisatie van
alle individuele gebruikers. [Nota Raming 2026, pp. 22–23](https://www.tweedekamer.nl/downloads/document?id=2025D24877).

In mei 2026 noemt de Kamer schrijven, redigeren, samenvatten en vertalen als
ondersteunde werkzaamheden. Leden en fracties kunnen sinds september 2025
productiviteits-AI aanvragen. Een chatbot voor parlementaire informatie en gebruik
van Vlam.ai worden als verdere mogelijkheden beschreven. Die passage bewijst geen
reeds operationele zoekchatbot en noemt geen dagelijks gebruikspercentage.
[Nota Raming 2027, pp. 20–22](https://www.tweedekamer.nl/downloads/document?id=2026D25317).

Het oorspronkelijke Leidse onderzoek beschrijft gesprekken met 58 Kamerleden.
Zij wensen onder andere bondige stukken, samenvatting met duiding en betere
informatieontsluiting. De onderzoekers waarschuwen voor ongelijke respons per
fractie; de uitkomsten zijn indicatief voor de gehele Kamer. De PDF draagt de titel
*Van overvloed naar overzicht?*, hoewel begeleidende stukken ook *inzicht*
gebruiken. [Onderzoeksrapport, samenvatting en onderzoeksontwerp](https://www.tweedekamer.nl/downloads/document?id=2025D49918).

Een aanvullende primaire bron voor individuele ervaringen is het oorspronkelijke
onderzoek van Investico en De Groene van 21 oktober 2026. Daarin verklaren
geïnterviewde leden AI onder meer te gebruiken voor het inkorten van eigen tekst
en debatvoorbereiding. De onderzoekers rapporteren ook detectieresultaten voor
spreekteksten. Dat zijn schattingen met een detector, geen sluitende registratie
van persoonlijk gebruik. Er is bovendien variatie tussen fracties, waaronder
bewuste beperkingen. De artikeltekst is niet opgenomen in de trainingsdata.
[Oorspronkelijke publicatie met werkwijze en reacties](https://www.platform-investico.nl/onderzoeken/bijna-de-helft-van-alle-kamerleden-sprak-dit-jaar-door-ai-gemaakte-teksten-uit-in-debat).

## Vertaling naar training en evaluatie

De volgende keuzes zijn onze afleiding uit het onderzoek, geen door de Kamer
goedgekeurde productspecificatie. Een klein model kan vooral worden getraind op
antwoordgedrag bij meegeleverde broninformatie. Actuele kennis hoort uit bronnen
te komen; het adapterbestand is geen betrouwbare opslagplaats voor veranderende
parlementaire feiten.

| Taak | Gewenst gedrag | Controle |
| --- | --- | --- |
| Samenvatten en briefing | Beknopt Nederlands, kernfeiten behouden, bron noemen | Feitdekking en bronverwijzing |
| Neutrale vervolgvragen | Vragen op basis van het fragment, geen onbewezen premisse | Vorm, relevantie en menselijke review |
| Ontbrekende informatie | Expliciet zeggen dat het fragment onvoldoende informatie bevat | Abstentie op onbeantwoordbare vragen |
| Documentstatus | Onderscheiden tussen plan, aanbeveling en uitgevoerd besluit | Gerichte statusgevallen |
| Redactie | Betekenis en onzekerheid behouden bij inkorten | Vergelijking met originele tekst |

Vertaling en lange documentvergelijking blijven in dit eerste experiment
onvoldoende afgedekt. Een positief resultaat op korte fragmenten onderbouwt geen
claim dat deze taken of juridisch advies betrouwbaar werken.

## Bronnen en herkomst van het experiment

Het lokale manifest staat buiten git op
`D:/Wetvia/training-runs/research_sources.json`. Het bevat twaalf verschillende
bronidentiteiten met oorspronkelijke Nederlandse parafrases, vindplaatsen,
controlefeiten en vragen waarop het fragment geen antwoord geeft. De vaste
voorgestelde verdeling is zes documenten voor training, twee voor ontwikkeling en
vier voor de eindtest. Alle items zijn concept en hebben geen menselijke review.
Er zijn geen privégegevens van gebruikers verwerkt.

De test bevat onder meer een gewijzigde convocatie. De zoekresultaattekst toonde
een oudere versie; de opgehaalde PDF meldt afgelasting en omzetting naar
schriftelijk overleg. Gebruik bij actualiteitsvragen dus het document zelf en
bewaar de geraadpleegde versie. [Herziene convocatie 2026D01188](https://www.tweedekamer.nl/downloads/document?id=2026D01188).

De Tweede Kamer staat teksthergebruik met bronvermelding toe, tenzij anders
vermeld; dit is geen claim van een algemene CC-licentie voor ieder aangehecht
document. Rijksoverheid vermeldt CC0 voor haar webteksten, met uitzonderingen.
Het manifest gebruikt voor het door universitaire auteurs geschreven rapport
uitsluitend korte eigen feitelijke parafrases. Foto's en audiovisueel materiaal
zijn uitgesloten. [Tweede Kamer: teksthergebruik](https://www.tweedekamer.nl/applicaties/disclaimer),
[Rijksoverheid: copyright](https://www.rijksoverheid.nl/service/copyright).

## Betekenis van de cijfers

Gebruik vóór en na training exact dezelfde testprompts, context, decodeerinstellingen
en scorer. Bewaar ruwe antwoorden en rapporteer per taak. Kies trainingsinstellingen
op de ontwikkelset. Pas na inzage in de testresultaten niet opnieuw de adapter aan
op die test; daarvoor is een nieuwe ongeziene test nodig.

Documenten zijn gescheiden, maar onderwerpen kunnen overlappen. De beperkte set
bevat bovendien door een agent geschreven instructies en referentieantwoorden.
Automatische controles op woorden, structuur en broncodes zijn benaderingen van
kwaliteit. Zij bewijzen geen semantische juistheid, onafhankelijke juridische
kennis of toepasbaarheid in de werkpraktijk. Laat voor inzet echte documenten en
gebruikersvragen beoordelen door Kamerondersteuners en een inhoudsdeskundige.
