# LED_KLOK

Een analoge klok gemaakt van een NeoPixel LED-strip rond een houten schijf,
aangestuurd door een Raspberry Pi (`Klok.py`). De klok wordt op afstand
bediend via MQTT, bedoeld om te koppelen aan Home Assistant.

## Configuratie

De MQTT-credentials staan **niet** in de code, maar worden via environment
variables aangeleverd:

| Variabele            | Verplicht | Standaard         | Omschrijving                    |
|-----------------------|-----------|--------------------|----------------------------------|
| `KLOK_MQTT_HOST`      | nee       | `192.168.3.100`    | IP/hostname van de MQTT-broker  |
| `KLOK_MQTT_PORT`      | nee       | `1883`             | Poort van de MQTT-broker        |
| `KLOK_MQTT_USERNAME`  | nee       | `homeassistant`    | MQTT-gebruikersnaam             |
| `KLOK_MQTT_PASSWORD`  | **ja**    | —                  | MQTT-wachtwoord                 |

Zonder `KLOK_MQTT_PASSWORD` stopt het script direct met een duidelijke
foutmelding.

### Lokaal draaien

```bash
export KLOK_MQTT_PASSWORD="jouw-mqtt-wachtwoord"
python3 Klok.py
```

### Als systemd service

Zet de variabelen in een environment file (bv. `/etc/led-klok.env`, met
beperkte leesrechten: `chmod 600`):

```
KLOK_MQTT_HOST=192.168.3.100
KLOK_MQTT_USERNAME=homeassistant
KLOK_MQTT_PASSWORD=jouw-mqtt-wachtwoord
```

En verwijs ernaar vanuit de service unit:

```ini
[Service]
EnvironmentFile=/etc/led-klok.env
ExecStart=/usr/bin/python3 /pad/naar/Klok.py
```

> **Let op:** het wachtwoord stond eerder hardcoded in `Klok.py` en is dus
> ooit naar de git-historie gepusht. Overweeg dit wachtwoord op de
> MQTT-broker te wijzigen, ook al staat het niet meer in de huidige code.
