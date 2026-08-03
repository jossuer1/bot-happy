"""
Script para poblar Mongo con categorías y celulares de prueba.
Correr una sola vez con: python -m app.scripts.seed_catalog
Requiere que MONGODB_URI esté en el .env
"""

from app.db import categories_collection, products_collection


def seed():
    categories_collection.delete_many({})
    products_collection.delete_many({})

    cat_gama_alta = categories_collection.insert_one({"name": "Gama Alta"}).inserted_id
    cat_gama_media = categories_collection.insert_one({"name": "Gama Media"}).inserted_id
    cat_economicos = categories_collection.insert_one({"name": "Económicos"}).inserted_id

    products_collection.insert_many([
        {
            "category_id": cat_gama_alta,
            "name": "iPhone 15 Pro Max",
            "description": "Celular con pantalla OLED, cámara profesional y procesador A17 Pro.",
            "price": 1200.0,
        },
        {
            "category_id": cat_gama_alta,
            "name": "Samsung Galaxy S25 Ultra",
            "description": "Smartphone premium con cámara avanzada, gran rendimiento y pantalla AMOLED.",
            "price": 1100.0,
        },
        {
            "category_id": cat_gama_media,
            "name": "Samsung Galaxy A55",
            "description": "Celular equilibrado con buena batería, pantalla AMOLED y cámara de alta resolución.",
            "price": 450.0,
        },
        {
            "category_id": cat_gama_media,
            "name": "Xiaomi Redmi Note 14 Pro",
            "description": "Smartphone con excelente relación calidad-precio y gran autonomía.",
            "price": 350.0,
        },
        {
            "category_id": cat_economicos,
            "name": "Motorola Moto G24",
            "description": "Celular económico para uso diario con batería de larga duración.",
            "price": 150.0,
        },
        {
            "category_id": cat_economicos,
            "name": "Xiaomi Redmi 14C",
            "description": "Equipo accesible con pantalla amplia y rendimiento básico.",
            "price": 120.0,
        },
    ])

    print("Catálogo de celulares insertado correctamente.")


if __name__ == "__main__":
    seed()