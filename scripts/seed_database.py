import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from faker import Faker
from loguru import logger
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import get_session, init_db
from db.models import Category, Customer, Order, OrderItem, Product

fake = Faker("pt_BR")
random.seed(42)

CATEGORIES = [
    ("Eletrônicos", "Smartphones, notebooks, tablets e acessórios"),
    ("Roupas Masculinas", "Camisas, calças, tênis e acessórios masculinos"),
    ("Roupas Femininas", "Vestidos, blusas, calçados e bolsas"),
    ("Casa & Decoração", "Móveis, decoração e utilidades domésticas"),
    ("Esportes", "Equipamentos e roupas esportivas"),
    ("Livros", "Livros físicos e e-books"),
    ("Alimentos & Bebidas", "Produtos alimentícios e bebidas artesanais"),
    ("Beleza & Saúde", "Cosméticos, perfumes e suplementos"),
    ("Brinquedos", "Brinquedos, jogos e hobbies"),
    ("Informática", "Computadores, periféricos e software"),
    ("Automotivo", "Peças, acessórios e cuidados com veículos"),
    ("Jardinagem", "Plantas, ferramentas e decoração external"),
    ("Pets", "Ração, acessórios e cuidados para animais"),
    ("Música", "Instrumentos, equipamentos de som e CDs"),
    ("Viagem", "Malas, mochilas e acessórios de viagem"),
]

PRODUCTS_BY_CATEGORY = {
    "Eletrônicos": [
        ("Smartphone Samsung Galaxy S24", 3299, 1800),
        ("iPhone 15 128GB", 5499, 3200),
        ("Notebook Dell Inspiron 15", 3899, 2100),
        ("Tablet iPad Air", 4299, 2500),
        ("Smartwatch Apple Watch SE", 1899, 950),
        ("Fone Bluetooth JBL Tune 770", 399, 180),
    ],
    "Informática": [
        ("Monitor LG 27'' 4K", 2199, 1200),
        ("Teclado Mecânico Keychron K2", 599, 280),
        ("Mouse Logitech MX Master 3", 549, 250),
        ("SSD Samsung 1TB NVMe", 449, 200),
        ("Webcam Logitech C920", 399, 180),
    ],
    "Roupas Masculinas": [
        ("Camiseta Nike Dri-FIT", 149, 55),
        ("Calça Jeans Levi's 511", 299, 120),
        ("Tênis Adidas Ultraboost", 699, 280),
        ("Camisa Social Hering", 129, 45),
    ],
    "Roupas Femininas": [
        ("Vestido Farm Floral", 249, 90),
        ("Tênis Nike Air Max", 599, 230),
        ("Bolsa Michael Kors", 899, 350),
        ("Blusa Zara Básica", 129, 40),
    ],
    "Esportes": [
        ("Bicicleta Speed Trek Domane", 6999, 3500),
        ("Halteres Ajustáveis 20kg", 389, 150),
        ("Tapete Yoga Premium", 129, 45),
        ("Raquete Beach Tennis", 299, 110),
    ],
    "Livros": [
        ("Clean Code - Robert Martin", 89, 30),
        ("Designing Data-Intensive Apps", 119, 45),
        ("O Poder do Hábito", 49, 18),
        ("Sapiens - Yuval Harari", 59, 22),
    ],
    "Alimentos & Bebidas": [
        ("Café Especial Grão Direto 250g", 49, 18),
        ("Vinho Cabernet Miolo Reserva", 89, 32),
        ("Kit Cervejas Artesanais 6un", 119, 45),
        ("Azeite Extra Virgem Português 500ml", 79, 28),
    ],
    "Beleza & Saúde": [
        ("Perfume Chanel Nº5 100ml", 899, 400),
        ("Proteína Whey Optimum 900g", 189, 75),
        ("Kit Skincare Neutrogena", 149, 55),
        ("Vitamina D3 + K2 60caps", 69, 22),
    ],
    "Brinquedos": [
        ("LEGO Technic Bugatti", 1299, 550),
        ("Boneca Barbie Fashionista", 129, 45),
        ("Hot Wheels Pista de Acrobacias", 199, 70),
    ],
    "Casa & Decoração": [
        ("Cafeteira Nespresso Essenza", 699, 300),
        ("Aspirador Robô Roomba i3", 1899, 850),
        ("Jogo de Panelas Tramontina", 499, 190),
        ("Luminária LED de Mesa", 179, 65),
    ],
    "Automotivo": [
        ("Suporte Veicular Celular", 79, 25),
        ("Câmera de Ré Multilaser", 199, 70),
        ("Kit Limpeza Automotiva", 129, 40),
    ],
    "Jardinagem": [
        ("Kit Ferramentas de Jardim", 149, 50),
        ("Vaso Autoirrigável Grande", 89, 28),
    ],
    "Pets": [
        ("Ração Royal Canin Golden 15kg", 299, 120),
        ("Cama Ortopédica para Cão G", 229, 85),
        ("Brinquedo Kong Classic", 79, 25),
    ],
    "Música": [
        ("Violão Yamaha F310", 599, 250),
        ("Controlador MIDI Arturia", 1299, 550),
    ],
    "Viagem": [
        ("Mala de Viagem Samsonite M", 799, 320),
        ("Mochila Osprey 40L", 899, 360),
        ("Cadeado TSA Pacsafe", 129, 40),
    ],
}

STATES = ["SP", "RJ", "MG", "RS", "BA", "PR", "SC", "GO", "PE", "CE",
          "AM", "MA", "PA", "MT", "MS", "ES", "RO", "TO", "PB", "RN"]
SEGMENTS = ["B2C"] * 70 + ["B2B"] * 20 + ["VIP"] * 10  # distribuição realista
CHANNELS = ["web"] * 50 + ["app"] * 35 + ["marketplace"] * 15
STATUSES = ["delivered"] * 60 + ["shipped"] * 15 + ["confirmed"] * 10 + \
           ["pending"] * 10 + ["cancelled"] * 5


def seed(n_customers: int = 500, n_orders: int = 5000) -> None:
    init_db()

    with get_session() as session:

        for model in [OrderItem, Order, Customer, Product, Category]:
            session.query(model).delete()
        session.commit()
        logger.info("Dados anteriores removidos")

        cat_objs: dict[str, Category] = {}
        for name, desc in CATEGORIES:
            cat = Category(name=name, description=desc)
            session.add(cat)
            cat_objs[name] = cat
        session.flush()
        logger.info(f"{len(cat_objs)} categorias inseridas")

        prod_objs: list[Product] = []
        prod_id = 1
        for cat_name, products in PRODUCTS_BY_CATEGORY.items():
            cat = cat_objs.get(cat_name)
            if not cat:
                continue
            for pname, price, cost in products:
                prod = Product(
                    id=prod_id,
                    name=pname,
                    category_id=cat.id,
                    price=Decimal(str(price)),
                    cost=Decimal(str(cost)),
                    stock_quantity=random.randint(0, 500),
                    is_active=random.random() > 0.05,
                )
                session.add(prod)
                prod_objs.append(prod)
                prod_id += 1
        session.flush()
        logger.info(f"{len(prod_objs)} produtos inseridos")

        customer_objs: list[Customer] = []
        used_emails: set[str] = set()
        for i in range(n_customers):
            email = fake.email()
            while email in used_emails:
                email = fake.email()
            used_emails.add(email)

            c = Customer(
                id=i + 1,
                name=fake.name(),
                email=email,
                state=random.choice(STATES),
                city=fake.city(),
                segment=random.choices(["B2C", "B2B", "VIP"], weights=[70, 20, 10])[0],
            )
            session.add(c)
            customer_objs.append(c)
        session.flush()
        logger.info(f"{len(customer_objs)} clientes inseridos")

        base_date = date(2023, 1, 1)
        order_item_id = 1

        for order_idx in range(n_orders):
            customer = random.choice(customer_objs)
            order_date = base_date + timedelta(days=random.randint(0, 730))
            status = random.choices(
                ["delivered", "shipped", "confirmed", "pending", "cancelled"],
                weights=[60, 15, 10, 10, 5],
            )[0]
            channel = random.choices(
                ["web", "app", "marketplace"], weights=[50, 35, 15]
            )[0]

            n_items = random.choices([1, 2, 3, 4], weights=[55, 25, 15, 5])[0]
            items_products = random.sample(prod_objs, min(n_items, len(prod_objs)))

            total = Decimal("0")
            discount_total = Decimal("0")
            freight = Decimal(str(round(random.uniform(0, 35), 2)))
            item_objs = []

            for prod in items_products:
                qty = random.randint(1, 5)
                disc = Decimal(str(random.choice([0, 0, 0, 0.05, 0.10, 0.15, 0.20])))
                subtotal = (prod.price * qty * (1 - disc)).quantize(Decimal("0.01"))
                total += subtotal
                discount_total += (prod.price * qty * disc).quantize(Decimal("0.01"))

                item_objs.append(OrderItem(
                    id=order_item_id,
                    order_id=order_idx + 1,
                    product_id=prod.id,
                    quantity=qty,
                    unit_price=prod.price,
                    discount_pct=disc,
                    subtotal=subtotal,
                ))
                order_item_id += 1

            order = Order(
                id=order_idx + 1,
                customer_id=customer.id,
                order_date=order_date,
                status=status,
                channel=channel,
                total_amount=(total + freight).quantize(Decimal("0.01")),
                discount_amount=discount_total,
                freight=freight,
            )
            session.add(order)
            for item in item_objs:
                session.add(item)

            if (order_idx + 1) % 1000 == 0:
                session.flush()
                logger.info(f"  {order_idx + 1}/{n_orders} pedidos inseridos...")

        session.commit()
        logger.info(f" Seed concluído: {n_orders} pedidos, {n_customers} clientes, {len(prod_objs)} produtos")


if __name__ == "__main__":
    seed()
