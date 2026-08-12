import time
import datetime
import math
import sys
import board
import neopixel
import paho.mqtt.client as mqtt
import json

# set constants
numLeds = 143
msInMin = 60000
secInUur = 3600
minInDag = 720
tzOffset = 3600000
urenEnMinConfig = json.loads('{"aan": false}')
secondenConfig = json.loads('{"aan": false}')
secKleurInvConfig = json.loads('{"aan": false}')
minFrameTime = 0.033

# program constants 
order = neopixel.GRB
pixels = neopixel.NeoPixel(board.D10, numLeds, brightness=0.3, auto_write=False, pixel_order=order)
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.username_pw_set("homeassistant", "eithit6ihae5Phaet6ietoorahG3ohtaedair6pu0Thu0ahwoh4Pie1isaix3pha")
mqttc.connect("192.168.3.100", 1883, 60)
frameTimeLast = time.time()

# effecten variabelen
glowEnable = False
glowWaarde = 0.0
glowRichting = False
glowBrightness = 0.0
minutenDimEnable = False
minutenGlowEnable = False
urenDimEnable = False
urenGlowEnable = False


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("Keuken/Klok/#")

# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    global urenEnMinConfig # gebruik de globale urenEnMinConfig, in plaats van een lokale variabele
    global secondenConfig
    global secKleurInvConfig
    global tzOffset
    global pixels
    global glowEnable
    global glowBrightness
    global minutenGlowEnable
    global minutenDimEnable
    global urenGlowEnable
    global urenDimEnable
    
# Ontvang config variablen
    if msg.topic.startswith("Keuken/Klok/Config/"):   
        if msg.topic == "Keuken/Klok/Config/tijdzone":
            tzOffset = int(msg.payload)
            
        elif msg.topic == "Keuken/Klok/Config/brightness":
            pixels.brightness = float(msg.payload)
            glowBrightness = float(msg.payload)
            
        elif msg.topic == "Keuken/Klok/Config/urenEnMin":
            urenEnMinConfig = json.loads(msg.payload)
            
        elif msg.topic == "Keuken/Klok/Config/seconden":
            secondenConfig = json.loads(msg.payload)
            
        elif msg.topic == "Keuken/Klok/Config/secKleurInv":
            secKleurInvConfig = json.loads(msg.payload)
    
# Bestuur klok (meet timing of print een frame)    
    elif msg.topic.startswith("Keuken/Klok/Control/"):
        if msg.topic.startswith("Keuken/Klok/Control/Timing/"):
            if msg.topic == "Keuken/Klok/Control/Timing/minutenEnUren":
                for i in range(10):
                    timestamp = int(time.time()*1000+tzOffset)
                    updateStart = time.time_ns()
                    minutenEnUren(timestamp, 0.2, urenEnMinConfig['r1'], urenEnMinConfig['g1'], urenEnMinConfig['b1'], urenEnMinConfig['r2'], urenEnMinConfig['g2'], urenEnMinConfig['b2'])
                    updateEnd = time.time_ns()
                    print("minutenEnUren time: ", (updateEnd - updateStart)/1000000)
                
            elif msg.topic == "Keuken/Klok/Control/Timing/seconden":
                for i in range(10):
                    timestamp = int(time.time()*1000+tzOffset)
                    updateStart = time.time_ns()
                    secondewijzer(timestamp,secondenConfig['r1'],secondenConfig['g1'],secondenConfig['b1'])
                    updateEnd = time.time_ns()
                    print("seconden time: ", (updateEnd - updateStart)/1000000)
                
            elif msg.topic == "Keuken/Klok/Control/Timing/update":
                for i in range(10):
                    updateStart = time.time_ns()
                    update()
                    updateEnd = time.time_ns()
                    updateTime = int((updateEnd - updateStart) / 1000000)
                    print("Update time: ", updateTime, "fps: ", int(1000 / updateTime))
                
        elif msg.topic == "Keuken/Klok/Control/printFrame": 
            update()
            print(pixels)

# Start effecten        
        if msg.topic.startswith("Keuken/Klok/Control/Effecten/"):
            if msg.topic == "Keuken/Klok/Control/Effecten/glow":
                glowEnable = True
            elif msg.topic == "Keuken/Klok/Control/Effecten/minuten/glow":
                if msg.payload.decode('UTF-8') == "false":
                    minutenGlowEnable = False
                elif msg.payload.decode('UTF-8') == "true":
                    minutenGlowEnable = True
                
            elif msg.topic == "Keuken/Klok/Control/Effecten/minuten/dim":
                if msg.payload.decode('UTF-8') == "false":
                    minutenDimEnable = False
                elif msg.payload.decode('UTF-8') == "true":
                    minutenDimEnable = True
                    
            elif msg.topic == "Keuken/Klok/Control/Effecten/uren/glow":
                if msg.payload.decode('UTF-8') == "false":
                    urenGlowEnable = False
                elif msg.payload.decode('UTF-8') == "true":
                    urenGlowEnable = True
                    
            elif msg.topic == "Keuken/Klok/Control/Effecten/uren/dim":
                if msg.payload.decode('UTF-8') == "false":
                    urenDimEnable = False
                elif msg.payload.decode('UTF-8') == "true":
                    urenDimEnable = True
    
def on_publish(client, userdata, mid, reason_code, properties):
    # reason_code and properties will only be present in MQTTv5. It's always unset in MQTTv3
    try:
        userdata.remove(mid)
    except KeyError:
        pass

# scale number from range to range
def scale(nr, sc11, sc12, sc21, sc22):
    return (nr - sc11) * (sc22 - sc21) / (sc12 - sc11) + sc21

# Set RGB waarde op arrayindex
def setColorAtIndex(pixel,r,g,b,brightMult=1):
    pixels[pixel] = (int(min(255, r * brightMult)), 
                     int(min(255, g * brightMult)), 
                     int(min(255, b * brightMult)))

# Change brightness waarde op arrayindex
def setBrightnessAtIndex(pixel,brightMult):
    pixels[pixel] = (max(0,min(255,int(pixels[pixel][0] * brightMult))), 
                     max(0,min(255,int(pixels[pixel][1] * brightMult))), 
                     max(0,min(255,int(pixels[pixel][2] * brightMult))))

# render second hand
def secondewijzer(timestamp,r,g,b):
    msVanMin = timestamp % msInMin # ms in een minuut
    secLed = int(numLeds / msInMin * msVanMin)
    
    for i in range(secLed - 3, secLed + 4):
        led = i % numLeds

        msplace = i * msInMin // numLeds
        timeDif = abs(msVanMin - msplace)
        rgb = 0
            
        if timeDif < 1500:
            rgb = int(min(255, max(0, (scale(timeDif, 800, 0, 0, 255)))))
    
        if rgb > 0:
            pixels[led] = max(pixels[led][0], int(rgb * r)), max(pixels[led][0], int(rgb * g)), max(pixels[led][0], int(rgb * b))
            
            
# secondewijzer met inverse kleuren van urenEnMin            
def secKleurInv(timestamp,r2,g2,b2,r1,g1,b1):
    msVanMin = timestamp % msInMin # ms in een minuut
    secVanUur = int((timestamp / 1000) % secInUur) 
    minVanDag = int((timestamp % 43200000) / msInMin)
    
    secEerst = (secVanUur / secInUur) < (minVanDag / minInDag) #Bool; true als minutenwijzer voor de urenwijzer staat. (gezien vanaf 12 uur met de klok mee)

    minLed = int((numLeds / secInUur) * secVanUur)
    uurLed = int((numLeds / minInDag) * minVanDag)
    
    for i in range(numLeds):
        msplace = i * msInMin // numLeds
        timeDif = abs(msVanMin - msplace)
        rgb = 0 
            
        if timeDif < 1500:   
            rgb = int(min(255, max(0, (scale(timeDif, 800, 0, 0, 255)))))
            if rgb > 0:
                if secEerst:
                    if (i <= minLed) or (i >= uurLed):
                        setColorAtIndex(i,r1,g1,b1,rgb)
                    else:
                        setColorAtIndex(i,r2,g2,b2,rgb)
                else:
                    if (i <= minLed) and (i >= uurLed):
                        setColorAtIndex(i,r1,g1,b1,rgb)
                    else:
                        setColorAtIndex(i,r2,g2,b2,rgb)

# render minutes and hours hand
def minutenEnUren(timestamp,dalBR,r1,g1,b1,r2,g2,b2):
    secVanUur = int((timestamp / 1000) % secInUur)
    minVanDag = int((timestamp % 43200000) / msInMin)

    secEerst = (secVanUur / secInUur) < (minVanDag / minInDag)
    
    r1 = int(255 * dalBR * r1)
    g1 = int(255 * dalBR * g1)
    b1 = int(255 * dalBR * b1)
    r2 = int(255 * dalBR * r2)
    g2 = int(255 * dalBR * g2)
    b2 = int(255 * dalBR * b2)

    minLed = int((numLeds / secInUur) * secVanUur)
    uurLed = int((numLeds / minInDag) * minVanDag)

    for i in range(numLeds):
        if secEerst:
            if (i <= minLed) or (i >= uurLed):
                setColorAtIndex(i,r1,g1,b1)
            else:
                setColorAtIndex(i,r2,g2,b2)
        else:
            if (i <= minLed) and (i >= uurLed):
                setColorAtIndex(i,r1,g1,b1)
            else:
                setColorAtIndex(i,r2,g2,b2)

    if minutenGlowEnable:
        for i in range(minLed - 5, minLed + 6):
            led = i % numLeds
            secAfstand = abs(((secInUur // numLeds) * i) - secVanUur)
            felDelta = max(1, (scale(secAfstand,0,100,7,1)))
            setBrightnessAtIndex(led,felDelta)
        
    elif minutenDimEnable:
        for i in range(minLed - 5, minLed + 6):
            led = i % numLeds
            secAfstand = abs(((secInUur // numLeds) * i) - secVanUur) # hoeveelheid afstand dat de led van de huidige tijd afzit in seconde         
            felDelta = min(1, (scale(secAfstand,0,100,0,1)))
            setBrightnessAtIndex(led,felDelta)
        
    if urenDimEnable:
        for i in range(uurLed - 5, uurLed + 6):
            led = i % numLeds
            minAfstand = abs(((minInDag // numLeds) * i) - minVanDag)
            felDelta = min(1, (scale(minAfstand,0,20,0,1)))
            setBrightnessAtIndex(led,felDelta)   
        
    elif urenGlowEnable:
        for i in range(uurLed - 5, uurLed + 6):
            led = i % numLeds
            minAfstand = abs(((minInDag // numLeds) * i) - minVanDag) # eenheid leds
            felDelta = max(1, (scale(minAfstand,0,20,7,1)))
            setBrightnessAtIndex(led,felDelta)
 
# effect glow
def glow():
    global glowRichting
    global glowWaarde
    global glowEnable
    
    if glowRichting:
        if glowWaarde > 0.0:
            glowWaarde = glowWaarde - 0.01
        else:
            glowRichting = False
            glowEnable = False
    else:
        if glowWaarde < 0.5:
            glowWaarde = glowWaarde + 0.01
        else:
            glowRichting = True
        
    pixels.brightness = min(1.0, (glowBrightness + glowWaarde))

# render new frame
def update():
    timestamp = int(time.time()*1000+tzOffset)
    minVanDag = int((timestamp % 43200000) / msInMin)
    secVanUur = int((timestamp / 1000) % secInUur)

    # volledig vullend
    if urenEnMinConfig['aan']: 
     minutenEnUren(timestamp,0.2,urenEnMinConfig['r1'],urenEnMinConfig['g1'],urenEnMinConfig['b1'],urenEnMinConfig['r2'],urenEnMinConfig['g2'],urenEnMinConfig['b2'])
    else:
        for i in range(numLeds):
            pixels[i] = (0, 0, 0)

    # deels vullend
    if secondenConfig['aan']:
        secondewijzer(timestamp,secondenConfig['r1'],secondenConfig['g1'],secondenConfig['b1'])
    elif secKleurInvConfig['aan']:
        secKleurInv(timestamp,urenEnMinConfig['r1'],urenEnMinConfig['g1'],urenEnMinConfig['b1'],urenEnMinConfig['r2'],urenEnMinConfig['g2'],urenEnMinConfig['b2'])

    # niet vullend
    if glowEnable:
        glow()

    # Update leds
    pixels.show()

unacked_publish = set()
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.on_publish = on_publish
mqttc.user_data_set(unacked_publish)

mqttc.loop_start()
msg_info = mqttc.publish("Keuken/Klok/online", True, qos=1)
unacked_publish.add(msg_info.mid)

# frametimings opstarten
for i in range(10):
    updateStart = time.time_ns()
    update()
    updateEnd = time.time_ns()
    # print("totaal: ", (updateEnd - updateStart)/1000000)

msg_info.wait_for_publish()

# main loop
while True:
    frameTime = time.time()
    if (frameTime - frameTimeLast) > minFrameTime:
        update()
        frameTimeLast = frameTime

# afsluiten (wordt niet echt gebruikt)  
msg_info = mqttc.publish("Keuken/Klok/online", False, qos=1)
unacked_publish.add(msg_info.mid)
msg_info.wait_for_publish()

mqttc.loop_stop()
