"""
Título: Proyecto 3 - Tiendita Full-Stack con Persistencia CSV, Pandas y Dashboard
Autor: Jorge Edwin Guevara Ayala
Fecha de creación: 07/10/2026
Descripción: API de la tiendita que guarda el inventario y las ventas en archivos CSV,
             usa Pandas para leer/escribir los datos y expone endpoints de análisis
             para el dashboard del frontend.
"""

from datetime import datetime
from pathlib import Path
import asyncio

import pandas as pd
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


app = FastAPI(title="API Proyecto Tiendita", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Candado global para evitar que dos compras modifiquen el mismo stock al mismo tiempo
lock = asyncio.Lock()

# Rutas de los CSV (relativas a este archivo para que funcione sin importar desde dónde se corra uvicorn)
CARPETA = Path(__file__).resolve().parent
RUTA_PRODUCTOS = CARPETA / "productos.csv"
RUTA_VENTAS = CARPETA / "ventas.csv"

COLUMNAS_PRODUCTOS = ["id", "nombre", "precio", "cantidad"]
COLUMNAS_VENTAS = ["id_venta", "producto_id", "nombre", "precio", "cantidad", "total", "timestamp"]


#Modelos de Pydantic
#Pedir al cliente que su petición debe estructurarse de esta manera.
class crearProducto(BaseModel):
    nombre: str = Field(..., min_length=1, description="Nombre del producto")
    precio: float = Field(..., gt=0, description="Precio del producto")
    cantidad: int = Field(..., ge=0, description="stock del producto")


#La salida de datos de la API debe de estructurarse de esta manera.
class respuestaProducto(BaseModel):
    id: int
    nombre: str
    precio: float
    cantidad: int


#Cuerpo opcional de la compra, si no se manda nada se compra una pieza
class compraProducto(BaseModel):
    cantidad: int = Field(1, ge=1, description="Piezas a comprar")


# ---------- Funciones de apoyo para los CSV ----------

def leerProductos() -> pd.DataFrame:
    # Si el archivo no existe se regresa un DataFrame vacío con las columnas correctas
    if not RUTA_PRODUCTOS.exists():
        return pd.DataFrame(columns=COLUMNAS_PRODUCTOS)
    df = pd.read_csv(RUTA_PRODUCTOS)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_PRODUCTOS)
    df["id"] = df["id"].astype(int)
    df["precio"] = df["precio"].astype(float)
    df["cantidad"] = df["cantidad"].astype(int)
    return df


def guardarProductos(df: pd.DataFrame):
    df[COLUMNAS_PRODUCTOS].to_csv(RUTA_PRODUCTOS, index=False)


def leerVentas() -> pd.DataFrame:
    if not RUTA_VENTAS.exists():
        return pd.DataFrame(columns=COLUMNAS_VENTAS)
    df = pd.read_csv(RUTA_VENTAS)
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_VENTAS)
    return df


def guardarVentas(df: pd.DataFrame):
    df[COLUMNAS_VENTAS].to_csv(RUTA_VENTAS, index=False)


def aDiccionario(fila) -> dict:
    # Convierte una fila de pandas a tipos normales de Python para que FastAPI la pueda serializar
    return {
        "id": int(fila["id"]),
        "nombre": str(fila["nombre"]),
        "precio": float(fila["precio"]),
        "cantidad": int(fila["cantidad"])
    }


# ---------- CRUD de productos ----------

#GET Obtiene lista de productos de mi inventario
@app.get("/productos", response_model=list[respuestaProducto])
def getProductos():
    try:
        df = leerProductos()
        return [aDiccionario(fila) for _, fila in df.iterrows()]
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al leer los productos: {str(error)}"
        )


#GET Obtiene un producto por su ID
@app.get("/productos/{producto_id}", response_model=respuestaProducto)
def getProducto(producto_id: int):
    try:
        df = leerProductos()
        encontrado = df[df["id"] == producto_id]
        if encontrado.empty:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No fue encontrado el producto"
            )
        return aDiccionario(encontrado.iloc[0])
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al consultar el producto: {str(error)}"
        )


#POST Agrega producto a mi inventario (se agrega una fila nueva al CSV)
@app.post("/productos", response_model=respuestaProducto, status_code=status.HTTP_201_CREATED)
async def addProducto(producto: crearProducto):
    try:
        async with lock:
            df = leerProductos()
            nuevo_id = int(df["id"].max()) + 1 if not df.empty else 1
            nuevo_producto = {
                "id": nuevo_id,
                "nombre": producto.nombre,
                "precio": producto.precio,
                "cantidad": producto.cantidad
            }
            nueva_fila = pd.DataFrame([nuevo_producto])
            df = nueva_fila if df.empty else pd.concat([df, nueva_fila], ignore_index=True)
            guardarProductos(df)
        return nuevo_producto
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al agregar el producto: {str(error)}"
        )


#DELETE Borra producto de mi inventario (se reescribe el CSV sin esa fila)
@app.delete("/productos/{producto_id}")
async def deleteProducto(producto_id: int):
    try:
        async with lock:
            df = leerProductos()
            if df[df["id"] == producto_id].empty:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No fue encontrado el producto"
                )
            df = df[df["id"] != producto_id]
            guardarProductos(df)
        return {"Message": "El producto fue eliminado"}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar el producto: {str(error)}"
        )


#POST Compra un producto: descuenta stock y registra la venta en ventas.csv
@app.post("/productos/{producto_id}")
async def comprarProducto(producto_id: int, compra: compraProducto | None = None):
    piezas = compra.cantidad if compra else 1
    try:
        # Sección crítica: leer, validar, descontar y guardar tiene que pasar de un jalón
        async with lock:
            df = leerProductos()
            indice = df.index[df["id"] == producto_id]

            if len(indice) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No existe el ID de ese producto"
                )

            i = indice[0]
            stock = int(df.at[i, "cantidad"])
            if stock <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No hay stock de ese producto"
                )
            if piezas > stock:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Solo quedan {stock} piezas de ese producto"
                )

            await asyncio.sleep(0.05)  # Simula latencia de una operación real
            df.at[i, "cantidad"] = stock - piezas
            guardarProductos(df)

            # Registro de la venta
            ventas = leerVentas()
            nuevo_id_venta = int(ventas["id_venta"].max()) + 1 if not ventas.empty else 1
            precio = float(df.at[i, "precio"])
            venta = {
                "id_venta": nuevo_id_venta,
                "producto_id": int(producto_id),
                "nombre": str(df.at[i, "nombre"]),
                "precio": precio,
                "cantidad": piezas,
                "total": round(precio * piezas, 2),
                "timestamp": datetime.now().isoformat(timespec="seconds")
            }
            nueva_fila = pd.DataFrame([venta])
            ventas = nueva_fila if ventas.empty else pd.concat([ventas, nueva_fila], ignore_index=True)
            guardarVentas(ventas)

        return {"Mensaje": "Producto comprado", "venta": venta}

    except HTTPException:
        # Mantiene el código HTTP de negocio (404/400) sin transformarlo a 500
        raise
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al comprar producto: {str(error)}"
        )


# ---------- Endpoints de análisis para el dashboard ----------

#GET KPIs generales: transacciones, ingresos y producto más vendido
@app.get("/dashboard/kpis")
def getKpis():
    try:
        ventas = leerVentas()
        if ventas.empty:
            return {"total_transacciones": 0, "ingresos_totales": 0.0,
                    "ticket_promedio": 0.0, "producto_estrella": "Sin ventas"}

        total_transacciones = int(len(ventas))
        ingresos_totales = round(float(ventas["total"].sum()), 2)
        # El producto estrella se calcula por piezas vendidas, no por número de tickets
        producto_estrella = str(ventas.groupby("nombre")["cantidad"].sum().idxmax())

        return {
            "total_transacciones": total_transacciones,
            "ingresos_totales": ingresos_totales,
            "ticket_promedio": round(ingresos_totales / total_transacciones, 2),
            "producto_estrella": producto_estrella
        }
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al calcular los KPIs: {str(error)}"
        )


#GET Cantidad vendida por producto (para la gráfica de barras)
@app.get("/dashboard/ventas-por-producto")
def getVentasPorProducto():
    try:
        ventas = leerVentas()
        if ventas.empty:
            return []
        resumen = (
            ventas.groupby("nombre")
            .agg(cantidad_vendida=("cantidad", "sum"), ingresos=("total", "sum"))
            .reset_index()
            .sort_values("cantidad_vendida", ascending=False)
        )
        resumen["cantidad_vendida"] = resumen["cantidad_vendida"].astype(int)
        resumen["ingresos"] = resumen["ingresos"].round(2)
        return resumen.to_dict(orient="records")
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al agrupar ventas por producto: {str(error)}"
        )


#GET Ventas agrupadas por hora (para la gráfica de línea)
@app.get("/dashboard/ventas-por-tiempo")
def getVentasPorTiempo():
    try:
        ventas = leerVentas()
        if ventas.empty:
            return []
        ventas["timestamp"] = pd.to_datetime(ventas["timestamp"])
        # Se redondea cada venta a su hora para poder agruparlas
        ventas["hora"] = ventas["timestamp"].dt.floor("h")
        por_hora = (
            ventas.groupby("hora")
            .agg(cantidad=("cantidad", "sum"), ingresos=("total", "sum"))
            .reset_index()
            .sort_values("hora")
        )
        por_hora["hora"] = por_hora["hora"].dt.strftime("%Y-%m-%d %H:00")
        por_hora["cantidad"] = por_hora["cantidad"].astype(int)
        por_hora["ingresos"] = por_hora["ingresos"].round(2)
        return por_hora.to_dict(orient="records")
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al agrupar ventas por tiempo: {str(error)}"
        )
