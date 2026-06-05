"""Idempotent startup seed — runs only when the employees table is empty."""
import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from .models.employee import Employee
from .database import AsyncSessionLocal

SEED_EMPLOYEES = [
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "employee_id": "NW-03241",
        "name": "James Chen",
        "email": "james.chen@northwindlogistics.com",
        "grade": 5,
        "department": "Operations",
        "role_title": "Operations Manager",
        "manager_id": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "employee_id": "NW-05117",
        "name": "Priya Patel",
        "email": "priya.patel@northwindlogistics.com",
        "grade": 4,
        "department": "Logistics Operations",
        "role_title": "Senior Specialist",
        "manager_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
        "employee_id": "NW-07832",
        "name": "Sarah Kim",
        "email": "sarah.kim@northwindlogistics.com",
        "grade": 3,
        "department": "Finance",
        "role_title": "Finance Specialist",
        "manager_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000004"),
        "employee_id": "NW-01985",
        "name": "Marcus Williams",
        "email": "marcus.williams@northwindlogistics.com",
        "grade": 6,
        "department": "Sales",
        "role_title": "Director of Sales",
        "manager_id": None,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000005"),
        "employee_id": "NW-09456",
        "name": "Elena Rodriguez",
        "email": "elena.rodriguez@northwindlogistics.com",
        "grade": 2,
        "department": "Information Technology",
        "role_title": "IT Associate",
        "manager_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
    },
]


async def seed_employees() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Employee).limit(1))
        if result.scalar():
            return  # Already seeded

        for data in SEED_EMPLOYEES:
            db.add(Employee(**data))
        await db.commit()
        print(f"[seed] Inserted {len(SEED_EMPLOYEES)} employees.")
