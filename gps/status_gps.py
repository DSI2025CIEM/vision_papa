import serial
import pynmea2
import csv
import time
import os
import math
from datetime import datetime

# === CONFIGURACIÓN DEL PUERTO SERIAL ===
PORT = 'COM3'       # Cambia según tu sistema
BAUDRATE = 9600     # Cambia si el GPS usa otra velocidad

# === RUTA DE SALIDA ===
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "csv_gps")
os.makedirs(desktop_path, exist_ok=True)

csv_filename = os.path.join(desktop_path, f"gps_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

# Crear archivo CSV con encabezados
with open(csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(["Hora local", "Direccion (°)", "Latitud", "Longitud", "Velocidad (km/h)", "Estatus"])

print(f"📡 Iniciando lectura del GPS en {PORT}...")
print(f"📁 Guardando datos en: {csv_filename}")
print("Presiona Ctrl + C para detener.\n")

# === CONEXIÓN SERIAL ===
ser = serial.Serial(PORT, BAUDRATE, timeout=1)

# Variables para determinar el estado
ultima_direccion = None
ultimo_tiempo = time.time()

try:
    while True:
        line = ser.readline().decode('ascii', errors='replace').strip()

        # Trama RMC: contiene dirección, velocidad, latitud y longitud
        if line.startswith('$GPRMC'):
            try:
                msg = pynmea2.parse(line)
                if msg.status == 'A':  # Datos válidos
                    hora_local = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    lat = msg.latitude
                    lon = msg.longitude
                    velocidad_nudos = float(msg.spd_over_grnd)
                    velocidad_kmh = velocidad_nudos * 1.852  # conversión a km/h
                    direccion = float(msg.true_course) if msg.true_course else 0.0

                    # === Determinar el estado del movimiento ===
                    if velocidad_kmh < 0.3:
                        estatus = "estático"
                    else:
                        if ultima_direccion is not None:
                            cambio_dir = abs(direccion - ultima_direccion)
                            if cambio_dir > 15:  # más de 15° de cambio => girando
                                estatus = "girando"
                            else:
                                estatus = "moviéndose"
                        else:
                            estatus = "moviéndose"

                    ultima_direccion = direccion

                    # Mostrar en consola
                    print(f"[{hora_local}] Dir:{direccion:.1f}° | Lat:{lat:.6f} | Lon:{lon:.6f} | Vel:{velocidad_kmh:.2f} km/h | {estatus}")

                    # Guardar en CSV
                    with open(csv_filename, mode='a', newline='') as file:
                        writer = csv.writer(file)
                        writer.writerow([hora_local, direccion, lat, lon, velocidad_kmh, estatus])

            except pynmea2.ParseError:
                continue

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\n🛑 Lectura detenida por el usuario.")

finally:
    ser.close()
    print(f"✅ Datos guardados correctamente en: '{csv_filename}'")
