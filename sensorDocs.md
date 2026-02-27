# Sensor documentation

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

# Farbe von Atomanlagen:
Nuclear research reactor: kleiner vollfarbiger Kreis, farbe: rgb(159, 0, 195)
kernkraftwerk: rgb(232, 0, 0)
Stillgelegte AKW: kreisförmig mit rgb(232, 0, 0), Mitte weiß (siehe karte) 

# Umrechnung CMP in Mikrosievert: 
==> die Umrechnung cpm in µSv wird in dem Webseiten-Programm gemacht, die Konstante ist für jedes Rohr hinterlegt:
	 let sv_factor = {'SBM-20': 1 / 2.47, 'SBM-19': 1 / 9.81888, 'Si22G': 0.081438, 'J306': 0.06536};
Umrechnung dann:
	let uSvph = value < 0 ? -1 : value / 60 * sv_factor[x.name];         x.name ist der Name des Rohres aus dem Array sv_factor

# Darstellung der Kurven: pro Sensor: 
Standartdarstellung, wenn man auf den Sensorbutton klickt: Strahlung über einen Tag (24 h )
über Buttons oben links kann man umschalten: Strahlung 30 Tage, 7 Tage. 
