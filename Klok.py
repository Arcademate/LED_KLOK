"""
LED-klok besturing
===================

Dit script stuurt een NeoPixel LED-strip aan die in een cirkel om een houten
schijf is gemonteerd, en laat 'm werken als een analoge klok: de leds
vormen samen de "wijzerplaat" en er worden virtuele uren-, minuten- en
secondewijzers overheen gerenderd door de juiste leds te kleuren.

De klok wordt op afstand bediend via MQTT (bedoeld voor Home Assistant):
  - Config-topics ("Keuken/Klok/Config/...") stellen kleuren, tijdzone en
    welke wijzers/effecten actief zijn in.
  - Control-topics ("Keuken/Klok/Control/...") schakelen effecten aan/uit
    of triggeren een debug/timing-meting.

Elk frame wordt opnieuw volledig berekend en naar de strip geschreven
(zie renderFrame()); de hoofdlus onderaan doet dat met een frame-cap zodat
de Raspberry Pi niet onnodig veel CPU gebruikt.
"""

import os
import time
import sys
import board
import neopixel
import paho.mqtt.client as mqtt
import json


# --------------------------------------------------------------------------
# Configuratie via environment variables (o.a. secrets)
# --------------------------------------------------------------------------
# Het MQTT-wachtwoord stond eerder hardcoded in dit bestand (en dus in git).
# Zet onderstaande variabelen in de omgeving waarin dit script draait, bv.
# via een systemd EnvironmentFile of `export KLOK_MQTT_PASSWORD=...` — zie
# de README voor een voorbeeld.
MQTT_HOST = os.environ.get("KLOK_MQTT_HOST", "192.168.3.100")
MQTT_PORT = int(os.environ.get("KLOK_MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("KLOK_MQTT_USERNAME", "homeassistant")
MQTT_PASSWORD = os.environ.get("KLOK_MQTT_PASSWORD")

if not MQTT_PASSWORD:
    sys.exit(
        "Environment variable KLOK_MQTT_PASSWORD is niet ingesteld. "
        "Zie README.md voor hoe je de MQTT-credentials configureert."
    )


# --------------------------------------------------------------------------
# Constanten
# --------------------------------------------------------------------------
AANTAL_LEDS = 143             # aantal leds op de strip / rond de wijzerplaat
MS_PER_MINUUT = 60_000
SEC_PER_UUR = 3_600
MIN_PER_12UUR = 720            # minuten in een volledige rondgang van de urenwijzer (12 * 60)
MS_PER_12UUR = MIN_PER_12UUR * MS_PER_MINUUT

MIN_FRAME_DUUR = 0.033         # minimale tijd (s) tussen frames -> cap van ~30 fps

PIXEL_VOLGORDE = neopixel.GRB


# --------------------------------------------------------------------------
# Hardware setup
# --------------------------------------------------------------------------
ledStrip = neopixel.NeoPixel(
    board.D10, AANTAL_LEDS, brightness=0.3, auto_write=False, pixel_order=PIXEL_VOLGORDE
)


# --------------------------------------------------------------------------
# Programmastatus (via MQTT bijgewerkt tijdens het draaien)
# --------------------------------------------------------------------------
# Tijdzone-offset in ms, wordt bijgewerkt via Config/tijdzone
tijdzoneOffsetMs = 3_600_000

# Wijzer-configuraties zoals aangeleverd door Home Assistant. Vorm:
# {"aan": bool, "r1": int, "g1": int, "b1": int, "r2": int, "g2": int, "b2": int}
# (de exacte keys liggen vast in het MQTT-contract met Home Assistant en
# blijven dus ongewijzigd)
uurMinuutConfig = {"aan": False}
secondeConfig = {"aan": False}
secondeKleurInversieConfig = {"aan": False}

# Welke visuele effecten aan staan. Dict i.p.v. losse globals, zodat we in
# on_message() niet voor elk effect een aparte `global` nodig hebben (het
# muteren van dict-items is geen herbinding van de naam zelf).
effecten = {
    "glow": False,
    "minuutGlow": False,
    "minuutDim": False,
    "uurGlow": False,
    "uurDim": False,
}

# Status van het "ademende" glow-effect (algehele helderheid golft op en neer)
glowStatus = {
    "waarde": 0.0,           # huidige opgetelde helderheid t.o.v. basisHelderheid
    "omhoog": False,         # richting van de golfbeweging
    "basisHelderheid": 0.0,  # helderheid zoals ingesteld via Config/brightness
}

laatsteFrameTijd = time.time()


# --------------------------------------------------------------------------
# MQTT callbacks
# --------------------------------------------------------------------------
def on_connect(client, userdata, flags, reason_code, properties):
    """Wordt aangeroepen zodra de verbinding met de broker tot stand komt."""
    client.subscribe("Keuken/Klok/#")


def is_effect_aan(msg):
    """Payload ("true"/"false", als bytes) omzetten naar een bool."""
    return msg.payload.decode("UTF-8") == "true"


def on_message(client, userdata, msg):
    global tijdzoneOffsetMs
    global uurMinuutConfig
    global secondeConfig
    global secondeKleurInversieConfig

    # Ontvang config variabelen
    if msg.topic.startswith("Keuken/Klok/Config/"):
        if msg.topic == "Keuken/Klok/Config/tijdzone":
            tijdzoneOffsetMs = int(msg.payload)

        elif msg.topic == "Keuken/Klok/Config/brightness":
            helderheid = float(msg.payload)
            ledStrip.brightness = helderheid
            glowStatus["basisHelderheid"] = helderheid

        elif msg.topic == "Keuken/Klok/Config/urenEnMin":
            uurMinuutConfig = json.loads(msg.payload)

        elif msg.topic == "Keuken/Klok/Config/seconden":
            secondeConfig = json.loads(msg.payload)

        elif msg.topic == "Keuken/Klok/Config/secKleurInv":
            secondeKleurInversieConfig = json.loads(msg.payload)

    # Bestuur klok (meet timing of print een frame)
    elif msg.topic.startswith("Keuken/Klok/Control/"):
        if msg.topic.startswith("Keuken/Klok/Control/Timing/"):
            if msg.topic == "Keuken/Klok/Control/Timing/minutenEnUren":
                for _ in range(10):
                    timestamp = int(time.time() * 1000 + tijdzoneOffsetMs)
                    start = time.time_ns()
                    uurEnMinuutWijzers(
                        timestamp, 0.2,
                        uurMinuutConfig["r1"], uurMinuutConfig["g1"], uurMinuutConfig["b1"],
                        uurMinuutConfig["r2"], uurMinuutConfig["g2"], uurMinuutConfig["b2"],
                    )
                    duurMs = (time.time_ns() - start) / 1_000_000
                    print("uurEnMinuutWijzers time: ", duurMs)

            elif msg.topic == "Keuken/Klok/Control/Timing/seconden":
                for _ in range(10):
                    timestamp = int(time.time() * 1000 + tijdzoneOffsetMs)
                    start = time.time_ns()
                    secondewijzer(timestamp, secondeConfig["r1"], secondeConfig["g1"], secondeConfig["b1"])
                    duurMs = (time.time_ns() - start) / 1_000_000
                    print("seconden time: ", duurMs)

            elif msg.topic == "Keuken/Klok/Control/Timing/update":
                for _ in range(10):
                    start = time.time_ns()
                    renderFrame()
                    duurMs = int((time.time_ns() - start) / 1_000_000)
                    print("Update time: ", duurMs, "fps: ", int(1000 / duurMs))

        elif msg.topic == "Keuken/Klok/Control/printFrame":
            renderFrame()
            print(ledStrip)

        # Start effecten
        elif msg.topic.startswith("Keuken/Klok/Control/Effecten/"):
            if msg.topic == "Keuken/Klok/Control/Effecten/glow":
                effecten["glow"] = True
            elif msg.topic == "Keuken/Klok/Control/Effecten/minuten/glow":
                effecten["minuutGlow"] = is_effect_aan(msg)
            elif msg.topic == "Keuken/Klok/Control/Effecten/minuten/dim":
                effecten["minuutDim"] = is_effect_aan(msg)
            elif msg.topic == "Keuken/Klok/Control/Effecten/uren/glow":
                effecten["uurGlow"] = is_effect_aan(msg)
            elif msg.topic == "Keuken/Klok/Control/Effecten/uren/dim":
                effecten["uurDim"] = is_effect_aan(msg)


def on_publish(client, userdata, mid, reason_code, properties):
    # reason_code en properties zijn alleen aanwezig bij MQTTv5, bij MQTTv3 altijd unset
    try:
        userdata.remove(mid)
    except KeyError:
        pass


# --------------------------------------------------------------------------
# Algemene hulpfuncties
# --------------------------------------------------------------------------
def herschaal(waarde, bronMin, bronMax, doelMin, doelMax):
    """Zet 'waarde' lineair om van bereik [bronMin, bronMax] naar [doelMin, doelMax]
    (zelfde idee als Arduino's map()). Extrapoleert buiten het bereik."""
    return (waarde - bronMin) * (doelMax - doelMin) / (bronMax - bronMin) + doelMin


def zetKleurOpIndex(ledIndex, r, g, b, helderheidFactor=1):
    """Zet de kleur van 1 led (overschrijft de bestaande waarde)."""
    ledStrip[ledIndex] = (
        int(min(255, r * helderheidFactor)),
        int(min(255, g * helderheidFactor)),
        int(min(255, b * helderheidFactor)),
    )


def zetHelderheidOpIndex(ledIndex, helderheidFactor):
    """Vermenigvuldig de huidige kleur van 1 led met een factor (dimmen/oplichten)."""
    r, g, b = ledStrip[ledIndex]
    ledStrip[ledIndex] = (
        max(0, min(255, int(r * helderheidFactor))),
        max(0, min(255, int(g * helderheidFactor))),
        max(0, min(255, int(b * helderheidFactor))),
    )


def secondeIntensiteit(ledMsPositie, msInHuidigeMinuut):
    """
    Felheid (0-255) van de 'komeetstaart' van de secondewijzer voor een led
    die (bij gelijkmatige verdeling over de cirkel) op ledMsPositie ms in de
    minuut zou staan. Binnen 1500ms van de actuele secondepositie licht een
    led op, met een naar 0 aflopende felheid naarmate de afstand toeneemt.
    """
    tijdVerschil = abs(msInHuidigeMinuut - ledMsPositie)
    if tijdVerschil >= 1500:
        return 0
    return int(min(255, max(0, herschaal(tijdVerschil, 800, 0, 0, 255))))


# --------------------------------------------------------------------------
# Wijzer-rendering
# --------------------------------------------------------------------------
def secondewijzer(timestamp, r, g, b):
    """Render de secondewijzer als een komeetstaart van ~7 leds in kleur (r,g,b)."""
    msInHuidigeMinuut = timestamp % MS_PER_MINUUT
    secLed = int(AANTAL_LEDS / MS_PER_MINUUT * msInHuidigeMinuut)

    # We hoeven niet over alle leds te lopen: buiten dit venster is de
    # felheid altijd 0 (zie secondeIntensiteit). i mag hier buiten
    # [0, AANTAL_LEDS) vallen -> dat geeft de wraparound bij het rond de
    # klok (bv. rond het 12-uur-punt) via ledMsPositie op natuurlijke wijze.
    for i in range(secLed - 3, secLed + 4):
        led = i % AANTAL_LEDS
        ledMsPositie = i * MS_PER_MINUUT // AANTAL_LEDS
        felheid = secondeIntensiteit(ledMsPositie, msInHuidigeMinuut)

        if felheid > 0:
            # Meng met de bestaande kleur (uren/minutenwijzer) i.p.v. die te
            # overschrijven, zodat de secondewijzer er "bovenop" ligt.
            # LET OP (bestaand gedrag, ongewijzigd): hieronder wordt voor
            # alle drie de kanalen vergeleken met het RODE kanaal
            # (bestaand[0]) i.p.v. het eigen kanaal ([0]/[1]/[2]). Dat lijkt
            # een kopieerfout in de originele code, met als gevolg dat de
            # kleurmenging niet helemaal is zoals bedoeld. Laat het weten als
            # dit gefixt moet worden.
            bestaand = ledStrip[led]
            ledStrip[led] = (
                max(bestaand[0], int(felheid * r)),
                max(bestaand[0], int(felheid * g)),
                max(bestaand[0], int(felheid * b)),
            )


def secondeKleurInversie(timestamp, r2, g2, b2, r1, g1, b1):
    """
    Alternatief voor secondewijzer(): de komeetstaart krijgt hier steeds de
    kleur van de wijzer (uur/minuut) die op dat punt van de wijzerplaat NIET
    zichtbaar is, zodat de secondewijzer altijd contrasteert met de
    ondergrond i.p.v. een vaste eigen kleur te hebben.

    Noot voor later: deze functie doorloopt (anders dan secondewijzer())
    alle AANTAL_LEDS leds per frame, omdat de exacte 1500ms-afstandsgrens zo
    op elke led precies wordt toegepast. Als dat niet nodig is, kan dit net
    als secondewijzer() met een klein venster rond secLed geoptimaliseerd
    worden — dat verandert wel de randgevallen rond het 12-uur-punt licht
    t.o.v. het huidige gedrag, dus bewust (nog) niet doorgevoerd.
    """
    msInHuidigeMinuut = timestamp % MS_PER_MINUUT
    secInHuidigUur = int((timestamp / 1000) % SEC_PER_UUR)
    minInKlokrond = int((timestamp % MS_PER_12UUR) / MS_PER_MINUUT)

    # True als de minutenwijzer nu vóór de urenwijzer staat (met de klok
    # mee gezien vanaf 12 uur)
    minutenVoorUren = (secInHuidigUur / SEC_PER_UUR) < (minInKlokrond / MIN_PER_12UUR)

    minLed = int((AANTAL_LEDS / SEC_PER_UUR) * secInHuidigUur)
    uurLed = int((AANTAL_LEDS / MIN_PER_12UUR) * minInKlokrond)

    for i in range(AANTAL_LEDS):
        ledMsPositie = i * MS_PER_MINUUT // AANTAL_LEDS
        felheid = secondeIntensiteit(ledMsPositie, msInHuidigeMinuut)
        if felheid == 0:
            continue

        if minutenVoorUren:
            binnenBoog = (i <= minLed) or (i >= uurLed)
        else:
            binnenBoog = (i <= minLed) and (i >= uurLed)

        if binnenBoog:
            zetKleurOpIndex(i, r1, g1, b1, felheid)
        else:
            zetKleurOpIndex(i, r2, g2, b2, felheid)


def renderWijzerRandeffect(centrumLed, huidigeTijdWaarde, tijdPerRonde, afstandBereik, felheidBereik, clampFunctie):
    """
    Gedeelde implementatie voor de "glow"/"dim"-rand rond de uren- en
    minutenwijzer: de 11 leds rond centrumLed krijgen een helderheid die
    lineair afneemt naarmate ze verder van de wijzer af staan.

    afstandBereik / felheidBereik: (van, naar) voor herschaal().
    clampFunctie: min(1, ...) voor dim-effecten, max(1, ...) voor glow-effecten.
    """
    for i in range(centrumLed - 5, centrumLed + 6):
        led = i % AANTAL_LEDS
        afstand = abs(((tijdPerRonde // AANTAL_LEDS) * i) - huidigeTijdWaarde)
        felheidFactor = clampFunctie(herschaal(afstand, afstandBereik[0], afstandBereik[1], felheidBereik[0], felheidBereik[1]))
        zetHelderheidOpIndex(led, felheidFactor)


def uurEnMinuutWijzers(timestamp, dalBrightness, r1, g1, b1, r2, g2, b2):
    """Render de uren- en minutenwijzer als twee gekleurde bogen die de hele
    wijzerplaat vullen, plus optioneel een glow/dim-rand op de wijzerpunten."""
    secInHuidigUur = int((timestamp / 1000) % SEC_PER_UUR)
    minInKlokrond = int((timestamp % MS_PER_12UUR) / MS_PER_MINUUT)

    minutenVoorUren = (secInHuidigUur / SEC_PER_UUR) < (minInKlokrond / MIN_PER_12UUR)

    # Basiskleuren gedimd met dalBrightness (de "nacht"-helderheid van de vlakken)
    dimR1, dimG1, dimB1 = int(255 * dalBrightness * r1), int(255 * dalBrightness * g1), int(255 * dalBrightness * b1)
    dimR2, dimG2, dimB2 = int(255 * dalBrightness * r2), int(255 * dalBrightness * g2), int(255 * dalBrightness * b2)

    minLed = int((AANTAL_LEDS / SEC_PER_UUR) * secInHuidigUur)
    uurLed = int((AANTAL_LEDS / MIN_PER_12UUR) * minInKlokrond)

    for i in range(AANTAL_LEDS):
        if minutenVoorUren:
            binnenBoog = (i <= minLed) or (i >= uurLed)
        else:
            binnenBoog = (i <= minLed) and (i >= uurLed)

        if binnenBoog:
            zetKleurOpIndex(i, dimR1, dimG1, dimB1)
        else:
            zetKleurOpIndex(i, dimR2, dimG2, dimB2)

    if effecten["minuutGlow"]:
        renderWijzerRandeffect(minLed, secInHuidigUur, SEC_PER_UUR, (0, 100), (7, 1), lambda x: max(1, x))
    elif effecten["minuutDim"]:
        renderWijzerRandeffect(minLed, secInHuidigUur, SEC_PER_UUR, (0, 100), (0, 1), lambda x: min(1, x))

    if effecten["uurDim"]:
        renderWijzerRandeffect(uurLed, minInKlokrond, MIN_PER_12UUR, (0, 20), (0, 1), lambda x: min(1, x))
    elif effecten["uurGlow"]:
        renderWijzerRandeffect(uurLed, minInKlokrond, MIN_PER_12UUR, (0, 20), (7, 1), lambda x: max(1, x))


# --------------------------------------------------------------------------
# Effecten
# --------------------------------------------------------------------------
def werkGlowEffectBij():
    """Laat de algehele helderheid langzaam op en neer 'ademen' tussen de
    basishelderheid en +0.5, en weer terug (eenmalig, daarna zichzelf uit)."""
    if glowStatus["omhoog"]:
        if glowStatus["waarde"] > 0.0:
            glowStatus["waarde"] -= 0.01
        else:
            glowStatus["omhoog"] = False
            effecten["glow"] = False
    else:
        if glowStatus["waarde"] < 0.5:
            glowStatus["waarde"] += 0.01
        else:
            glowStatus["omhoog"] = True

    ledStrip.brightness = min(1.0, glowStatus["basisHelderheid"] + glowStatus["waarde"])


# --------------------------------------------------------------------------
# Frame rendering
# --------------------------------------------------------------------------
def renderFrame():
    """Bereken en toon één volledig frame op basis van de huidige tijd en
    ingestelde configuratie/effecten."""
    timestamp = int(time.time() * 1000 + tijdzoneOffsetMs)

    # volledig vullend
    if uurMinuutConfig["aan"]:
        uurEnMinuutWijzers(
            timestamp, 0.2,
            uurMinuutConfig["r1"], uurMinuutConfig["g1"], uurMinuutConfig["b1"],
            uurMinuutConfig["r2"], uurMinuutConfig["g2"], uurMinuutConfig["b2"],
        )
    else:
        ledStrip.fill((0, 0, 0))

    # deels vullend
    if secondeConfig["aan"]:
        secondewijzer(timestamp, secondeConfig["r1"], secondeConfig["g1"], secondeConfig["b1"])
    elif secondeKleurInversieConfig["aan"]:
        secondeKleurInversie(
            timestamp,
            uurMinuutConfig["r1"], uurMinuutConfig["g1"], uurMinuutConfig["b1"],
            uurMinuutConfig["r2"], uurMinuutConfig["g2"], uurMinuutConfig["b2"],
        )

    # niet vullend
    if effecten["glow"]:
        werkGlowEffectBij()

    # Update leds
    ledStrip.show()


# --------------------------------------------------------------------------
# MQTT client opzetten en verbinden
# --------------------------------------------------------------------------
mqttClient = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttClient.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqttClient.connect(MQTT_HOST, MQTT_PORT, 60)

onbevestigdeBerichten = set()
mqttClient.on_connect = on_connect
mqttClient.on_message = on_message
mqttClient.on_publish = on_publish
mqttClient.user_data_set(onbevestigdeBerichten)

mqttClient.loop_start()
statusBericht = mqttClient.publish("Keuken/Klok/online", True, qos=1)
onbevestigdeBerichten.add(statusBericht.mid)

# frametimings opstarten (LED-driver "warm laten lopen" voor de eerste echte frames)
for _ in range(10):
    renderFrame()

statusBericht.wait_for_publish()

# --------------------------------------------------------------------------
# Hoofdlus
# --------------------------------------------------------------------------
while True:
    frameTijd = time.time()
    if (frameTijd - laatsteFrameTijd) > MIN_FRAME_DUUR:
        renderFrame()
        laatsteFrameTijd = frameTijd

# afsluiten (wordt niet echt gebruikt, want de lus hierboven stopt nooit)
statusBericht = mqttClient.publish("Keuken/Klok/online", False, qos=1)
onbevestigdeBerichten.add(statusBericht.mid)
statusBericht.wait_for_publish()

mqttClient.loop_stop()
