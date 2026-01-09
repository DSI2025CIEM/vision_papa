#distancia_gps.py
import serial
import pynmea2
import csv
import math
from datetime import datetime
import time

# === CONFIGURACIÓN DEL GPS ===
PORT = 'COM6'
# Cambia por el puerto donde está tu GPS (ej. /dev/ttyUSB0)
BAUDRATE = 115200      # Puede ser 115200 según configuración
# === PARÁMETROS DE DISTANCIA ===
DISTANCIA_UMBRAL = 1.13  # metros

# === ARCHIVO CSV ===
csv_filename = f"gps_trayectoria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
with open(csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Hora", "Latitud", "Longitud", "Distancia desde último punto (m)", "Distancia acumulada (m)"])

# === FUNCIÓN HAVERSINE ===
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # Radio de la Tierra (m)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# === CONEXIÓN SERIAL ===
ser = serial.Serial(PORT, BAUDRATE, timeout=1)
punto_inicial = None
distancia_total = 0.0

print(f"📡 Leyendo coordenadas del GPS 7000 en {PORT}...")
print("Guardando un punto cada 1.13 m de desplazamiento.\nPresiona Ctrl + C para detener.\n")

try:
    while True:
        line = ser.readline().decode('ascii', errors='replace').strip()
        if not line.startswith('$GPGGA'):
            continue
        
        try:
            msg = pynmea2.parse(line)
            lat = msg.latitude
            lon = msg.longitude

            if lat == 0 or lon == 0:
                continue  # ignorar lecturas sin señal

            # Primer punto
            if punto_inicial is None:
                punto_inicial = (lat, lon)
                tiempo = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"📍 Punto inicial -> Lat: {lat:.6f}, Lon: {lon:.6f}")
                with open(csv_filename, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([tiempo, lat, lon, 0.0, 0.0])
                continue

            # Calcular distancia desde el último punto guardado
            distancia = haversine(punto_inicial[0], punto_inicial[1], lat, lon)

            # Si supera el umbral, registrar el nuevo punto
            if distancia >= DISTANCIA_UMBRAL:
                distancia_total += distancia
                punto_inicial = (lat, lon)
                tiempo = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"✅ Movimiento detectado: {distancia:.2f} m | Total: {distancia_total:.2f} m")
                print(f"   Nueva posición guardada -> Lat: {lat:.6f}, Lon: {lon:.6f}")

                with open(csv_filename, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([tiempo, lat, lon, round(distancia, 3), round(distancia_total, 3)])

            time.sleep(0.2)  # evitar sobrecarga de CPU

        except pynmea2.ParseError:
            pass

except KeyboardInterrupt:
    print("\n🛑 Lectura detenida por el usuario.")
    ser.close()
    print(f"📁 Datos guardados en '{csv_filename}'")
