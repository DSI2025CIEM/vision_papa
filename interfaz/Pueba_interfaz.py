# Propuesta de interfaz GPS.
# /11/2025.
#Primer commit


#Librerías importadas:
import tkinter as tk
from tkinter import scrolledtext, filedialog
from datetime import datetime
import threading
import serial
import cv2
import PIL.Image, PIL.ImageTk


class NavigationSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Navegación GPS")
        self.root.geometry("1200x750")
        self.root.configure(bg="#D4D2D1")

        #Variables actualizadas por el GPS
        self.latitude = tk.StringVar(value="")
        self.longitude = tk.StringVar(value="")
        self.speed_kmh = tk.StringVar(value="")
        self.speed_knts = tk.StringVar(value="")
        self.course = tk.StringVar(value="")
        self.date = tk.StringVar(value="")
        self.time = tk.StringVar(value="")
        self.azimuth = tk.StringVar(value="")
        self.route_file = tk.StringVar(value="")   # Único editable (ruta del archivo)

        self.create_widgets()

        #Configuracion GPS
        try:
            self.serial_port = serial.Serial("COM6", 115200, timeout=1) #Puerto serial y baudios 
            self.add_console_message("GPS conectado en COM6")
        except:
            self.serial_port = None
            self.add_console_message(" ERROR: No se pudo abrir COM6")

        threading.Thread(target=self.read_serial, daemon=True).start()

        #Camara
        self.camera = cv2.VideoCapture(0)  # Cámara 
        self.update_camera()

    def create_widgets(self): #Creacion de apartados de datos.
        #Cambiamos la tipografía a Segoe UI 
        label_font = ('Segoe UI', 18, 'bold')
        entry_font = ('Segoe UI', 18)
        small_font = ('Segoe UI', 8)
        title_font = ('Segoe UI', 20, 'bold')
        button_font = ('Segoe UI', 12, 'bold')

        left_frame = tk.Frame(self.root, bg="#D4D2D1", padx=60, pady=20)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH)
        

        #Campos bloqueados
        self.create_field(left_frame, "Latitud", self.latitude, "$TODAS", 0, label_font, entry_font, small_font) #Creacion de campos para mostrtrar elementos de la sentencia
        self.create_field(left_frame, "Longitud", self.longitude, "$TODAS", 1, label_font, entry_font, small_font)
        self.create_field(left_frame, "Km/h", self.speed_kmh, "$GPVTG", 2, label_font, entry_font, small_font)
        self.create_field(left_frame, "KNTS", self.speed_knts, "$GPRMC", 3, label_font, entry_font, small_font)
        self.create_field(left_frame, "Dirección", self.course, "$GPVTG/$GPRMC", 4, label_font, entry_font, small_font)
        self.create_field(left_frame, "Fecha", self.date, "$GPZDA/$GPRMC", 5, label_font, entry_font, small_font)
        self.create_field(left_frame, "Hora", self.time, "$GPZDA/$GPRMC", 6, label_font, entry_font, small_font)
        self.create_field(left_frame, "Azimut", self.azimuth, "$GPGSV", 7, label_font, entry_font, small_font)

        tk.Label(left_frame, text="", bg="#D4D2D1").grid(row=8, column=0) #Espacio en blanco 

        #Campo Ruta editable
        tk.Label(left_frame, text="Ruta de almacenamiento:", bg="#D4D2D1",
                 font=label_font).grid(row=9, column=0, sticky='e')

        tk.Entry(left_frame, textvariable=self.route_file, font=entry_font,
                 width=25, bg='white', state="normal").grid(
            row=9, column=1, pady=5, sticky='w')

        #Botón para abrir explorador
        tk.Button(
            left_frame, text="Seleccionar carpeta", bg="#B0B0B0", fg="white",
            font=button_font, command=self.open_folder_selector
        ).grid(row=10, column=1, sticky='w', pady=10)

        #Frame derecho
        right_frame = tk.Frame(self.root, bg="#D4D2D1", padx=20, pady=20)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(right_frame, text="Flujo de datos.", bg="#D4D2D1",
                 font=title_font).pack(anchor='center')

        #Consola
        self.console = scrolledtext.ScrolledText(   #Muestra logs
            right_frame, wrap=tk.WORD, width=60, height=10,
            font=('Courier New', 10), bg='white'
        )
        self.console.pack(fill=tk.BOTH, expand=False) #Acomoda la pantalla
        self.console.configure(state="disabled") #Bloquea la edicion de la consola al usuario 

        #Cámara
        tk.Label(right_frame, text="Cámara - Vista del trayecto",  #Crea una etiqueta (Label) que muestra el texto
                 bg="#D4D2D1", font=('Segoe UI', 16, 'bold')).pack(pady=10)

        self.camera_label = tk.Label(right_frame, bg="black")  #Contenedor donde se mostrará la imagen o video de la camara
        self.camera_label.pack(fill=tk.BOTH, expand=True)

    def create_field(self, parent, label_text, variable, protocol, row, label_font, entry_font, small_font):
        tk.Label(parent, text=label_text, bg="#D4D2D1", font=label_font).grid(row=row, column=0)
        tk.Entry(parent, textvariable=variable, font=entry_font,
                 width=12, bg='white', state="readonly").grid(row=row, column=1, sticky='w') #Organiza datos 
        tk.Label(parent, text=protocol, bg="#D4D2D1",
                 font=small_font).grid(row=row, column=2)

    #GPS
    def read_serial(self):
        if not self.serial_port:
            return

        while True:
            try:
                line = self.serial_port.readline().decode(errors="ignore").strip()#Lee linea, convierte bytes a texto , ignora errores
                if line.startswith("$"): #Restriccion para procesar unicamente sentencias NMEA
                    self.process_nmea(line)
            except:
                pass

    def process_nmea(self, sentence): #Recibe la sentencia 
        self.add_console_message(sentence)#Manda la sentencia al área de consola y la muestra en pantalla como un msj nuevo
        parts = sentence.split(",") #Divide la sentencia en partes para acceder a los datos 

        if sentence.startswith("$GPRMC") and len(parts) >= 10: #Procesa la sentencia GPRMC
            if parts[2] == "A":  #Valida que losdatos sean los necesarios para poder procesarlos 

                # Hora UTC
                t = parts[1] #Extrae la hora mientras tenga  parte y StringVar
                if len(t) >= 6:
                    self.time.set(f"{t[0:2]}:{t[2:4]}:{t[4:6]}") #Extrae la hora en formato hhmmss.sss

                # Velocidad nudos
                self.speed_knts.set(parts[7]) #Lee la velocidad del mensaje 7 corresponde speed over ground in knots (nudos)

                # Rumbo
                self.course.set(parts[8])  #Con self accede a las variables y funciones internas 

                # Fecha
                f = parts[9]
                self.date.set(f"{f[0:2]}/{f[2:4]}/20{f[4:6]}")

                # Lat / Lon
                self.latitude.set(self.convert_lat(parts[3], parts[4]))
                self.longitude.set(self.convert_lon(parts[5], parts[6]))

        # GPVTG Velocidad km/h
        if sentence.startswith("$GPVTG") and len(parts) >= 8: #Revisa si la sentencia NMEA que llegó es del tipo GPVTG
            self.speed_kmh.set(parts[7]) #Guarda la velocidad km/h dentro de una variable que la interfaz muestra

    # Conversión NMEA
    def convert_lat(self, raw, hemi):
        try:
            d = float(raw[:2])
            m = float(raw[2:])
            v = d + m / 60
            return f"{v:.6f}" if hemi == "N" else f"{-v:.6f}" #Convierte la latitud en grados decimales
        except:
            return ""

    def convert_lon(self, raw, hemi):#Convierte la longitud a grados decimales con signo
        try:
            d = float(raw[:3])
            m = float(raw[3:])
            v = d + m / 60
            return f"{v:.6f}" if hemi == "E" else f"{-v:.6f}"
        except:
            return ""

    #Consola
    def add_console_message(self, msg):
        self.console.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.console.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.console.configure(state="disabled")
        self.console.see(tk.END)

    #Explorador de carpetas
    def open_folder_selector(self):
        folder = filedialog.askdirectory()
        if folder:
            self.route_file.set(folder)

    #Cámara 
    def update_camera(self):
        ret, frame = self.camera.read()   #Lee frame de la cámara
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  #Convierte BGR a RGB
            img = PIL.ImageTk.PhotoImage(image=PIL.Image.fromarray(frame))
            self.camera_label.imgtk = img
            self.camera_label.configure(image=img)

        #Llama de nuevo la función después de 30ms para actualizar (loop)
        self.camera_label.after(30, self.update_camera)


# MAIN
if __name__ == "__main__":
    root = tk.Tk()
    app = NavigationSystem(root)
    root.mainloop()
