"""
Script para poblar Mongo con categorías y productos de prueba.
Correr una sola vez con: python -m app.scripts.seed_catalog
Requiere que MONGODB_URI esté en el .env
"""
from dotenv import load_dotenv

# Igual que en main.py: hay que cargar el .env ANTES de importar app.db,
# porque app.db lee MONGODB_URI apenas se importa.
load_dotenv()

from app.db import categories_collection, products_collection


def seed():
    categories_collection.delete_many({})
    products_collection.delete_many({})

    cat_ropa = categories_collection.insert_one({"name": "Ropa"}).inserted_id
    cat_accesorios = categories_collection.insert_one({"name": "Accesorios"}).inserted_id
    cat_calzado = categories_collection.insert_one({"name": "Calzado"}).inserted_id

    products_collection.insert_many([
        {
            "category_id": cat_ropa,
            "name": "Camiseta básica",
            "description": "Camiseta 100% algodón, varios colores disponibles.",
            "price": 15.0,
        },
        {
            "category_id": cat_ropa,
            "name": "Sudadera",
            "description": "Sudadera con capucha, talla S a XL.",
            "price": 28.0,
        },
        {
            "category_id": cat_accesorios,
            "name": "Gorra",
            "description": "Gorra ajustable, bordado incluido.",
            "price": 12.0,
        },
        {
            "category_id": cat_calzado,
            "name": "Zapatillas",
            "description": "Zapatillas casuales, tallas 38-44.",
            "price": 45.0,
        },
    ])

    print("Catálogo de prueba insertado correctamente.")


if __name__ == "__main__":
    seed()
