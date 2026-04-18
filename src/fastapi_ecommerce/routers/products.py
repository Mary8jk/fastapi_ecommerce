from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy import select, update, func, desc
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Optional
from fastapi_ecommerce.db_depends import get_db, get_async_db
from fastapi_ecommerce.schemas import (Product,
                                       ProductList,
                                       ProductCreate,
                                       Review as ReviewScheme)
from fastapi_ecommerce.models.categories import Category as CategoryModel
from fastapi_ecommerce.models.products import Product as ProductModel
from fastapi_ecommerce.models.users import User as UserModel
from fastapi_ecommerce.models.reviews import Review as ReviewModel
from fastapi_ecommerce.auth import get_current_seller
from pathlib import Path
import uuid


BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_ROOT = BASE_DIR / "media" / "products"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2 097 152 байт

# Создаём маршрутизатор для товаров
router = APIRouter(
    prefix="/products",
    tags=["products"],
)


async def save_product_image(file: UploadFile) -> str:
    """
    Сохраняет изображение товара и возвращает относительный URL.
    """
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Only JPG, PNG or WebP images are allowed")

    content = await file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="Image is too large")

    extension = Path(file.filename or "").suffix.lower() or ".jpg"
    file_name = f"{uuid.uuid4()}{extension}"
    file_path = MEDIA_ROOT / file_name
    file_path.write_bytes(content)

    return f"/media/products/{file_name}"


def remove_product_image(url: str | None) -> None:
    """
    Удаляет файл изображения, если он существует.
    """
    if not url:
        return
    relative_path = url.lstrip("/")
    file_path = BASE_DIR / relative_path
    if file_path.exists():
        file_path.unlink()


@router.get("/",
            response_model=ProductList,
            status_code=status.HTTP_200_OK)
async def get_all_products(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        search: str | None = Query(None, min_length=1,
                                   description="Поиск по названию товара"),
        category_id: int | None = Query(
            None, description="ID категории для фильтрации"),
        min_price: float | None = Query(
            None, ge=0, description="Минимальная цена товара"),
        max_price: float | None = Query(
            None, ge=0, description="Максимальная цена товара"),
        in_stock: bool | None = Query(
            None, description="true — только товары в наличии, false — только без остатка"),
        seller_id: int | None = Query(
            None, description="ID продавца для фильтрации"),
        db: AsyncSession = Depends(get_async_db),
):
    """
    Возвращает список всех активных товаров с поддержкой фильтров.
    """
    # Проверка логики min_price <= max_price
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_price не может быть больше max_price",
        )

    # Формируем список фильтров
    filters = [ProductModel.is_active == True]

    if category_id is not None:
        filters.append(ProductModel.category_id == category_id)
    if min_price is not None:
        filters.append(ProductModel.price >= min_price)
    if max_price is not None:
        filters.append(ProductModel.price <= max_price)
    if in_stock is not None:
        filters.append(ProductModel.stock > 0 if in_stock else ProductModel.stock == 0)
    if seller_id is not None:
        filters.append(ProductModel.seller_id == seller_id)

    # Подсчёт общего количества с учётом фильтров
    total_stmt = select(func.count()).select_from(ProductModel).where(*filters)

    rank_col = None
    if search:
        search_value = search.strip()
        if search_value:
            ts_query = func.websearch_to_tsquery('english', search_value)
            filters.append(ProductModel.tsv.op('@@')(ts_query))
            rank_col = func.ts_rank_cd(ProductModel.tsv, ts_query).label("rank")
            # total с учётом полнотекстового фильтра
            total_stmt = select(func.count()).select_from(ProductModel).where(*filters)

    total = await db.scalar(total_stmt) or 0

    # Основной запрос (если есть поиск — добавим ранг в выборку и сортировку)
    if rank_col is not None:
        products_stmt = (
            select(ProductModel, rank_col)
            .where(*filters)
            .order_by(desc(rank_col), ProductModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(products_stmt)
        rows = result.all()
        items = [row[0] for row in rows]    # сами объекты
        # при желании можно вернуть ранг в ответе
        ranks = [row.rank for row in rows]
    else:
        products_stmt = (
            select(ProductModel)
            .where(*filters)
            .order_by(ProductModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = (await db.scalars(products_stmt)).all()
        ranks = []

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "ranks": ranks,
    }


@router.post("/", response_model=Product,
             status_code=status.HTTP_201_CREATED)
async def create_product(product: ProductCreate = Depends(ProductCreate.as_form),
                         image: UploadFile | None = File(None),
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)
                         ):
    """
    Создаёт новый товар, привязанный к текущему продавцу (только для 'seller').
    """
    category_result = await db.scalars(
        select(CategoryModel).where(
            CategoryModel.id == product.category_id,
            CategoryModel.is_active.is_(True))
    )
    if not category_result.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Category not found or inactive")
    image_url = await save_product_image(image) if image else None
    db_product = ProductModel(**product.model_dump(),
                              seller_id=current_user.id,
                              image_url=image_url)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.get("/category/{category_id}",
            response_model=list[Product],
            status_code=status.HTTP_200_OK)
async def get_products_by_category(category_id: int,
                                   db: AsyncSession = Depends(get_async_db)
                                   ) -> list[Product]:
    """
    Возвращает список товаров в указанной категории по её ID.
    """
    category_query = await db.scalars(select(CategoryModel).where(
        CategoryModel.id == category_id,
        CategoryModel.is_active.is_(True)))
    category = category_query.first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Category not found or inactive')
    products_query = await db.scalars(select(ProductModel).where(
        ProductModel.category_id == category_id,
        ProductModel.is_active.is_(True)))
    products = products_query.all()
    return products


@router.get("/{product_id}",
            response_model=Product,
            status_code=status.HTTP_200_OK)
async def get_product(product_id: int,
                      db: AsyncSession = Depends(get_async_db)) -> Product:
    """
    Возвращает детальную информацию о товаре по его ID.
    """
    query_product = await db.scalars(
        select(ProductModel).where(
            ProductModel.is_active.is_(True),
            ProductModel.id == product_id
        )
    )
    product = query_product.first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Product not found or inactive')
    query_category = await db.scalars(
        select(CategoryModel).where(CategoryModel.is_active.is_(True),
                                    CategoryModel.id == product.category_id))
    category = query_category.first()
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Category not found or inactive'
        )

    return product


@router.put("/{product_id}", response_model=Product)
async def update_product(product_id: int,
                         product: ProductCreate = Depends(ProductCreate.as_form),
                         image: UploadFile | None = File(None),
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)
                         ):
    """
    Обновляет товар, если он принадлежит текущему продавцу
    (только для 'seller').
    """
    result = await db.scalars(select(ProductModel).where(
        ProductModel.id == product_id, ProductModel.is_active.is_(True)))
    db_product = result.first()
    if not db_product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found")
    if db_product.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only update your own products")
    category_result = await db.scalars(
        select(CategoryModel).where(
            CategoryModel.id == product.category_id,
            CategoryModel.is_active.is_(True))
    )
    if not category_result.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Category not found or inactive")
    await db.execute(
        update(ProductModel).where(
            ProductModel.id == product_id).values(**product.model_dump())
    )
    if image:
        remove_product_image(db_product.image_url)
        db_product.image_url = await save_product_image(image)
    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.delete("/{product_id}", response_model=Product)
async def delete_product(product_id: int,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)
                         ):
    """
    Выполняет мягкое удаление товара, если он принадлежит текущему продавцу
    (только для 'seller').
    """
    result = await db.scalars(
        select(ProductModel).where(
            ProductModel.id == product_id,
            ProductModel.is_active.is_(True)
        )
    )
    product = result.first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found or inactive")
    if product.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only delete your own products")
    remove_product_image(product.image_url)
    await db.execute(
        update(ProductModel).where(
            ProductModel.id == product_id).values(is_active=False)
    )
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}/reviews/",
            status_code=status.HTTP_200_OK)
async def get_review_for_product(product_id: int,
                                 db: AsyncSession = Depends(get_async_db)
                                 ) -> list[ReviewScheme]:
    product = (await db.execute(
        select(ProductModel).where(
            ProductModel.id == product_id,
            ProductModel.is_active.is_(True)
        ))).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='product not found or inactive')
    query_reviews = await db.scalars(
        select(ReviewModel).where(
            ReviewModel.product_id == product_id,
            ReviewModel.is_active.is_(True)
        ))
    reviews = query_reviews.all()
    return reviews
