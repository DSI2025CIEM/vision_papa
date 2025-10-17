import cv2
from ultralytics import YOLO
from pathlib import Path
import glob
import numpy as np
import os

class Conteo:
    def __init__(self):
        self.capa_rgb_ruta = r"C:\MonitoreoPapa\DatosCosecha\Dataset_Mosaico\Dataset_Tecla\set_Capa_RGB"
        self.capa_d_ruta = r"C:\MonitoreoPapa\DatosCosecha\Dataset_Mosaico\Dataset_Tecla\set_Capa_D"
        self.width_frame = 848
        self.height_frame = 480

    def get_capa_profundidad(self, capa_d_path) -> np.ndarray:
        """Carga la capa de profundidad desde archivo .npy"""
        return np.load(capa_d_path)

    def getSize(self, box, capa_d=None, depth_frame=None, depth_scale=None,
                intrinsics=None, alert=False):
        """
        box: (x, y, w, h)  # x,y top-left
        capa_d: numpy array (preferiblemente en METROS), or None
        depth_frame: pyrealsense2.depth_frame (optional)
        depth_scale: float (meters per raw unit) (optional)
        intrinsics: pyrealsense2.intrinsics (optional, has fx,fy,ppx,ppy)
        """
        try:
            x, y, w, h = box
            cx = int(x + w/2)
            cy = int(y + h/2)

            # 1) Obtener profundidad (en metros) prefiriendo depth_frame API
            z = None
            if depth_frame is not None:
                # safe casting
                z = depth_frame.get_distance(cx, cy)  # en metros
            elif capa_d is not None:
                H, W = capa_d.shape[:2]
                # recortar region 5x5 con clipping
                x0 = max(0, cx - 2); x1 = min(W, cx + 3)
                y0 = max(0, cy - 2); y1 = min(H, cy + 3)
                region = capa_d[y0:y1, x0:x1].astype(float)
                # excluir ceros/nan
                valid = region[np.isfinite(region) & (region > 0)]
                if valid.size > 0:
                    z = float(np.median(valid))
                else:
                    z = None

                # si capa_d es raw (uint16), aplicar depth_scale si se proporcionó
                if z is None and depth_scale is not None and capa_d.dtype != float:
                    # tomar la mediana del region raw y aplicar scale
                    region_raw = capa_d[y0:y1, x0:x1]
                    valid_raw = region_raw[(region_raw > 0)]
                    if valid_raw.size > 0:
                        z = float(np.median(valid_raw)) * float(depth_scale)

            # fallback
            if z is None or np.isnan(z) or z <= 0:
                if alert:
                    print("⚠️ Profundidad inválida; usando fallback 1.0 m")
                z = 1.0  # O mejor: devolver None / marcar no confiable

            # 2) Obtener intrínsecos (fx, fy). Si no están, estimar desde HFOV - menos preciso.
            if intrinsics is not None:
                fx = intrinsics.fx
                fy = intrinsics.fy
            else:
                # estimación: usar HFOV real de tu cámara si la conoces (D457 ≈ 87°)
                HFOV_deg = 87.0
                VFOV_deg = 58.0
                fx = (self.width_frame / 2.0) / np.tan(np.radians(HFOV_deg / 2.0))
                fy = (self.height_frame / 2.0) / np.tan(np.radians(VFOV_deg / 2.0))

            # 3) conversión píxel -> mm (usar fx y fy)
            px_to_mm_x = (z / fx) * 1000.0
            px_to_mm_y = (z / fy) * 1000.0

            ancho_mm = w * px_to_mm_x
            alto_mm  = h * px_to_mm_y

            return ancho_mm, alto_mm, z * 1000.0, (px_to_mm_x, px_to_mm_y)

        except Exception as e:
            print("Error en getSize:", e)
            return 0, 0, 0, (0,0)

    def process_images_in_folder(self, model_path):
        """
        Procesa imágenes RGB y profundidad emparejadas, cuenta objetos y estima dimensiones.
        """
        capa_rgb = sorted(glob.glob(os.path.join(self.capa_rgb_ruta, "capa_rgb_*.png")),
                          key=lambda x: int(os.path.splitext(os.path.basename(x))[0].split("_")[-1]))
        capa_d = sorted(glob.glob(os.path.join(self.capa_d_ruta, "capa_d_*.npy")),
                        key=lambda x: int(os.path.splitext(os.path.basename(x))[0].split("_")[-1]))

        if not capa_rgb or not capa_d:
            raise FileNotFoundError("No se encontraron imágenes RGB o de profundidad en las rutas especificadas.")
        if len(capa_rgb) != len(capa_d):
            raise ValueError("La cantidad de imágenes RGB y capas de profundidad no coincide.")

        print("Frame | Obj_ID | Ancho_px | Alto_px | Ancho_mm | Alto_mm | Profundidad_mm")

        # Cargar modelo una sola vez (mejor rendimiento)
        model = YOLO(model_path)
        model(classes=[1], verbose=False)

        conteo_total = 0

        for idx, (rgb_path, d_path) in enumerate(zip(capa_rgb, capa_d), start=1):
            image = cv2.imread(rgb_path)
            if image is None:
                print(f"Error al abrir {rgb_path}")
                continue

            capa_d_array = self.get_capa_profundidad(d_path)

            # Inferencia YOLO
            results = model.predict(image, verbose=False)

            total_frame = 0

            if results and results[0].boxes is not None:
                boxes = results[0].boxes.xywh.cpu().numpy()

                for j, box in enumerate(boxes, start=1):
                    x, y, w, h = box
                    ancho_mm, alto_mm, profundidad_mm, pxmm = self.getSize(box, capa_d_array)

                    # Dibujar el bounding box
                    x1, y1 = int(x - w / 2), int(y - h / 2)
                    x2, y2 = int(x + w / 2), int(y + h / 2)
                    cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(image, f"ID{j}", (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

                    print(f"{idx:03d} | {j:02d} | {w:.1f} | {h:.1f} | {ancho_mm:.2f} | {alto_mm:.2f} | {profundidad_mm:.2f}")

                    total_frame += 1

            conteo_total += total_frame
            cv2.putText(image, f"Objetos: {total_frame}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

            cv2.imshow("YOLO detección + dimensiones", image)
            cv2.waitKey(2000)

        cv2.destroyAllWindows()
        print(f"\n✅ Conteo total de objetos detectados: {conteo_total}")
        return conteo_total


if __name__ == "__main__":
    main = Conteo()
    MODEL_PATH = r"C:\MonitoreoPapa\models\ModeloPapa.pt"
    total = main.process_images_in_folder(MODEL_PATH)
    print("Conteo total acumulado:", total)
