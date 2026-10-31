# Afgooien

Een eigen dartspel bovenop de Autodarts-detectie. Autodarts doet de camera's,
de kalibratie en het herkennen van de pijlen; Afgooien doet de spelregels, het
scorebord, wie er aan de beurt is en de spraak.

Alleen standaard Python nodig (3.9 of nieuwer), **geen extra pakketten**.
Werkt op Windows, Mac, Linux en straks op een Raspberry Pi.

## Telefoon als bediening (darts corrigeren)

Klik op het hoofdscherm op **📱** (rechtsboven) en scan de QR-code met je telefoon. Je telefoon moet
op hetzelfde wifi-netwerk zitten. Je telefoon toont dan:
- het bord met de pijlen van deze beurt;
- de 3 pijlen erboven;
- de beurtscore en de stand.

Het werkt op Android en iPhone, zonder app te installeren, en met meerdere telefoons tegelijk.

- **Corrigeren:** tik een pijl aan (bijv. "S5") en tik daarna de juiste plek op het bord.
- **Pijl plaatsen:** zet je vinger op het bord. De pijl springt naar je vinger en schuift mee tot
  je loslaat; de oude plek blijft vaag zichtbaar. Boven je vinger toont een vergrootglas het vak
  (bijv. "T5") en je telefoon trilt zachtjes bij elk nieuw vak.
- **Vasthouden = inzoomen:** houd je je vinger langer dan 0,7 s vast, dan zoomt het bord in tot 3×
  rond je vinger. De plek onder je vinger blijft staan en elke beweging is daarna veel fijner.
  Loslaten = plaatsen; het bord zoomt weer uit.
- **Naar de rand = meeschuiven:** kom je met je vinger bij de rand van het bord, dan schuift het beeld
  die kant op (een gele gloed laat zien welke kant). Hoe dichter bij de rand, hoe sneller. Zo kom
  je ook ingezoomd bij elk deel van het bord.
- **Inzoomen:** kies je een pijl, dan zoomt het bord in op die pijl (1,8×). Met ＋ / − zoom je verder
  (tot 4×) of weer uit.
- **Toetsen:** of kies via **Toetsen** het vak: Single/Double/Triple + nummer, Bull, of "Mis (op bord)".
- **Invoeren:** een lege plek ("＋ invoeren") voert een pijl in die het systeem miste.
- Ongedaan, Mis en Volgende werken zoals op het hoofdscherm. Bij Afgooien kun je de
  bull/bullseye/100+-punten ook op de telefoon verdelen.
- **Als app op je startscherm:** Chrome → ⋮ → *Toevoegen aan startscherm*. Het adres staat ook
  in het venster van de server, bijv. `http://192.168.1.20:8080/m`.
- **Lukt verbinden niet?** Sta Python in de Windows-firewall toe voor *privénetwerken*, en controleer
  dat je telefoon niet op een gastnetwerk zit. Op de Raspberry Pi werkt het meteen.

## Starten met één klik

- **Windows**: dubbelklik op **Afgooien.bat**. De server start en Chrome opent het speelscherm
  als eigen venster (zonder tabbladen). Sluit je dat venster, dan stopt alles.
  Eenmalig een snelkoppeling op je bureaublad maken (met Afgooien-icoon): open een
  opdrachtvenster in de map en typ `py launcher.py --snelkoppeling`.
- **Mac**: dubbelklik op **Afgooien.command**. **Linux / Raspberry Pi**: `python3 launcher.py`.

Opties kun je erachter zetten, ook in de snelkoppeling (Eigenschappen → Doel):

| Optie | Wat |
|---|---|
| `--kiosk` | volledig scherm zonder randen, voor de monitor naast het bord (Alt+F4 = sluiten) |
| `--browser edge` | Microsoft Edge in plaats van Chrome (Edge heeft de mooiste natuurlijke stemmen) |
| `--autodarts off` | zonder Autodarts, pijlen aanklikken |
| `--laat-draaien` | server blijft aan als het venster sluit |

Klik je nog een keer terwijl Afgooien al draait, dan opent alleen het venster. Start eerst de
Autodarts-app (Board Manager); Afgooien blijft anders zoeken tot hij hem vindt. Het venster
gebruikt een eigen Chrome-profiel (in de gegevensmap), zodat de stem meteen mag praten.

## Starten

1. Start de **Autodarts Board Manager** zoals je gewend bent en zet het bord op "Start".
2. Start Afgooien:
   - Windows: dubbelklik `start.bat`
   - Mac/Linux/Raspberry Pi: `./start.sh` (of `python3 run.py`)
3. Open **http://localhost:8080** in je browser. Op een tablet, telefoon of tv in
   hetzelfde wifi-netwerk gebruik je het adres dat in het venster staat
   (bijv. `http://192.168.1.23:8080`).

Rechtsboven zie je of Autodarts verbonden is.

### Opties

```
python run.py --autodarts off                       # zonder Autodarts, pijlen aanklikken
python run.py --autodarts http://192.168.1.50:3180  # Board Manager op een ander apparaat
python run.py --port 9000                           # andere poort voor het speelscherm
```

## Bediening

| Actie | Hoe |
|---|---|
| Pijl invoeren | Klik op het bord op het scherm (ook tijdens een Autodarts-spel) |
| Pijl corrigeren | Klik op de pijl onder het bord (bijv. "S5") en daarna op de plek waar hij echt zit |
| Tekstgrootte | A− / A+ rechtsboven (wordt onthouden), of Instellingen → Weergave |
| Zoom hele scherm | Instellingen → Weergave, of `Ctrl` + `+` / `−` / `0` |
| Taal | Instellingen → Taal: Nederlands of English (scherm, verloop én stem) |
| Mis | knop **Mis** of toets `M` |
| Ongedaan maken | knop **Ongedaan** of toets `Z` |
| Volgende speler | pijlen uit het bord halen (Autodarts ziet dat), of knop / `Enter` |
| Stem instellen | 🔊 rechtsboven: aan/uit, stem kiezen, toonhoogte, snelheid, testknoppen |
| Verloop | klik op "Verloop" om het logboek uit of in te klappen |
| Bot toevoegen | "+ 🤖 Bot toevoegen" bij Nieuw spel, of kies per speler "Mens" of een botniveau |
| Reset camera's | knop onder het bord (alleen met Autodarts): reset de Board Manager |

**Statusring om het bord:** groen = gooien; geel = niet gooien (pijlen uit het bord
halen, bot is aan de beurt, of eerst kiezen); rood = geen verbinding met Autodarts of
een probleem. Rood of blijft hij geel terwijl het bord leeg is? Klik op "Reset camera's".
De reset-opdracht aan de Board Manager is nog niet getest met een echt bord; lukt hij
niet, dan zie je een melding en klik je in Autodarts zelf op Reset.

**Bots:** niveau 1 haalt gemiddeld 0,5 punt per beurt, niveau 2 1,0, niveau 3 1,5,
niveau 4 2,0, niveau 5 2,5 en niveau 6 3,0 (afgesteld met `tools/bot_calibrate.py`).
Bots gooien virtueel; tijdens hun beurt telt Autodarts niet mee.

**100+-meter:** met de 100+-regel aan zie je onder je pijlen je beurtscore en wat je
nog nodig hebt (bijv. "nog 57 voor 100+: minimaal T19"): groen = makkelijk,
oranje = triple/hoge dubbel nodig, rood = bijna onmogelijk.

**Stem:** de stem komt van de browser. Het mooist klinkt Microsoft Edge (gratis
op Windows en Mac), met de natuurlijke stem "Microsoft Maarten Online (Natural)".
Afgooien kiest automatisch de beste Nederlandse stem; je kunt hem ook zelf kiezen.
Zet je de taal op English, dan schakelt de stem over naar Engels (in Edge bijv.
"Microsoft Ryan Online (Natural)", Brits). Per taal wordt je eigen stemkeuze onthouden.

**Instellingen → Weergave** (per scherm, handig voor een monitor naast het bord):
zoom van het hele scherm, tekstgrootte van het spelscherm, grootte van het dartbord,
animaties/confetti aan of uit, scherm wakker houden tijdens een potje, en volledig scherm.
De taal geldt juist voor alle schermen die met hetzelfde spel verbonden zijn en wordt
bewaard in `instellingen.json` in de gegevensmap.

Detecteert Autodarts een pijl verkeerd: klik op die pijl onder het bord en daarna op
de plek waar hij echt zit. Het spel rekent alles daarna opnieuw uit.

**Logboek:** elke worp (met de ruwe gegevens van Autodarts) en elke correctie komt in
`data/worpen.jsonl`. Met `python tools/analyse_worpen.py` zie je hoe nauwkeurig de
detectie is en welke vergissingen vaak voorkomen. Stuur dat bestand op om de detectie
op jouw bord te laten verbeteren.

**Waar worden gegevens bewaard?** Buiten de programmamap, zodat ze blijven bestaan als
je een nieuwe versie uitpakt:

- Windows: `%APPDATA%\Afgooien` (plak dat in de adresbalk van de Verkenner)
- Mac: `~/Library/Application Support/Afgooien`
- Linux / Raspberry Pi: `~/.local/share/afgooien`

Daarin staan `instellingen.json` (taal), `spelers.json` (opgeslagen spelers), `geschiedenis.json` (scorebord),
`worpen.jsonl` (logboek) en `spel.json` (lopend potje; na een crash gaat het spel verder).
Het venster van start.bat toont de map bij het opstarten. Gegevens uit de `data`-map van
een oudere versie worden automatisch overgenomen als je die map in de nieuwe programmamap
zet, of start eenmalig met `start.bat --import-data "C:\pad\naar\oude\afgooien"`.

## Andere spellen (Spelkeuze)

**X01** (101 t/m 1001, standaard 501): gooi je score precies naar nul. Instelbaar zoals in
Autodarts: startscore, wedstrijd (Uit = 1 leg / Legs: first to N / Sets: first to N sets van
N legs), inmode en uitmode (Straight / Double / Master) en bull-off (Uit / WDF = dichtst bij
het midden begint / PDC = alleen bull en bullseye tellen). Bust = terug naar de score van het
begin van je beurt. Onder de instructie staat de uitgooi-route (bijv. "T20 · T20 · Bull") en
het eerste vak licht op het bord op. De beginner wisselt per leg. Statistieken: 3-pijls-
gemiddelde, first 9, 180/140+/100+, hoogste finish, beste leg, uitgooi% en busts.

**Count Up**: elke pijl telt zijn gewone score; na het aantal rondes (standaard 8) wint de
hoogste. Ook solo te spelen.

**Cricket**: sluit 15 t/m 20 en de bull (3 marks; dubbel = 2, triple = 3). Normaal, cut-throat
of zonder punten; maximaal aantal rondes instelbaar. Een marks-tabel staat onder de spelers.

**Party**
- **Killer**: iedereen krijgt een willekeurig nummer; raak je eigen dubbel om killer te worden,
  daarna kost elke dubbel van een ander die speler een leven (levens instelbaar). Minimaal 2 spelers.
- **Shanghai**: ronde 1 op 1, ronde 2 op 2 … (7, 10 of 20 rondes); single + dubbel + triple in
  één beurt wint direct (uit te zetten).
- **Halve-It**: doelen 15, 16, een dubbel, 17, 18, een triple, 19, 20, bull; niets geraakt = score
  gehalveerd.
- **Golf**: 9 of 18 holes; dubbel = 1 slag, triple = 2, single = 3, mis = 5. Na elke pijl mag je
  stoppen (Volgende): de laatste pijl telt. Laagste totaal wint.
- **Gotcha**: tel op naar precies 201/301/501; kom je op iemands score, dan gaat die terug naar 0.

**Training**
- **Rond de klok**: 1 t/m 20 op volgorde (elk vak, alleen dubbels of alleen triples), optioneel
  de bull als laatste en "dubbel/triple slaat over".
- **Bob's 27**: begin op 27, D1 t/m D20 (+ bull): raak = waarde erbij, alles mis = eraf; onder nul
  is af (of doorspelen).
- **Doubles oefenen**: een dubbel per ronde, op volgorde of willekeurig.
- **Bullen**: alleen de bull telt (25/50), 1 t/m 30 rondes.
- **Random checkout**: elke ronde krijgt iedereen dezelfde willekeurige finish (2–40, 41–100,
  101–170 of alles), double out, één beurt; de uitgooi-route staat erbij.

Alle spellen werken met 1 t/m 8 spelers en bots. Botniveaus zijn daar een
3-pijlsgemiddelde: niveau 1 ≈ 25, 2 ≈ 35, 3 ≈ 45, 4 ≈ 55, 5 ≈ 65, 6 ≈ 80. Het scorebord heeft
per spel een eigen ranglijst, prijzen en potjeslijst (kies het spel rechtsboven).

## Spelregels (zoals ingebouwd)

1. **Nummer kiezen**: elke speler gooit één pijl met zijn verkeerde arm. Het
   nummer dat je raakt is van jou. Bull, mis of een nummer dat al van iemand is:
   opnieuw gooien.
2. **Bull-gooi**: daarna één pijl zo dicht mogelijk bij de bullseye. Wie het
   dichtst bij is begint, de rest volgt op afstand. Gelijk om de eerste plek:
   die spelers gooien opnieuw.
3. **Punten halen**: om de beurt 3 pijlen. Op je eigen nummer: single 1, dubbel 2,
   triple 3 punten, maximaal 5.
4. **Afgooien**: zodra je 5 punten hebt (ook midden in je beurt) haal je met
   treffers op andermans nummer punten bij hen weg. **Af ben je alleen door een andere
   speler**: hij zet je op 0 (met een pijl op je nummer of met bonuspunten), of hij raakt
   je nummer terwijl je al op 0 staat (ook als je nog nooit punten had). Word je zelf onder de 5 gegooid, dan
   moet je eerst weer 5 halen. Je eigen nummer raken met 5 punten doet niets.
5. **Buiten het bord** kost je 1 punt, maar alleen als het hele bord gemist is. Een pijl
   net boven de dubbel (in de cijferring) is mis, maar kost niets. Je kunt niet onder 0
   komen en jezelf niet afgooien: wie zichzelf zo op 0 gooit, speelt gewoon door. Op het scherm: klik in de cijferring = mis op het bord,
   klik buiten het bord of de knop "Buiten bord −1" = strafpunt.
6. **Bull = 1 punt, bullseye = 3 punten.** Heb je nog geen 5, dan krijg je ze zelf
   (tot 5, de rest vervalt). Stond je al vóór die pijl op 5, dan kies je in een venster bij
   wie ze eraf gaan. Kom je pas door deze pijl op 5 (bijv. 3 punten + bullseye), dan haal je
   met die bonus niets af: met je volgende pijl mag je afgooien. Verdelen mag,
   bijv. 2 bij de ene en 1 bij de andere speler. Haal je zo iemands laatste punt weg, dan
   is hij af. Je kunt bonuspunten alleen afhalen bij spelers die nog punten hebben: wie al
   op 0 staat verliest niets, en heeft niemand punten, dan vervalt de bonus.
7. **100 of meer in één beurt** (gewone dartscore, bijv. T20 + D20) = 3 punten, op
   dezelfde manier. Telt één keer per beurt.
8. De laatste die over is wint.

Heeft nog maar één tegenstander punten, dan gaan de punten van bull, bullseye of
100+ meteen bij hem eraf (geen keuzevenster).

Krijg je meer punten dan je nodig hebt om op 5 te komen, dan vervalt de rest.
Pijlen die binnenkomen terwijl het keuzevenster openstaat, wachten en tellen
daarna gewoon mee.

Onder "Spelregels aanpassen" kun je het aantal punten, pijlen per beurt, de
regel voor "af" en elk van de extra regels (5-7) aan- of uitzetten.

## Als de koppeling met Autodarts niet werkt

**Autodarts 2.x:** op http://localhost:3180 zie je "Board Manager is no longer supported".
Dat is normaal: alleen het oude webscherm is weg. Camera's kalibreren en starten doe je
in de Autodarts Desktop-app; Afgooien leest de worpen via `/api/state` op dezelfde poort.

De lokale API van de Board Manager is niet officieel beschreven. Afgooien vraagt
`http://localhost:3180/api/state` op. Komen er geen pijlen binnen:

1. Start de Board Manager en draai `python tools/autodarts_probe.py`
2. Gooi een paar pijlen en haal ze uit het bord
3. Stuur het bestand `autodarts_probe.log` op, dan wordt de koppeling aangepast.

## Testversie (zonder installatie)

`dist/afgooien-testversie.html` is één losse pagina met dezelfde spelregels; werkt
zonder server en zonder internet. Dubbelklik om te openen en voer pijlen in door
op het bord te klikken; de rand met cijfers telt als "buiten het bord".

De spelregels staan twee keer in het project: `afgooien/engine.py` (programma met
Autodarts) en `web/engine.js` (testversie). `tests/test_parity.py` speelt duizenden
willekeurige potjes met beide en controleert dat ze na elke stap identiek zijn.
Pas je een regel aan, doe dat in beide en draai de tests. Opnieuw bouwen:
`python tools/build_testversie.py`.

## Testen zonder bord

```
python tools/fake_autodarts.py     # venster 1: typ T20, D5, S1, B, BE, M of u (uitnemen)
python run.py                      # venster 2
```

Automatische tests: `python -m unittest discover -s tests`

## Raspberry Pi

Werkt op een Raspberry Pi 4 of 5 met **Raspberry Pi OS (64-bit, met bureaublad)**.

1. Installeer Autodarts op de Pi: `bash <(curl -sL get.autodarts.io)` en stel de camera's in.
   Autodarts 2 start niet vanzelf: open `autodarts` en installeer de dienst onder **Service**
   (dan start hij ook na een herstart).
   Het installatiescript zet ook een natuurlijke stem (Piper) op de Pi; kies onder Stem → Soort stem
   eventueel weer "Browserstem".
2. Zet de map van Afgooien op de Pi (zip downloaden en uitpakken, bijv. in `~/afgooien`).
3. Open een terminal in die map en typ: `bash install_pi.sh`

Het script:
- installeert Chromium en een stem (espeak-ng);
- laat Afgooien als dienst starten bij het opstarten, ook na een stroomstoring;
- opent het speelscherm vanzelf op volledig scherm;
- zet het uitgaan van het scherm uit.

Na `sudo reboot` start alles vanzelf.

| Variant | Commando |
|---|---|
| Alleen server, scherm op laptop/tablet/tv | `bash install_pi.sh --geen-scherm` |
| Venster, niet volledig scherm | `bash install_pi.sh --geen-kiosk` |
| Zonder Autodarts | `bash install_pi.sh --autodarts off` |
| **Snelste: Raspberry Pi OS Lite** (geen bureaublad) | `bash install_pi.sh --lite` |
| Weer uit het opstarten halen | `bash install_pi.sh --verwijder` |

**Beste prestaties:** gebruik Raspberry Pi OS **Lite** (64-bit) met `--lite`. Dan draait er geen
bureaublad: de Pi start direct een minimale kiosk-schil (cage) met de browser op volledig scherm.
Dat scheelt geheugen en rekenkracht, zodat er meer overblijft voor Autodarts. Het spel ziet er precies
hetzelfde uit. De browser blijft Chromium: dat is op de Pi de enige browser met
hardwareversnelling, en hij is nodig voor de stem en voor dezelfde weergave. Lichtere browsers
(zoals WPE/cog) hebben geen stem en geven verschillen in de weergave.

**Prestatiemodus** (Instellingen → Weergave) staat op een Raspberry Pi vanzelf aan. Hij vervangt de
zware live-effecten (vervaging achter menu's en vensters, de gloed rond het bord) door lichte
varianten die er vrijwel hetzelfde uitzien. Ook valt er minder confetti.

**Raspberry Pi 4:** volgens Autodarts zelf is een Pi 4 mét monitor erop te zwaar voor 3 camera's
("bleeding edge"); de Pi 5 is getest. Lukt de herkenning niet goed, gebruik dan `--geen-scherm`
en open het spel op een laptop, tablet of tv: `http://<ip-van-de-pi>:8080` (het script toont het
adres). Gebruik in elk geval de officiële voeding, actieve koeling en 800x600 bij de camera's,
en zet op een Pi-scherm eventueel Instellingen → Weergave → Animaties uit.

**Stem op de Pi:** Chromium op Linux heeft alleen de robotachtige espeak-stem. Voor een mooie stem:
zet de stem op het Pi-scherm uit (🔊) en laat een tablet, telefoon of laptop met Edge meekijken;
elk scherm dat het spel open heeft, kan de stem afspelen.

Na een update: nieuwe versie uitpakken (over de oude heen) en `sudo systemctl restart afgooien`.

## Versies

Het versienummer staat linksonder in beeld (en in `afgooien/__init__.py`).

- **1.28**: updates vanuit de app (Instellingen → Updates): zip-bestand uploaden vanaf je telefoon/pc, of
  automatisch ophalen uit een GitHub-release; vorige versie blijft als reserve (terugzetten kan met één knop).
  De app meldt het als een update ook `install_pi.sh` opnieuw nodig heeft
- **1.27**: na een potje ook "Alle spellen" en "Hoofdmenu"; pictogrammen voor telefoon en stem als SVG (werkten
  niet op Raspberry Pi OS Lite zonder emoji-lettertype; dat wordt nu ook geïnstalleerd); aan/uit-knop rechtsboven
  op het scherm van de Pi: uitzetten of herstarten (install_pi.sh geeft daar toestemming voor, `run.py --power`)
- **1.26**: nieuw stemmenmenu (instellingen staan nu op de server, dus ook in te stellen vanaf de telefoon):
  kies Piper (offline), ElevenLabs (meest echt, met je eigen gratis sleutel), Microsoft Azure of de browserstem.
  Commentaar zoals bij een dartwedstrijd: korte uitroepen na een 180, finish, uitschakeling enz. (uit/af en
  toe/veel). Testknoppen op de telefoon laten het grote scherm praten. Na een update laadt het scherm de
  nieuwe versie vanzelf (installatiescript herstart de dienst)
- **1.25**: natuurlijke stem op de Raspberry Pi: Piper (Nederlandse en Engelse mannenstem, zonder internet)
  in plaats van de robotstem; wordt geïnstalleerd door `bash install_pi.sh` (overslaan: `--geen-stem`).
  Het stemmenmenu maakte de Pi traag (honderden espeak-stemmen): het toont nu alleen stemmen van je eigen
  taal en de browserstem wordt pas aangeraakt als je die echt gebruikt. Telefoon als volledige
  afstandsbediening: knop "Menu" op de telefoonpagina opent het hoofdmenu (alle spellen met instellingen,
  scorebord, instellingen) zonder stem; start je daar een potje, dan springt de telefoon naar de bediening
- **1.24**: groter dartbord: op een breed scherm staan de pijlen en knoppen nu naast het bord, zodat het
  bord de volle hoogte krijgt; nieuwe instelling "Breedte dartbord-kant" (standaard 65%). Sneller op de
  Raspberry Pi: lichtere prestatiemodus (geen grote schaduwen en eindeloze animaties), stemmenlijst één keer
  ophalen, Chromium tekent met de GPU, het scherm krijgt voorrang op andere programma's en de processor
  blijft op volle snelheid (opnieuw `bash install_pi.sh --lite` draaien; uitzetten met `--geen-turbo`)
- **1.23**: werkt met Autodarts 2 (2.1.0): de pijlen kwamen binnen als "Mis" omdat Autodarts 2
  de worpen in een ander formaat doorgeeft; uitgestuiterde pijlen tellen als mis op het bord
- **1.22**: telefoon: vasthouden zoomt in tot 3× (was te ver); met je vinger bij de rand schuift het
  bord mee, zodat je ingezoomd overal kunt komen
- **1.21**: telefoon: pijl met je vinger verslepen tot je loslaat; na 0,7 s vasthouden zoomt het bord
  in rond je vinger voor fijn plaatsen
- **1.20**: telefoon: vergrootglas onder je vinger (met vak-label en trilling) en automatisch inzoomen
  op de gekozen pijl, plus zoomknoppen tot 4×
- **1.19**: telefoon als bediening: QR-code (📱) koppelt je telefoon; groot bord met de 3 pijlen om
  te corrigeren of in te voeren (bord of toetsen), stand, verdelen van bonuspunten; als app op het
  startscherm te zetten
- **1.18**: Raspberry Pi: `install_pi.sh` installeert Afgooien als dienst en opent het speelscherm
  automatisch op volledig scherm bij het opstarten; stem via speech-dispatcher; `--lite` voor Raspberry Pi OS
  Lite (kiosk zonder bureaublad, snelst); prestatiemodus (automatisch op de Pi)
- **1.17**: launcher: Afgooien.bat start met één klik de server en opent Chrome als eigen venster
  (optioneel kiosk/Edge, snelkoppeling met icoon); Afgooien: een bonus (bull, bullseye, 100+) haalt
  alleen punten af als je al vóór die pijl op 5 stond
- **1.16**: Afgooien: de regel voor "af" precies gemaakt. Af ben je alleen door een andere
  speler: hij zet je op 0 (pijl of bonus), of raakt je nummer terwijl je al op 0 staat. Jezelf
  op 0 gooien (naast het bord) maakt je niet af. Wie op 0 staat verliest geen bonuspunten
- **1.15**: Afgooien: bonuspunten (bull, bullseye, 100+) gooien niemand meer af. Je kon in je
  eerste beurt winnen als de tegenstander nog op 0 stond. Nu ben je alleen af als iemand je
  nummer raakt
- **1.14**: 11 nieuwe spellen: Cricket, Killer, Shanghai, Halve-It, Golf, Gotcha, Rond de klok,
  Bob's 27, Doubles oefenen, Bullen en Random checkout; allemaal met bots, stem, NL/EN en een
  eigen scorebord; nieuwe Spelkeuze-pagina
- **1.13**: nieuwe spellen X01 (legs/sets, straight/double/master in en uit, bull-off WDF/PDC,
  uitgooi-routes) en Count Up, allebei met meerdere spelers en bots; scorebord per spel
- **1.12**: taalkeuze Nederlands / English voor de hele app, inclusief verloop, meldingen
  en stem (Engelse stem wordt automatisch gekozen); Instellingen → Weergave met zoom,
  tekstgrootte, bordgrootte, animaties aan/uit, scherm wakker houden en volledig scherm;
  stembediening ook bij Instellingen
- **1.11**: spelers opslaan (Instellingen → Spelers: toevoegen, verwijderen, stats resetten);
  opgeslagen spelers snel kiezen in de lobby; gegevens staan buiten de programmamap en blijven
  bij een nieuwe versie bewaard; lettertype gerepareerd (i zonder puntje op Windows)
- **1.10**: nieuwe vormgeving: navigatie (Home, Spelen, Scorebord), startpagina met
  statistieken, spelkeuze (met ruimte voor toekomstige spellen), lobby, groot scorepaneel,
  pijlenbalk boven het bord en bedieningsbalk eronder; lettertype Inter meegeleverd (OFL)
- **1.09**: strafpunt alleen als het hele bord gemist is (pijl in de cijferring = mis zonder
  strafpunt); bord op het scherm tot de echte buitenrand; schaal van Autodarts-coördinaten instelbaar
- **1.08**: pijl naast het bord telt nu als mis (was soms het nummer ernaast); pijlen
  corrigeren door ze aan te klikken en op het bord te zetten; logboek van alle worpen en
  correcties (data/worpen.jsonl) + tools/analyse_worpen.py; bij een afgooibeurt noemt de
  stem wie welk nummer en hoeveel punten heeft; veel groter scorebord met A−/A+
- **1.07**: probe veilig voor Autodarts 2 (vraagt geen API-sleutel op, maskeert geheimen)
- **1.06**: bots (niveau 1-6 = 0,5 tot 3,0 punten per beurt), statusring om het bord
  (groen/geel/rood) met reset-knop, extra regels per potje op het startscherm, 100+-meter
- **1.05**: scorebord met ranglijst, prijzen, "wie gooit wie af?" en potjesoverzicht;
  statistieken per speler (punten per beurt, triples/dubbels per potje, raak%, snelst op 5)
- **1.04**: versienummer in beeld
- **1.03**: caller-stem met instellingen, animaties (af, afgooier, 100+/180, bull, winnaar),
  inklapbaar verloop, geen keuzevenster bij één tegenstander
- **1.02**: buiten bord −1, bull/bullseye, 100+ = 3 punten, verdeel-venster, testversie
- **1.01**: eerste versie: Afgooien met Autodarts-koppeling

## Opbouw

```
run.py                     start + opties
afgooien/engine.py         spelregels (los te testen, geen afhankelijkheden)
afgooien/server.py         webserver + live updates (Server-Sent Events)
afgooien/sources/autodarts.py   koppeling met de Board Manager
web/                       speelscherm (HTML/CSS/JS, geen build-stap)
tools/                     probe en nep-Autodarts
tests/                     automatische tests
```
