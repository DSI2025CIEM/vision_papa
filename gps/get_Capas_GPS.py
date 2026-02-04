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

# =====================================================
#      EVENTO COMPARTIDO POR LAS 2 CLASES PARA CAPTURAR IMAGENES
# =====================================================
evento_captura = threading.Event() # La bandera del evento es inicialmente False

# =====================================================
#      CLASE DE LECTURA DE LA CÁMARA REALSENSE
# =====================================================
class HiloCamara(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.width = 848 # Ancho frame de camara
        self.height = 480 # Largo frame de camara
        self.count = 0 # Contador de capturas
        self.running = True # Condicional para correr hilo

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

                    evento_captura.clear()  # limpiar evento

                    # Guardar capas en sus respectivas rutas rutas
                    np.save(f"C:/GPS/capturas/DatosCosecha/capa_d_{self.count}.npy", depth_m)
                    cv2.imwrite(f"C:/GPS/capturas/DatosCosecha/capa_rgb_{self.count}.png", color_bgr)
                    cv2.imwrite(f"C:/GPS/capturas/DatosCosecha/depth_colormap_{self.count}.png", depth_colormap)

                    print(f"Imagen capturada automaticamente ({self.count})")

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

                # Distancia desde el ultimo punto (sumatoria total)
                                            # lat1,            lon1,             lat2, lon2
                incremento = self.haversine(punto_anterior[0], punto_anterior[1], lat, lon)

                # Acumular distancia total
                self.distancia_total += incremento

                # Actualizar punto anterior
                punto_anterior = (lat, lon)

                print(f"Incremento: {incremento:.3f} m | Total: {self.distancia_total:.3f} m")

                # Distancia desde el punto inicial a donde se capturo la foto
                distancia_umbral = self.haversine(punto_inicial[0], punto_inicial[1], lat, lon)

                # Verificar si se supero el umbral
                if distancia_umbral >= self.umbral:
                    print(f"Capturando capas, el GPS se ha movido: {distancia_umbral:.2f} m (>= {self.umbral} m)")
                    punto_inicial = (lat, lon)

                    # Avisar al hilo de cámara
                    evento_captura.set()

                time.sleep(0.1)

            except Exception as e:
                print("Error GPS:", e)

        ser.close()
        print("Hilo GPS detenido.")

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
    hilo_camara = HiloCamara() # Instancia clase camara
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
