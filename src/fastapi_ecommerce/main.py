from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi_ecommerce.routers import (categories,
                                       products,
                                       users,
                                       reviews,
                                       cart,
                                       orders,
                                       )


app = FastAPI(title='Market project',
              version='0.1.0')

app.mount("/media", StaticFiles(directory="media"), name="media")

app.include_router(router=categories.router)
app.include_router(router=products.router)
app.include_router(router=users.router)
app.include_router(router=reviews.router)
app.include_router(router=cart.router)
app.include_router(router=orders.router)

@app.get('/')
async def root():
    return {"message": "Добро пожаловать в API интернет-магазина!"}
