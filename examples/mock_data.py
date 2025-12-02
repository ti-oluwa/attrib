#############
# MOCK DATA #
#############
category_data = [
    {
        "id": "1",  # should be int
        "name": "Electronics",
        "description": "Electronic devices and accessories",
    },
    {
        "id": 2,
        "name": "Clothing",
        "description": None,  # optional description
    },
    {
        "id": "3",  # should be int
        "name": "Books",
        "description": "Physical and digital books",
    },
    {
        "id": 4,
        "name": "Home & Garden",
        "description": "Home improvement and garden supplies",
    },
]


product_data = [
    {
        "id": "1",  # should be int
        "name": "Laptop",
        "price": "999.99",  # should be float
        "quantity": "10",  # should be int
        "category": category_data[0],
        "status": "available",
    },
    {
        "id": 2,
        "name": "T-Shirt",
        "price": 19.99,
        "quantity": 50,
        "category": category_data[1],
        "status": "available",
    },
    {
        "id": 3,
        "name": "Python Programming Book",
        "price": "39.99",  # should be float
        "quantity": 25,
        "category": category_data[2],
        "status": "available",
    },
    {
        "id": 4,
        "name": "Garden Hose",
        "price": 29.99,
        "quantity": "0",  # should be int
        "category": category_data[3],
        "status": "out_of_stock",
    },
    {
        "id": 5,
        "name": "Wireless Mouse",
        "price": 25.50,
        "quantity": 100,
        "category": category_data[0],
        "status": "available",
    },
    {
        "id": 6,
        "name": "Jeans",
        "price": "49.99",  # should be float
        "quantity": 30,
        "category": category_data[1],
        "status": "available",
    },
    {
        "id": 7,
        "name": "JavaScript Guide",
        "price": 35.00,
        "quantity": 20,
        "category": category_data[2],
        "status": "available",
    },
    {
        "id": "8",  # should be int
        "name": "Lawn Mower",
        "price": "299.99",  # should be float
        "quantity": 5,
        "category": category_data[3],
        "status": "available",
    },
    {
        "id": 9,
        "name": "USB Cable",
        "price": 9.99,
        "quantity": 200,
        "category": category_data[0],
        "status": "available",
    },
    {
        "id": 10,
        "name": "Winter Jacket",
        "price": 89.99,
        "quantity": 15,
        "category": category_data[1],
        "status": "available",
    },
    {
        "id": "11",  # should be int
        "name": "Database Design Book",
        "price": "44.99",  # should be float
        "quantity": 10,
        "category": category_data[2],
        "status": "available",
    },
    {
        "id": 12,
        "name": "Plant Pot",
        "price": 15.99,
        "quantity": 40,
        "category": category_data[3],
        "status": "available",
    },
    {
        "id": 13,
        "name": "Keyboard",
        "price": 75.00,
        "quantity": 25,
        "category": category_data[0],
        "status": "available",
    },
    {
        "id": 14,
        "name": "Sneakers",
        "price": 69.99,
        "quantity": 20,
        "category": category_data[1],
        "status": "available",
    },
]


customer_data = [
    {
        "id": 1,
        "name": "John Doe",
        "email": "john@doe.com",
        "stock_level": "50",  # should be int
        "products": [product_data[0], product_data[1], product_data[2]],
    },
    {
        "id": 2,
        "name": "Jane Smith",
        "email": "jane.smith@example.com",
        "stock_level": 75,
        "products": [product_data[3], product_data[4], product_data[5]],
    },
    {
        "id": "3",  # should be int
        "name": "Alice Johnson",
        "email": "alice.j@company.org",
        "stock_level": "100",  # should be int
        "products": [product_data[6], product_data[7], product_data[8]],
    },
]
