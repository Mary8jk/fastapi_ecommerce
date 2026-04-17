from fastapi import FastAPI
from fastapi_ecommerce.routers import (categories,
                                       products,
                                       users,
                                       reviews,
                                       cart,
                                       )


app = FastAPI(title='Market project',
              version='0.1.0')


app.include_router(router=categories.router)
app.include_router(router=products.router)
app.include_router(router=users.router)
app.include_router(router=reviews.router)
app.include_router(router=cart.router)


@app.get('/')
async def root():
    return {"message": "Добро пожаловать в API интернет-магазина!"}
