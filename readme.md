# Migrate from multigeiger projekt to newer/simpler version

References: 

https://ecocurious.de/projekte/multigeiger-2/

website
https://multigeiger.citysensor.de/



## api or data sources
### sensors
https://multigeiger.citysensor.de/mapdata/getaktdata?box=

```json
{"avgs":[{"location":[9.15962714069,48.77895659073],"id":31122,"lastSeen":"2025-12-20T15:46:19.000Z","name":"Si22G","indoor":0,"cpm":"82"},{"location":[9.024,48.682],"id":41135,"lastSeen":"2025-12-20T15:46:07.000Z","name":"Si22G","indoor":0,"cpm":"101"},{"location":[7.902,48.05],"id":40475,"lastSeen":"2024-05-10T11:21:00.000Z","name":"Si22G","indoor":0,"cpm":-2},{"location":[9.11,48.734],"id":39976,"lastSeen":"2025-12-07T20:57:21.000Z","name":"Si22G","indoor":0,"cpm":-2},{"location":[8.904,48.68],"id":34188,"lastSeen":"2021-01-05T08:38:04.000Z","name":"Si22G","indoor":0,"cpm":-2},{"location":[13.188,52.558],"id":33144,"lastSeen":"2022-04-17T22:27:57.000Z","name":"SBM-20","indoor":0,"cpm":-2},{"location":[9.29,49.064],"id":43293,"lastSeen":"2021-09-30T20:34:34.000Z","name":"Si22G","indoor":0,"cpm":-2},{"location":[7.26443138638,47.1465504],"id":35253,"lastSeen":"2025-12-20T15:45:04.000Z","name":"Si22G","indoor":1,"cpm":"105"},{"location":[9.242,48.674],"id":41675,"lastSeen":"2025-12-20T15:46:21.000Z","name":"Si22G","indoor":0,"cpm":"81"}, ...
],
"lastDate":"2025-12-20T15:52:01.000Z"}
```

### nuclear stations
https://multigeiger.citysensor.de/mapdata/getakwdata?box%5B0%5D%5B%5D=8.160095214843752&box%5B0%5D%5B%5D=48.37175998050947&box%5B1%5D%5B%5D=10.199432373046877&box%5B1%5D%5B%5D=49.182601048138054

> nuclearStations.json


### wind
https://maps.sensor.community/data/v1/wind.json

```json
[{"header":{"discipline":0,"disciplineName":"Meteorological products","gribEdition":2,"gribLength":281758,"center":7,"centerName":"US National Weather Service - NCEP(WMC)","subcenter":0,"refTime":"2025-12-20T06:00:00.000Z","significanceOfRT":1,"significanceOfRTName":"Start of forecast","productStatus":0,"productStatusName":"Operational products","productType":1,"productTypeName":"Forecast products","productDefinitionTemplate":0,"productDefinitionTemplateName":"Analysis/forecast at horizontal level/layer at a point in time","parameterCategory":2,"parameterCategoryName":"Momentum","parameterNumber":2,"parameterNumberName":"U-component_of_wind","parameterUnit":"m.s-1","genProcessType":2,"genProcessTypeName":"Forecast","forecastTime":0,"surface1Type":103,"surface1TypeName":"Specified height level above ground","surface1Value":10.0,"surface2Type":255,"surface2TypeName":"Missing","surface2Value":0.0,"gridDefinitionTemplate":0,"gridDefinitionTemplateName":"Latitude_Longitude","numberPoints":259920,"shape":6,"shapeName":"Earth spherical with radius of 6,371,229.0 m","gridUnits":"degrees","resolution":48,"winds":"true","scanMode":0,"nx":720,"ny":361,"basicAngle":0,"lo1":0.0,"la1":90.0,"lo2":359.5,"la2":-90.0,"dx":0.5,"dy":0.5},"data":[-7.3500648,-7.3500648,-7.3500648,-7.3400645,-7.3400645,-7.330065,-7.3200645,-7.3200645,-7.310065,-7.3000646,-7.290065,-7.2800646,-7.270065,-7.2600646,-7.250065,-7.2400646,-7.230065,-7.2200646,-7.210065,-7.190065,-7.1800647,-7.1600647,-7.1500645,-7.1300645,-7.1200647,-7.1000648,-7.080065, ...
``` 

> wind.json

see also: https://www.weather.gov/documentation/services-web-api


#### Wind from ECMFW


https://www.ecmwf.int/en/forecasts/datasets/open-data
https://charts.ecmwf.int/products/medium-wind-100m?base_time=202512220000&projection=opencharts_europe&valid_time=202512220000

https://pypi.org/project/ecmwf-opendata/


The following wording shall be attached to the services created with this ECMWF data product:

    Copyright statement: Copyright "This service is based on data and products of the European Centre for Medium-Range Weather Forecasts (ECMWF)".
    Source www.ecmwf.int
    Licence Statement: This ECMWF data is published under a Creative Commons Attribution 4.0 International (CC BY 4.0). https://creativecommons.org/licenses/by/4.0/
    Disclaimer: ECMWF does not accept any liability whatsoever for any error or omission in the data, their availability, or for any loss or damage arising from their use.
    Where applicable, an indication if the material has been modified and an indication of previous modifications



## code

Tested with python3.12 and python3.13. 

Replace python3.12 with whatever python you use


### 1) Create sqlite database
**To be replaced with mariadb, postgres, something else**

make sure file data/radiation_relevant_schema.json  exists

run createDb.sh

should create data/radiation.db 

### 2) Run Daemon once for testing

make sure files data/sensor_types.json and data/measurement_items.json exist

run python3.12 luftApiDaemon.py 

should update database and write some files data directory.

check data/radiation.csv and data/radiation.geojson

### 3) Run analysis

make sure database exists

run python3.12 luftSequence.py

should write timeseries gor 2 periods (day, month) for each sensor to data/series_<period>_\<sensor_id\>.json

should write plot for first 10 sensors to data/series_\<sensor_id\>.png if param -png given

### 4) Install crontab
*/5 * * * * cd \<directory\> && /usr/bin/python3.12 \<directory\>/luftApiDaemon.py >> \<directory\>/luftApiDaemon.log 2>&1

replace log with /dev/null if desired 
install luftsequence in similar fashion, use like every 33minutes instead of every 5
