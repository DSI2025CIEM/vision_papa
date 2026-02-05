import threading
import cv2
import numpy as np
import pyrealsense2 as rs
import serial
import pynmea2
import csv
import math
import time
from datetime import datetime
import os
import re
from threading import Lock

estado_gps = {
    "lat": None,
    "lon": None,
    "distancia_umbral": 0.0,
    "distancia_total": 0.0
}

lock_gps = Lock()

def timestamp_actual():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]

def crear_nuevo_recorrido(base_path):
    os.makedirs(base_path, exist_ok=True)

    recorridos = [
        d for d in os.listdir(base_path)
        if os.path.isdir(os.path.join(base_path, d)) and re.match(r"Recorrido_\d+", d)
    ]

    if not recorridos:
        nuevo_numero = 1
    else:
        numeros = [int(d.split("_")[1]) for d in recorridos]
        nuevo_numero = max(numeros) + 1

    recorrido_path = os.path.join(base_path, f"Recorrido_{nuevo_numero}")

    rutas = {
        "base": recorrido_path,
        "rgb": os.path.join(recorrido_path, "Capas_RGB"),
        "depth": os.path.join(recorrido_path, "Capas_D"),
        "colormap": os.path.join(recorrido_path, "Capas_ColorMap"),
    }

    for ruta in rutas.values():
        os.makedirs(ruta, exist_ok=True)

    print(f"Nuevo recorrido creado: Recorrido_{nuevo_numero}")
    return rutas


# =====================================================
#      EVENTO COMPARTIDO POR LAS 2 CLASES PARA CAPTURAR IMAGENES
# =====================================================
evento_captura = threading.Event() # La bandera del evento es inicialmente False

# =====================================================
#      CLASE DE LECTURA DE LA CÁMARA REALSENSE
# =====================================================
class HiloCamara(threading.Thread):
    def __init__(self, rutas, csv_path):
        super().__init__(daemon=True)
        self.width = 848 # Ancho frame de camara
        self.height = 480 # Largo frame de camara
        self.count = 0 # Contador de capturas
        self.running = True # Condicional para correr hilo
        self.rutas = rutas
        self.csv_path = csv_path

    def run(self):
        pipe, align, depth_scale = self.start_pipeline()

        print("Hilo de cámara iniciado...")

        while self.running:
            try:
                # Obtencion de capas
                color_bgr, depth_colormap, depth_m = self.get_capas(pipe, align, depth_scale)

                # Mostrar captura de capa RGB con conteo de captura
                cv2.putText(color_bgr, str(self.count) , (int(20), int(30)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
                cv2.imshow("Capa RGB", color_bgr)
                cv2.waitKey(1)

                # Esperar señal del GPS
                if evento_captura.is_set():

                    # Se cuenta +1 si el evento captura es True
                    self.count += 1

                    # Timestamp para ligar a imagen
                    ts = timestamp_actual()

                    

                    # Guardar capas en sus respectivas rutas rutas
                    np.save(
                        os.path.join(self.rutas["depth"], f"capa_d_{self.count}_{ts}.npy"),
                        depth_m
                    )

                    cv2.imwrite(
                        os.path.join(self.rutas["rgb"], f"capa_rgb_{self.count}_{ts}.png"),
                        color_bgr
                    )

                    cv2.imwrite(
                        os.path.join(self.rutas["colormap"], f"depth_colormap_{self.count}_{ts}.png"),
                        depth_colormap
                    )

                    # Leer estado GPS congelado
                    with lock_gps:
                        lat = estado_gps["lat"]
                        lon = estado_gps["lon"]
                        dist_umbral = estado_gps["distancia_umbral"]
                        dist_total = estado_gps["distancia_total"]

                    # Escribir CSV
                    with open(self.csv_path, "a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            self.count,
                            ts,
                            lat,
                            lon,
                            round(dist_umbral, 3),
                            round(dist_total, 3)
                        ])

                    evento_captura.clear()  # limpiar evento

                    print(f"Imagen {self.count} capturada | Timestamp: {ts}")

            except Exception as e:
                print("Error hilo camara:", e)
                break

        pipe.stop()
        cv2.destroyAllWindows()
        print("Hilo de camara detenido.")

    # ------------------------------
    def start_pipeline(self):
        # Configuraciones del frame de la camara
        conf = rs.config()
        conf.enable_stream(rs.stream.color, self.width, self.height, rs.format.rgb8, 30)
        conf.enable_stream(rs.stream.depth, self.width, self.height, rs.format.z16, 30)

        # Comienza streaming de camara
        pipe = rs.pipeline()
        profile = pipe.start(conf)

        # Alinear capa RGB con capa Depth
        align = rs.align(rs.stream.color)
        depth_scale = profile.get_device().first_depth_sensor().get_depth_scale()

        return pipe, align, depth_scale

    # ------------------------------
    def get_capas(self, pipe, align, depth_scale):
        # Alinea los frames de capa RGB y Depth una vez obtenidos los frames
        frames = pipe.wait_for_frames()
        aligned = align.process(frames)

        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()

        depth_raw = np.asanyarray(depth_frame.get_data())
        color = np.asanyarray(color_frame.get_data())

        # Convierte matriz de color_frame a formato de imagen RGB -> formato .png
        color_bgr = cv2.cvtColor(color, cv2.COLOR_RGB2BGR)

        #Convierte matriz de depth_frame a formato de imagen ColorMap -> formato .png
        depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_raw, alpha=0.03), cv2.COLORMAP_JET)

        # Obtiene Capa Depth en formato .npy -> matriz de datos de profundidad
        depth_m = depth_raw * depth_scale
        
        # Regresa capas RGB, Depth y ColorMap(Profundidad a color)
        return color_bgr, depth_colormap, depth_m


# =====================================================
#      CLASE DEL GPS EN HILO
# =====================================================
class HiloGPS(threading.Thread):
    def __init__(self, puerto="COM5", umbral=1.13):
        super().__init__(daemon=True)
        self.port = puerto # Puerto de cable de comunicacion con el GPS
        self.umbral = umbral # Umbral de distancia recorrida para tomar captura de capas
        self.running = True # Condicional para correr GPS 
        self.distancia_total = 0.0   # Distancia total acumulada del recorrido (metros)

    def run(self):
        ser = serial.Serial(self.port, 115200, timeout=1)
        punto_anterior = None # Punto anterior de mediciones -> (lat, lon)
        punto_inicial = None  # Punto inicial de mediciones -> (lat, lon)

        print("Hilo GPS iniciado...")

        while self.running:
            # Linea de la sentencia para obtencion de datos del GPS
            line = ser.readline().decode('ascii', errors='replace').strip()

            # Definicion del formato de los datos obtenidos del GPS
            # Verifica si hay una sentencia que empiece con $GPGGA
            if not line.startswith("$GPGGA"):
                continue # En caso de que la sentencia sea diferente aqui se omite el resto del codigo y brinca al inicio del while para volver a iterar 

            try:
                # Parseo de datos del GPS
                msg = pynmea2.parse(line)
                # Obtencion de latitud y longitud
                lat, lon = msg.latitude, msg.longitude
                if lat == 0 or lon == 0:
                    continue # En caso de que lat o lon sea 0 aqui se omite el resto del codigo y brinca al inicio del while para volver a iterar 


                # Primer punto para ambas mediciones
                if punto_inicial is None:
                    punto_inicial = (lat, lon)
                if punto_anterior is None:
                    punto_anterior = (lat, lon)
                    print(f"Punto inicial -> {lat:.6f}, {lon:.6f}")
                    continue

                # Distancia entre dos lecturas consecutivas del GPS
                                            # lat1,            lon1,             lat2, lon2
                incremento = self.haversine(punto_anterior[0], punto_anterior[1], lat, lon)

                # Acumular distancia total
                self.distancia_total += incremento

                # Actualizar punto anterior
                punto_anterior = (lat, lon)

                print(f"Incremento: {incremento:.3f} m | Total: {self.distancia_total:.3f} m")

                # Distancia desde el punto inicial a donde se capturo la foto
                distancia_umbral = self.haversine(punto_inicial[0], punto_inicial[1], lat, lon)

                # Si la distancia_umbral es mayor al umbral de 1.13m se manda la señal de captura y punto_inicial va guardar las coordenadas que detecto en ese momento de captura
                # Si todavia no se cumple la condicion se ignora el if y el while se duerme 0.1 segundos y se vuelven a hacer los calculos
                if distancia_umbral >= self.umbral:
                    print(f"Capturando capas, el GPS se ha movido: {distancia_umbral:.2f} m (>= {self.umbral} m)")

                    with lock_gps:
                        estado_gps["lat"] = lat
                        estado_gps["lon"] = lon
                        estado_gps["distancia_umbral"] = distancia_umbral
                        estado_gps["distancia_total"] = self.distancia_total

                    punto_inicial = (lat, lon) # El punto inicial se actualiza hasta que se supera el umbral de distancia

                    # Avisar al hilo de cámara
                    evento_captura.set()

                time.sleep(0.1)

            except Exception as e:
                print("Error GPS:", e)

        ser.close()
        print("Hilo GPS detenido.")

    # Ecuacion de haversine
    # Funcion que devuelve distancia entre dos puntos de la tierra
    @staticmethod
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# =====================================================
#        MAIN: INICIAR LOS HILOS
# =====================================================
if __name__ == "__main__":

    # Ruta base para creacion de carpetas de los recorridos
    BASE_PATH = "datasets\GPS_Capas"

    # Carpetas de los recorridos
    RUTAS_RECORRIDO = crear_nuevo_recorrido(BASE_PATH)

    csv_path = os.path.join(RUTAS_RECORRIDO["base"], "Recorrido.csv")

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "captura",
            "timestamp",
            "lat",
            "lon",
            "distancia_umbral",
            "distancia_total"
        ])

    # Objeto hilo_camara, le pasamos como propiedad las carpetas de los recorridos
    hilo_camara = HiloCamara(RUTAS_RECORRIDO, csv_path)
    # Objeto hilo_gps
    hilo_gps = HiloGPS() # Instancia clase gps

    hilo_camara.start() # Inicia hilo de camara
    hilo_gps.start() # Inicia hilo de GPS

    print("\nSistema iniciado: Cámara + GPS + Captura automática cada 1.13 m\n")

    try:
        while True:
            time.sleep(0.5)
    
    # Si se finaliza el programa por el usuario se detienen hilos
    except KeyboardInterrupt:
        print("\n Finalizando...")

        hilo_camara.running = False
        hilo_gps.running = False
        
        time.sleep(1)
