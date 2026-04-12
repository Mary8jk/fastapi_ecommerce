from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from fastapi_ecommerce.db_depends import get_async_db
from fastapi_ecommerce.schemas import ReviewCreate, Review as ReviewScheme
from fastapi_ecommerce.models.products import Product as ProductModel
from fastapi_ecommerce.models.reviews import Review as ReviewModel
from fastapi_ecommerce.models.users import User as UserModel
from fastapi_ecommerce.auth import get_current_buyer, get_current_user


router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
)


@router.get("/", status_code=status.HTTP_200_OK)
async def get_all_reviews(db: AsyncSession = Depends(get_async_db)
                          ) -> list[ReviewScheme]:
    """
    Доступ: Разрешён всем (аутентификация не требуется).
    Описание: Возвращает список всех активных отзывов о товарах.
    """
    query = await db.scalars(
        select(ReviewModel).where(ReviewModel.is_active == True))
    db_reviews = query.all()
    return db_reviews


@router.post("/",
             response_model=ReviewScheme,
             status_code=status.HTTP_201_CREATED)
async def create_review(review_obj: ReviewCreate,
                        db: AsyncSession = Depends(get_async_db),
                        current_user: UserModel = Depends(get_current_buyer)
                        ) -> ReviewScheme:
    """
    Доступ: Только аутентифицированные пользователи с ролью "buyer".
    Описание: Создаёт новый отзыв для указанного товара.
    После добавления отзыва пересчитывает средний рейтинг товара
    на основе всех активных оценок (grade) для этого товара.
    """
    get_product = (await db.execute(
        select(ProductModel).where(
            ProductModel.id == review_obj.product_id,
            ProductModel.is_active == True
        )
    )).scalar_one_or_none()
    if get_product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='product not found')
    get_reviews = (await db.execute(select(ReviewModel).where(
        ReviewModel.product_id == review_obj.product_id,
        ReviewModel.user_id == current_user.id,
        ReviewModel.is_active == True
    ))).scalar_one_or_none()
    if get_reviews is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail='review already exist')
    db_review = ReviewModel(**review_obj.model_dump(),
                            user_id=current_user.id)
    db.add(db_review)
    await db.flush()
    # recalc raiting
    await update_product_rating(
        db=db,
        product_id=review_obj.product_id
    )
    await db.commit()
    await db.refresh(db_review)

    return db_review


async def update_product_rating(db: AsyncSession,
                                product_id: int):
    """
    Пересчитывает рейтинг товара.
    """
    result = await db.execute(
        select(func.avg(ReviewModel.grade)).where(
            ReviewModel.product_id == product_id,
            ReviewModel.is_active == True
        )
    )
    avg_rating = result.scalar() or 0.0
    product = await db.get(ProductModel, product_id)
    product.rating = avg_rating


@router.delete("/{review_id}",
               status_code=status.HTTP_200_OK)
async def delete_review(review_id: int,
                        db: AsyncSession = Depends(get_async_db),
                        current_user: UserModel = Depends(get_current_user)
                        ) -> dict:
    """
    Доступ: Автор отзыва или пользователи с ролью "admin".
    Выполняет мягкое удаление отзыва по review_id,
    устанавливая is_active = False.
    После удаления пересчитывает рейтинг товара (rating в таблице products)
    на основе оставшихся активных отзывов.
    """
    review = (await db.execute(select(ReviewModel).where(
        ReviewModel.id == review_id,
        ReviewModel.is_active == True
    ))).scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail='review not found or unactive')
    if review.user_id != current_user.id and current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Only owner review or admin can delete this review')
    await db.execute(update(ReviewModel).where(
        ReviewModel.id == review_id).values(is_active=False))
    await db.flush()
    # recalc raiting
    await update_product_rating(
        db=db,
        product_id=review.product_id
    )
    await db.commit()
    await db.refresh(review)
    return {"message": "Review deleted"}
