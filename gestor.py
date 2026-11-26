
import json
import os
import re
import shlex
import sys
import time
import unicodedata
from datetime import date

#Librería para utilizar directorios y rutas de archivos. 
from pathlib import Path

#Crear las hojas de cálculo. 
import pandas as pd

#Manejar los errores y mandarlas en un except para encontrarlos más rápido. 
from pymongo.errors import PyMongoError
from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

#Diseño de los reportes. 
#Librebria ReporLab.
#Referencia: https://recursospython.com/guias-y-manuales/crear-documentos-pdf-en-python-con-reportlab/#google_vignette
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, Image)



#Librería prompt_toolkit, usado para el autocompletado. 
#Referencia: 
#https://github.com/lstein/prompt-toolkit
try:  
    from prompt_toolkit import prompt as pt_prompt
    from prompt_toolkit.completion import Completer, Completion
except ImportError:  
    pt_prompt = None
    Completer = object



#Referencia de todo lo usado para esta función: 
#https://www.geeksforgeeks.org/python/how-to-split-a-file-into-a-list-in-python/
#https://www.geeksforgeeks.org/python/python-os-path-splitext-method/
#https://www.geeksforgeeks.org/python/python-os-environ-object/


def cargarenv(ruta=".env"):
    #Con la librería Path creamos una ruta relativa, donde se encuentra el archivo .env, que contiene las variables de entorno, como la contraseña de la base de datos.
    p = Path(ruta)
    if p.exists():
        #Si la ruta existe, se lee el archivo línea por línea, con read_text se lee como un string. 
        for linea in p.read_text(encoding="utf-8").splitlines():
            #Splitlines separa los strings que se obtuvieron con read_text, y los convierte en una lista. 
            linea = linea.strip()
            #Con Strip eliminamos los espacios en blanco al inicio y al final de cada línea, para que no haya errores al leer las variables de entorno.
            if linea and not linea.startswith("#") and "=" in linea:
                #Este if verifica que la linea que va a evaluar tenga algun valor, tambien evalua si no es algun 
                #comentario y si si es, pues lo ignora y tambien evalúa que tenga la estructura clave valor. 
                k, v = linea.split("=", 1)
                #Despues dividimos la línea en dos variables, k(key) y v(value) y usando split, las separa por el igual. 
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
                #Aquí ya retorna las variables como van a ser usadas. 
                #Elimina las comillas de la key, luego del value y al final las comillas simples que pudieron haber quedado. 




#Estas son constantes, variables que por nada del mundo se deben cambiar, si quieren modificar algún dato de la conexión, debe hacerse en el archivo .env, no aquí.
cargarenv()
MONGOURI = os.getenv("MONGOURI", "mongodb+srv://departamentoorientacion128_db_user:K7GMu6bztEYNpD@bdorientacion.rtlyomr.mongodb.net/")
DBNAME = os.getenv("DBNAME", "BDOrientacion")
ESCUELA = os.getenv("ESCUELA", "Centro de bachillerato Tecnológico Industrial y de Servicios No. 128")
DATOSJSON = Path("datos_json")
#Esta es la direccion a la cual se guardan los archivos PDF
DIRECCIONPDFS = Path("reportes")
TIMEOUT = int(os.getenv("MONGO_TIMEOUT_MS", "10000"))
DIRECCIONEXPORTAR = Path("exportaciones")

DATOSALUMNO = [
    "numero_control", "apellido_paterno", "apellido_materno", "nombre",
    "generacion", "especialidad", "semestre", "grupo", "turno",
    "nombre_padre_madre", "telefono",
]

DATOSCANALIZACION = [
    "fecha_atencion", "persona_reporta", "motivo",
    "medida_modificacion_conducta", "seguimiento_documentos",
]
ETIQUETAS = {
    "fecha_atencion": "Fecha de atención",
    "numero_control": "Número de control",
    "apellido_paterno": "Apellido paterno",
    "apellido_materno": "Apellido materno",
    "nombre": "Nombre(s)",
    "generacion": "Generación",
    "especialidad": "Especialidad",
    "semestre": "Semestre",
    "grupo": "Grupo",
    "turno": "Turno",
    "persona_reporta": "Persona que reporta",
    "motivo": "Motivo",
    "nombre_padre_madre": "Nombre de padre o madre",
    "telefono": "Teléfono",
    "medida_modificacion_conducta": "Medida de modificación de conducta",
    "seguimiento_documentos": "Seguimiento de los documentos",
    "canalizaciones_anteriores": "Número de canalizaciones anteriores",
}

ALIAS = {
    "numero_control": ["numero_de_control", "no_control", "n_control", "control", "matricula", "num_control"],
    "fecha_atencion": ["fecha_de_atencion", "fecha"],
    "persona_reporta": ["persona_que_reporta", "reporta", "quien_reporta"],
    "nombre_padre_madre": ["nombre_de_padre_o_madre", "padre_o_madre", "nombre_padre_o_madre", "tutor"],
    "medida_modificacion_conducta": ["medida_de_modificacion_de_conducta", "medida"],
    "seguimiento_documentos": ["seguimiento_de_los_documentos", "seguimiento"],
    "generacion": ["generación"],
    "nombre": ["nombre_s", "nombres"],
}



def quitaracentos(txt: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", txt) if unicodedata.category(c) != "Mn")


def normcolumna(col: str) -> str:
    c = quitaracentos(str(col)).lower().strip()
    c = re.sub(r"[^a-z0-9]+", "_", c).strip("_")
    for oficial, alternativos in ALIAS.items():
        if c == oficial or c in [quitaracentos(a) for a in alternativos]:
            return oficial
    return c


def limpiar(valor) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    v = str(valor).strip()
    return "" if v.lower() in ("nan", "nat", "none") else v


def fecha(valor) -> str:
    v = limpiar(valor)
    if not v:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}", v):  
        return v[:10]
    f = pd.to_datetime(v, dayfirst=True, errors="coerce")  
    return f.strftime("%Y-%m-%d") if not pd.isna(f) else v


def urioculta(uri: str) -> str:
    return re.sub(r"://([^:/@]+):[^@]+@", r"://\1:****@", uri)


def conectar():
    try:
        cliente = MongoClient(MONGOURI, serverSelectionTimeoutMS=TIMEOUT,
                              connectTimeoutMS=TIMEOUT, maxPoolSize=20,
                              appname="BD_Orientacion")
        db = cliente[DBNAME]
        cliente.admin.command("ping")
        db.alumnos.create_index("numero_control", unique=True)
        db.alumnos.create_index([("apellido_paterno", ASCENDING), ("apellido_materno", ASCENDING)])
        db.canalizaciones.create_index([("numero_control", ASCENDING), ("fecha_atencion", DESCENDING)])
        db.canalizaciones.create_index([("generacion", ASCENDING), ("especialidad", ASCENDING),
                                        ("semestre", ASCENDING), ("grupo", ASCENDING), ("turno", ASCENDING)])
    except PyMongoError as e:
        raise ConnectionError(
            f"No se pudo conectar a MongoDB ({urioculta(MONGOURI)}). Revise que el servicio esté encendido, "
            f"la URI sea correcta y que la IP desde la que se conecta "
            f"esté permitida. Detalle: {type(e).__name__}") from e
    return db


def estadoconexion(db) -> dict:
    t = time.perf_counter()
    try:
        db.client.admin.command("ping")
        return {"conectado": True, "ms": round((time.perf_counter() - t) * 1000)}
    except PyMongoError as e:
        return {"conectado": False, "error": type(e).__name__}



#Autocompletado con el número de control. 
class ControlCompleter(Completer):

    def __init__(self, db):
        self.db = db

    def get_completions(self, document, complete_event):
        txt = document.text.strip()
        if not txt:
            return
        cur = self.db.alumnos.find(
            {"numero_control": {"$regex": "^" + re.escape(txt)}},
            {"_id": 0, "numero_control": 1, "nombre": 1, "apellido_paterno": 1, "apellido_materno": 1},
        ).limit(10)
        for a in cur:
            nombre = f"{a.get('apellido_paterno','')} {a.get('apellido_materno','')} {a.get('nombre','')}".strip()
            yield Completion(a["numero_control"], start_position=-len(txt), display_meta=nombre)


def preguntar(msg, default="", completer=None) -> str:
    if pt_prompt:
        return pt_prompt(f"{msg}: ", default=default, completer=completer, complete_while_typing=True).strip()
    r = input(f"{msg}{f' [{default}]' if default else ''}: ").strip()
    return r or default



MACROS = {}

def macro(nombre, ayuda):
    def deco(fn):
        MACROS[nombre] = (fn, ayuda)
        return fn
    return deco


def leerarchivo(ruta: Path):
    ext = ruta.suffix.lower()
    if ext in (".xls", ".xlsx"):
        filas = []
        for hoja in pd.read_excel(ruta, dtype=str, sheet_name=None).values():
            filas += hoja.to_dict("records")
    elif ext == ".json":
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
        filas = datos if isinstance(datos, list) else datos.get("alumnos", []) + datos.get("canalizaciones", [])
    else:
        raise ValueError("Formato no admitido. Formatos admitidos: .xls, .xlsx, .json")
    registros = []
    for fila in filas:
        r = {normcolumna(k): limpiar(v) for k, v in fila.items()}
        if r.get("numero_control"):
            r["fecha_atencion"] = fecha(r.get("fecha_atencion"))
            registros.append(r)
    return registros, len(filas) - len(registros)


@macro("importar"," importar — Importa datos desde un archivo Excel o JSON.")
def importar(db, args):
    if not args:
        print("Importar requiere del nombre del archivo.")
        return
    ruta = Path(args[0])
    if not ruta.exists():
        print(f"No existe el archivo: {ruta}")
        return
    try:
        registros, omitidas = leerarchivo(ruta)
    except Exception as e:
        print(f"No se pudo leer el archivo: {e}")
        return
    if not registros:
        print("No se encontraron filas con número de control.")
        return
    texto_json = ""
    if ruta.suffix.lower() != ".json":  
        DATOSJSON.mkdir(exist_ok=True)
        ruta_json = DATOSJSON / (ruta.stem + ".json")
        ruta_json.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
        texto_json = f" | JSON: {ruta_json}"

    ops_alumnos, ops_can, controles = [], [], set()
    for r in registros:
        alumno = {k: r[k] for k in DATOSALUMNO if k in r}
        ops_alumnos.append(UpdateOne({"numero_control": alumno["numero_control"]},
                                   {"$set": alumno}, upsert=True))
        if r.get("fecha_atencion") or r.get("motivo"):
            can = {k: r.get(k, "") for k in DATOSALUMNO + DATOSCANALIZACION}
            clave = {"numero_control": can["numero_control"],
                     "fecha_atencion": can["fecha_atencion"], "motivo": can["motivo"]}
            ops_can.append(UpdateOne(clave, {"$set": can}, upsert=True))  # reimportar no duplica
            controles.add(can["numero_control"])
    db.alumnos.bulk_write(ops_alumnos, ordered=False)
    if ops_can:
        db.canalizaciones.bulk_write(ops_can, ordered=False)
        recalcular_anteriores(db, controles)
    print(f" {len(registros)} filas cargadas, {omitidas} omitidas{texto_json} | "
          f"alumnos: {len(ops_alumnos)} | canalizaciones: {len(ops_can)}")


def datosexportables(db, filtro=None):
    filtro = filtro or {}
    can = list(db.canalizaciones.find(filtro, {"_id": 0}).sort(
        [("apellido_paterno", ASCENDING), ("fecha_atencion", ASCENDING)]))
    if filtro:
        controles = list({c["numero_control"] for c in can})
        alu = list(db.alumnos.find({"numero_control": {"$in": controles}}, {"_id": 0}).sort("apellido_paterno", ASCENDING))
    else:
        alu = list(db.alumnos.find({}, {"_id": 0}).sort("apellido_paterno", ASCENDING))
    return alu, can


def exportarjson(db, filtro=None) -> bytes:
    alu, can = datosexportables(db, filtro)
    paquete = {"exportado": date.today().isoformat(), "alumnos": alu, "canalizaciones": can}
    return json.dumps(paquete, ensure_ascii=False, indent=2).encode("utf-8")


def exportarexcel(db, filtro=None) -> bytes:
    from io import BytesIO
    from openpyxl.styles import Font, PatternFill
    alu, can = datosexportables(db, filtro)
    cols_can = ["fecha_atencion"] + DATOSALUMNO + DATOSCANALIZACION[1:] + ["canalizaciones_anteriores"]
    salida = BytesIO()
    with pd.ExcelWriter(salida, engine="openpyxl") as w:
        for hoja, filas, cols in (("Alumnos", alu, DATOSALUMNO), ("Canalizaciones", can, cols_can)):
            df = pd.DataFrame(filas, columns=cols).rename(columns=ETIQUETAS)
            df.to_excel(w, sheet_name=hoja, index=False)
            ws = w.sheets[hoja]
            ws.freeze_panes = "A2"
            for celda in ws[1]:
                celda.fill = PatternFill("solid", fgColor="7A1F3D")
                celda.font = Font(bold=True, color="FFFFFF")
            for n, col in enumerate(df.columns, start=1):
                largo = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)])
                ws.column_dimensions[ws.cell(1, n).column_letter].width = min(largo + 2, 45)
            for fila in ws.iter_rows(min_row=2):
                for celda in fila:
                    if isinstance(celda.value, str):
                        celda.data_type = "s"  
    return salida.getvalue()


@macro("exportar", "exportar — Exporta los datos en formato JSON o XLSX.")
def exportar(db, args):
    if not args or args[0].lower() not in ("xlsx", "json"):
        print("Uso: exportar xlsx|json [campo=valor ...]")
        return
    formato = args[0].lower()
    filtro = filtro(args[1:])
    datos = exportarexcel(db, filtro) if formato == "xlsx" else exportarjson(db, filtro)
    DIRECCIONEXPORTAR.mkdir(exist_ok=True)
    ruta = DIRECCIONEXPORTAR / f"orientacion_{date.today().isoformat()}.{formato}"
    ruta.write_bytes(datos)
    print(f"Exportado: {ruta}")


@macro("conexion", "conexion — Consulta el estado de la conexión. ")
def conexion(db, args):
    e = estadoconexion(db)
    print(f"Servidor: {urioculta(MONGOURI)}  —  Base de Datos: {DBNAME}")
    if not e["conectado"]:
        print(f" Sin conexión ({e['error']}).")
        return
    print(f" Conectado ({e['ms']} ms) | MongoDB {db.client.server_info()['version']}")
    print(f"  alumnos: {db.alumnos.count_documents({})} | canalizaciones: "
          f"{db.canalizaciones.count_documents({})} | usuarios: {db.usuarios.count_documents({})}")


def recalcular_anteriores(db, controles):
    ops = []
    for c in controles:
        docs = list(db.canalizaciones.find({"numero_control": c}, {"_id": 1}).sort("fecha_atencion", ASCENDING))
        for i, d in enumerate(docs):
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {"canalizaciones_anteriores": i}}))
    if ops:
        db.canalizaciones.bulk_write(ops, ordered=False)


@macro("registrar", "registrar — Genera un nuevo reporte de canalización para un alumno (por número de control).")
def registrar(db, args):
    control = preguntar("Número de control", completer=ControlCompleter(db) if pt_prompt else None)
    if not control:
        return
    alumno = db.alumnos.find_one({"numero_control": control}, {"_id": 0})
    if alumno:
        print(f"Alumno: {alumno.get('apellido_paterno','')} {alumno.get('apellido_materno','')} {alumno.get('nombre','')}")
    else:
        print("Alumno nuevo: Capture todos los datos.")
        alumno = {"numero_control": control}
    datos = {"numero_control": control}
    for campo in DATOSALUMNO[1:]:  
        datos[campo] = preguntar(ETIQUETAS[campo], alumno.get(campo, ""))
    datos["fecha_atencion"] = fecha(preguntar(ETIQUETAS["fecha_atencion"], date.today().isoformat()))
    for campo in DATOSCANALIZACION[1:]:
        datos[campo] = preguntar(ETIQUETAS[campo])
        #Funciones CRUD, como update, insert, count, vitales de Mongo para acceder y manejar los documentos. 
    datos["canalizaciones_anteriores"] = db.canalizaciones.count_documents({"numero_control": control})
    db.alumnos.update_one({"numero_control": control},
                          {"$set": {k: datos[k] for k in DATOSALUMNO}}, upsert=True)
    db.canalizaciones.insert_one(datos)
    print(f"Reporte guardado (anteriores: {datos['canalizaciones_anteriores']}).")
    if preguntar("¿Generar PDF ahora? (s/n)", "s").lower().startswith("s"):
        ruta = pdf([datos], f"canalizacion_{control}_{datos['fecha_atencion']}.pdf")
        print(f"PDF guardado en: {ruta}")
        #Path de aqui: Carpeta reportes. 


def filtro(args):
    filtro = {}
    for a in args:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        k = normcolumna(k)
        if k in ("desde", "hasta"):
            filtro.setdefault("fecha_atencion", {})["$gte" if k == "desde" else "$lte"] = fecha(v)
        else:
            filtro[k] = {"$regex": f"^{re.escape(v)}$", "$options": "i"}
    return filtro


def mostrar(docs, campos):
    docs = list(docs)
    if not docs:
        print("(sin resultados)")
        return
    print(pd.DataFrame(docs)[campos].to_string(index=False))
    print(f"\n{len(docs)} resultado(s)")


@macro("buscar", "buscar — Busca alumnos por número de control o apellido paterno (por ejemplo: 'buscar 12345678' o 'buscar Luna').")
def buscar(db, args):
    if not args:
        print("Uso: buscar <texto>")
        return
    t = re.escape(" ".join(args))
    cur = db.alumnos.find({"$or": [{"numero_control": {"$regex": "^" + t}},
                                   {"apellido_paterno": {"$regex": "^" + t, "$options": "i"}}]},
                          {"_id": 0}).limit(50)
    mostrar(cur, ["numero_control", "apellido_paterno", "apellido_materno", "nombre", "semestre", "grupo", "turno"])


@macro("filtrar", "filtrar — Filtra los reportes según los datos indicados (por ejemplo: 'filtrar semestre=5').")
def filtrar(db, args):
    filtro = filtro(args)
    cur = db.canalizaciones.find(filtro, {"_id": 0}).sort("fecha_atencion", DESCENDING).limit(500)
    mostrar(cur, ["fecha_atencion", "numero_control", "apellido_paterno", "nombre", "semestre",
                  "grupo", "turno", "motivo", "canalizaciones_anteriores"])



#Diseño del PDF.

def pdf(docs, nombre_archivo) -> Path:
    DIRECCIONPDFS.mkdir(exist_ok=True)
    ruta = DIRECCIONPDFS / nombre_archivo
    est = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=est["Title"], fontSize=15, spaceAfter=2)
    sub = ParagraphStyle("s", parent=est["Normal"], alignment=1, fontSize=10, textColor=colors.grey)
    cel = ParagraphStyle("c", parent=est["Normal"], fontSize=9.5, leading=12)
    etq = ParagraphStyle("e", parent=cel, fontName="Helvetica-Bold")

    doc = SimpleDocTemplate(str(ruta), pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm, title="Reporte de canalización")
    historia = []
    for i, d in enumerate(docs):
        historia += [Paragraph(ESCUELA, titulo),
                     Paragraph("Canalización por parte del departamento de Orientación", sub),
                     Paragraph("<b>Reporte de docente hacia alumno</b>", ParagraphStyle("r", parent=sub, fontSize=12, textColor=colors.black, spaceBefore=6)),
                     Spacer(1, 14)]
        orden = ["fecha_atencion", "numero_control", "apellido_paterno", "apellido_materno", "nombre","generacion", "especialidad", "semestre", "grupo", "turno","persona_reporta", "nombre_padre_madre", "telefono"]
        filas = []
        for j in range(0, len(orden), 2):
            par = orden[j:j + 2]
            fila = []
            for k in par:
                fila += [Paragraph(ETIQUETAS[k], etq), Paragraph(limpiar(d.get(k)) or "—", cel)]
            while len(fila) < 4:
                fila += ["", ""]
            filas.append(fila)
        t = Table(filas, colWidths=[3.4 * cm, 5.1 * cm, 3.4 * cm, 5.1 * cm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        historia += [t, Spacer(1, 12)]

        largos = ["motivo", "medida_modificacion_conducta", "seguimiento_documentos"]
        filas_l = [[Paragraph(ETIQUETAS[k], etq), Paragraph(limpiar(d.get(k)) or "—", cel)] for k in largos]
        filas_l.append([Paragraph(ETIQUETAS["canalizaciones_anteriores"], etq), Paragraph(str(d.get("canalizaciones_anteriores", 0)), cel)])
        tl = Table(filas_l, colWidths=[5.5 * cm, 11.5 * cm], rowHeights=[2.4 * cm, 2.4 * cm, 2.4 * cm, None])
        tl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),("VALIGN", (0, 0), (-1, -1), "TOP")]))
        historia += [tl, Spacer(1, 70)]

        firmas = Table([["______________________", "______________________", "______________________"],
                        ["Orientador(a)", "Alumno(a)", "Padre / madre / tutor"]], colWidths=[5.7 * cm] * 3)
        firmas.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
        historia.append(firmas)
        if i < len(docs) - 1:
            historia.append(PageBreak())

        img= Image("logopumas.jpg", width=100, height=100)
        img.hAlign = "RIGHT"
        historia.append(img)
    doc.build(historia)
    return ruta


@macro("reporte", "reporte — Genera un PDF con el último reporte del alumno indicado (por número de control). ")
def reporte(db, args):
    if not args:
        print("Uso: reporte <numero_control> [fecha]")
        return
    filtro = {"numero_control": args[0]}
    if len(args) > 1:
        filtro["fecha_atencion"] = fecha(args[1])
    d = db.canalizaciones.find_one(filtro, {"_id": 0}, sort=[("fecha_atencion", DESCENDING)])
    if not d:
        print("No hay canalizaciones con esos datos.")
        return
    print(f"canalizacion_{d['numero_control']}_{d['fecha_atencion']}.pdf")


@macro("lote", "lote — Muestra un PDF con todas las canalizaciones que cumplan el filtro dado.")
def lote(db, args):
    docs = list(db.canalizaciones.find(filtro(args), {"_id": 0}).sort(
        [("apellido_paterno", ASCENDING), ("fecha_atencion", ASCENDING)]))
    if not docs:
        print("(sin resultados)")
        return
    print(f"PDF con {len(docs)} hojas: {pdf(docs, f'lote_{date.today().isoformat()}.pdf')}")


@macro("ayuda", "ayuda — Muestra los macros disponibles y su descripción. :)")
def ayuda(db, args):
    print("\nMacros disponibles (puedes encadenarlos con ';'):")
    for n, (_, h) in MACROS.items():
        print(f"  {h}")
    print("  salir cerrar el programa\n")

def ejecutar(db, linea):
    for cmd in [c.strip() for c in linea.split(";") if c.strip()]:
        partes = shlex.split(cmd)
        nombre, args = partes[0].lower(), partes[1:]
        if nombre in ("salir", "exit"):
            return False
        if nombre not in MACROS:
            print(f"Macro desconocida: {nombre}. Escribe 'ayuda'.")
            continue
        try:
            MACROS[nombre][0](db, args)
        except Exception as e:  
            print(f"Error en '{nombre}': {e}")
    return True


def main():
    try:
        db = conectar()
    except ConnectionError as e:
        sys.exit(f" {e}")
    if len(sys.argv) > 1:
        ejecutar(db, " ".join(f'"{a}"' if " " in a and ";" not in a else a for a in sys.argv[1:]))
        return
    print("Gestor de Base de Datos de Orientación Educativa Jaguar— escribe 'ayuda' para ver los macros.")
    while True:
        try:
            if not ejecutar(db, input("SGDB> ")):
                break
        except (EOFError, KeyboardInterrupt):
            break


if __name__ == "__main__":
    main()