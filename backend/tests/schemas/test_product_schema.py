from app.schemas.product import ProductCreate, ProductUpdate


def test_product_create_trims_name():
    body = ProductCreate(name="  PlayStation 5 Pro  ", target_price=649.99, urls=[])
    assert body.name == "PlayStation 5 Pro"


def test_product_update_trims_name():
    body = ProductUpdate(name="  New Name  ")
    assert body.name == "New Name"


def test_product_update_name_none_passes_through():
    body = ProductUpdate(target_price=99.99)
    assert body.name is None
