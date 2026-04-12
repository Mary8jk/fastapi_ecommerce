from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Optional
from fastapi_ecommerce.db_depends import get_db, get_async_db
from fastapi_ecommerce.schemas import Product, ProductCreate, Review as ReviewScheme
from fastapi_ecommerce.models.categories import Category as CategoryModel
from fastapi_ecommerce.models.products import Product as ProductModel
from fastapi_ecommerce.models.users import User as UserModel
from fastapi_ecommerce.models.reviews import Review as ReviewModel
from fastapi_ecommerce.auth import get_current_seller

# Создаём маршрутизатор для товаров
router = APIRouter(
    prefix="/products",
    tags=["products"],
)


@router.get("/", status_code=status.HTTP_200_OK)
async def get_all_products(db: AsyncSession = Depends(get_async_db)
                           ) -> list[Product]:
    """
    Возвращает список всех товаров.
    """
    query = await db.scalars(
        select(ProductModel).where(ProductModel.is_active == True))
    db_products = query.all()
    return db_products


@router.post("/", response_model=Product,
             status_code=status.HTTP_201_CREATED)
async def create_product(product: ProductCreate,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)
                         ):
    """
    Создаёт новый товар, привязанный к текущему продавцу (только для 'seller').
    """
    category_result = await db.scalars(
        select(CategoryModel).where(
            CategoryModel.id == product.category_id,
            CategoryModel.is_active == True)
    )
    if not category_result.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Category not found or inactive")
    db_product = ProductModel(**product.model_dump(),
                              seller_id=current_user.id)
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)  # Для получения id и is_active из базы
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
        CategoryModel.is_active == True))
    category = category_query.first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Category not found or inactive')
    products_query = await db.scalars(select(ProductModel).where(
        ProductModel.category_id == category_id,
        ProductModel.is_active == True))
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
            ProductModel.is_active == True,
            ProductModel.id == product_id
        )
    )
    product = query_product.first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='Product not found or inactive')
    query_category = await db.scalars(
        select(CategoryModel).where(CategoryModel.is_active == True,
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
                         product: ProductCreate,
                         db: AsyncSession = Depends(get_async_db),
                         current_user: UserModel = Depends(get_current_seller)
                         ):
    """
    Обновляет товар, если он принадлежит текущему продавцу
    (только для 'seller').
    """
    result = await db.scalars(select(ProductModel).where(
        ProductModel.id == product_id, ProductModel.is_active == True))
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
            CategoryModel.is_active == True)
    )
    if not category_result.first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Category not found or inactive")
    await db.execute(
        update(ProductModel).where(
            ProductModel.id == product_id).values(**product.model_dump())
    )
    await db.commit()
    await db.refresh(db_product)  # Для консистентности данных
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
            ProductModel.is_active == True)
    )
    product = result.first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Product not found or inactive")
    if product.seller_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only delete your own products")
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
            ProductModel.is_active == True
        ))).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='product not found or inactive')
    query_reviews = await db.scalars(
        select(ReviewModel).where(
            ReviewModel.product_id == product_id,
            ReviewModel.is_active == True
        ))
    reviews = query_reviews.all()
    return reviews
