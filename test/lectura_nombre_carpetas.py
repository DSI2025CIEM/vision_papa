from os import path, mkdir
import os

cont=0

carpeta_raiz = "datasets/GPS_Capas"
carpeta_nueva = f"/Recorrido_{cont}"

print(os.listdir(carpeta_raiz))

if (path.exists(f"{carpeta_raiz}{carpeta_nueva}")):
    print(f"La carpeta {carpeta_raiz}{carpeta_nueva} ya existe")
else:
    mkdir(f"{carpeta_raiz}{carpeta_nueva}")
    print(f"Carpeta {carpeta_raiz}{carpeta_nueva} creada")