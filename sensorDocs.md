# Sensor documentation

# aktuelle Arbeitsversion: 
https://radiation.ok-lab-karlsruhe.de/

# Einbindung in die Ecocurious-Seite (über iframe vom alten/neue Server)
https://ecocurious.de/multigeiger-karte/
Die Seite ist aktuell mit Rand eingebunden. Es wäre gut, wenn wir die neue Darstellung rechts und links randlos einbinden können 

# Sensortypen: 
Es gibt 3 verschiedenen Zählrohrtypen: Si22g, SDM19 und SDM20. 
Reinhard: Ich würde sagen immer wenn ein Sensor das Wort "radiation" mit drin hat ist es einer von uns. Siehe:
https://archive.sensor.community/2026-02-02/

# Farbe der Open-Steetmap-Karte: 
Bitte wieder das dezente grau! 

# Farbe der Sensorsymbole auf der Karte in Anhängigkeit vom gemessenen Strahlungswert: 
größer als 5 µSv: rgb(163, 47, 246)
2 µSv: rgb(193, 47, 178)
0,5 µSv: rgb(243, 57, 47)
0,2: rgb(243, 248, 48)
0,1: rgb(128, 245, 122)
0,05: rgb(82, 153, 104)
offline: rgb(149, 149, 149)
indoor: rgb(173, 211, 234)
gleitende Übergänge zwischen den Farben 

Frage an Reinhard: Die gleitende Farbskala bei den Sensor-Radiation-Buttons, wie hast du die programmiert (von grün nach rot)?  ==> das ist mit der Library D3.js erzeugt. Da gibt es sicher was ähnliches für Python.

# Farbe von Atomanlagen:
Nuclear research reactor: kleiner vollfarbiger Kreis, farbe: rgb(159, 0, 195)
kernkraftwerk: rgb(232, 0, 0)
Stillgelegte AKW: kreisförmig mit rgb(232, 0, 0), Mitte weiß (siehe karte) 

# Umrechnung CPM in Mikrosievert: 
Reinhard: ==> die Umrechnung cpm in µSv wird in dem Webseiten-Programm gemacht, die Konstante ist für jedes Rohr hinterlegt: let sv_factor = {'SBM-20': 1 / 2.47, 'SBM-19': 1 / 9.81888, 'Si22G': 0.081438, 'J306': 0.06536};
Umrechnung dann: let uSvph = value < 0 ? -1 : value / 60 * sv_factor[x.name];  x.name ist der Name des Rohres aus dem Array sv_factor
(in der Mail vom 4.2.2026 von Reinhard)

# Darstellung der Kurve pro Sensor: 
Standartdarstellung, wenn man auf den Sensorbutton klickt: "Strahlung über einen Tag" (24 h ) . Über Buttons oben links kann man umschalten: Strahlung 30 Tage, 7 Tage. Es gibt also 3 verschiedenen Darstellungen. 
Bitte Überschriften "Strahlung über einen Tag,  Impulse pro Minute (bzw. Mikrosievert pro Stunde)" übernehmen 
Die y-Achse zeigt aktuell Werte von 0,1-0,175 Mikrosievert. Die x-Achse zeigt die Uhrzeit in 3h-Abständen (wie die Skala/y-Achse sich bei erhöhter Strahlung automatisch aufweitet (also wie es programmiert wird), müßte Reinhard wissen). 
Es gibt die gemessenen Werte ("alle Werte") in einer hellgrünen Kurse und den gleitenden Mittelwert über 1 h in einer dunkelgründen Kurse. Klickt man auf diese, erscheint der Zahlenwert. Beides wird unterhalb der Kurve in einer Legende erläutert. der aktuelle Messwert wird nochmal in einer kleinen Tabelle links unten im Kurvenfenster dargestellt. Über "Ende" schließen wir das Fenster wieder 

# Radonpeaks: 
Mit den Skalen, so wie Reinhard sie gewählt hat, kann man den Radonpeak gut erkennen. Daher ist es gut, sie so beizubehalten. 

# Wie lange sollen Messwerte archiviert werden? 
Andreas: Darstellung Messwerte: Reicht es, die Historie von einer Woche vorzuhalten? Ich fände das ok. 
Jürgen: => Verstehe ich das richtig? Danach sollen die Werte dann bei uns gelöscht werden? Wenn ja: Ich fände eine Woche schon sehr knapp. Damit ist es ja kaum möglich einen langsamen Anstieg zu sehen. 
Reinhard: ==> Auch ich halte ein Woche für viel zu wenig. Wenn nur noch die Geigerwerte (und nicht alle Feinstaubwert, so wie bei mir) gelesen werden müssen, ist das Halten der Werte für 1 Jahr m.E. kein Problem 

# Datenspeicherung/Download durch User 
Reicht es, wenn User sich dann von einer Woche die Stundenmittelwerte abrufen und speichern könnten? 
Jürgen: => Bei Stundenmittelwerte sieht man die Radon-Peaks nicht mehr richtig. Von dem her fände ich das schwierig. 
Reinhard: ==> bin der gleichen Meinung
Jürgen: Es ist wichtig, dass die Daten vom Sensor weiterhin ihren gewohnten und etablierten Weg gehen und dann, nach wie vor, auch bei luftdaten.info archiviert werden. Daran wollen wir auf keinen Fall etwas ändern. Laut meinem Verständnis holt Reinhard bzw. Andreas die Daten parallel ab über ein Programmierinterface (API). Das wird in eine parallele Datenbank gegeben und dann visualisiert. 
Reinhard: ==> genau so funktioniert das bei mir und so würde ich es auch weiter handhaben. Wenn wir nicht zu sensor.community senden, muss ja auch die Firmware angepasst werden.

# neuer Server: 
er muss all 5 min die Werte von sensor.community abholen und selber in eine Datenbank schreiben, die dann für die Web-Darstellung ausgelesen wird

Andreas: Warum wird im 5-Minuten-Intervall ausgelesen, ist nur Counts_pro_minute wichtig oder auf hv-pulses, was ist sample_time.
Reinhard: ==> Wichtig sind nur die counts_pro_minute. Hv_pulses ist zum Debugger und sample-time sind immer etwa die 150sec


# Gesamtkarte/Wahlmöglichkeiten für die Nutzer/Legende: 
Links oben kann über den Button "Zählrohre" der Nutzer einstellen, on er nur die Si22G-Rohre sehen will oder alle. Über den Button "AKWs/Anlagen" kann der Nutzer aktive, stillgelegte und sonstige Kraftwerke anzeigen lassen. Über den Button "Wind" kann er die aktuellen Windrichtungen und Windströme zuschalten, Über eine Suchmaske 
Unter dem Button "Info" steht wichtiges zur Karte, das sollten wir übernehmen: 

# Allgemein
Auf der Karte wird jede Zählstation mit dem Radioaktivitäts-Symbol angezeigt. Die Farbe des Symbols ändert sich mit der Zählrate, der Zusammenhang ist rechts oben in der Legende dargestellt.
Hat der Sensor seit mind. 1 Stunde keine Daten mehr gesendet, so wird er dunkelgrau eingefärbt. Hat er über eine Woche nicht gesendet, wird er nicht mehr dargestellt.
Die Karte ist standardmäßig auf Stuttgart ausgerichtet. Wenn der Aufruf der Webseite mit einer Stadt erfolgt (z.B: https://multigeiger.citysensor.de/Berlin), so wird die Karte auf diese Stadt zentriert.
Wird statt dessen eine Sensornummer angegeben, so wird die Karte auf diesen Sensor zentriert und gleich die zugehörige Grafik angezeigt (z.B. für den Sensor Nr. 34188 ist der Aufruf dann: https://multigeiger.citysensor.de/34188).
Bedienelemente

Die Karte kann mit dem Mausrad oder den beiden Knöpfen +/- in der linken obere Ecke ein- und ausgezoomed werden.Mit gedrückter Maustaste läßt sich die Karte verschieben.

Über der Karte befindet sich die Navigationsleiste mit folgenden Knöpfen/Eingabefeldern:

    Zählrohre
    Hier wird umgeschaltet, ob alle Sensoren oder nur die Sensoren, die ein Si22G-Zählrohr haben, angezeigt werden.
    AKEs/Anlagen
    Hier kann ausgewählt werden, welche Kraftwerke bzw. andere Nuklear-Anlagen angezeigt werden.
    Wind
    Hier kann der Wind-Layer ein- und ausgeschaltet werden. Beim Start wird die Karte ohne Wind angezeigt.
    Legende
    Damit wird die Legende ein- oder und ausgeblendet.
    Ort oder Sensornummer suchen
    In dieses Eingabefeld kann ein Ort oder eine Sensornummer eingegeben werden. Die Karte wird dann darauf zentriert.
    Info
    Es erscheint diese Info-Seite.

Ein Klick auf das Radioaktivitäts-Symbol bringt eine Info-Tafel zur Anzeige. Auf dieser Tafel stehen folgende Informationen:

    Sensor-Nummer
    Typ des Zählrohres
    Adresse des Sensors (falls in der Datenbank vorhanden)
    Aktueller Messwert in cpm (Impulse pro Minute) und µSv/h (Micro-Sievert pro Stunde)
    Link Grafik anzeigen

Außer den Sensoren werden auch die Kernkraftwerke (AKW) angezeigt. Aktive AKWs werden rot, sillgelegte werden als roter Ring und sonstige Nuklearanlagen werden in violett dargestellt.

Ein Klick auf ein AKW-Symbol bringt eine kleine Info-Tafel mit folgenden Daten zur Anzeige:

    Name des Kraftwerkes
    Baujahr (wenn bekannt)
    Datum der Stilllegung (falls das AKW stillgelegt ist/wird)
    Bei den anderen Anlagen die Art der Anlage

Quellen:
Die Daten für die Kerkraftwerke stammen aus folgenden Quellen:

    Wikipedia(Liste der Kernkraftwerke)
    Wikipedia(Kernenergie nach Ländern)
    Power Reactor Information System(aktuelle Infos zu AKWs weltweit)
    AtomkraftwerkePlag(Rechercheplattform zur Atomenergie)

Besten Dank an Ralf Wessels, der die Daten gesammelt und zur Verfügung gestellt hat.

Grafik

Durch Klick auf Grafik anzeigen öffnet sich ein Fenster, das den Verlauf der letzten 24 Stunden anzeigt. Es werden alle Messwerte (Wert alle 2.5min) angezeigt und zusätzlich ein gleitender Mittelwert. Der Zeitbereich für diesen Mittelwerrt kann über Einstellung im Bereich von 10min bis 6 Stunden geändert werden. Zusätzlich kann über das Einstell-Menü ein Langzeitmittelwert (48h bis 120h) mit Bereichsgrenzen (+/-5% bis +/-50%) eingeblendet werden.
Über die Knöpfe -24h -12h +12h +24h kann der Zeitstrahl um die jeweilige Anzahl an Stunden verschoben werden.
Der Knopf live schaltet wieder auf den Live-Mode um, d.h. es werden wieder die Daten der letzten 24 Stunden angezeigt.

Über den Knopf 7d kann der Verlauf einer ganzen Woche betrachtet werden. Auch hier kann der Zeitstrahl verschoben werden, und zwar um 3 bzw. 7 Tage. Außerdem kann über den Einstellung-Knopf festgelegt werden, über welchen Zeitraum die Werte gemittelt werden und ob eine gleitende oder statische Mittelwertbildung durchgeführt werden soll.

Über den Knopf 30d wird die Darstellung der Tagesmittelwerte jeden Tages der letzten 30 Tage als Balken-Diagramm angezeigt.
Durch Klick auf den Knopf Ende wird die Grafik verlassen.





