import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from ..database import get_db
from ..models.employee import Employee

router = APIRouter(prefix="/employees", tags=["employees"])


class EmployeeOut(BaseModel):
    id: uuid.UUID
    employee_id: str
    name: str
    email: str
    grade: int
    department: str
    role_title: str

    model_config = {"from_attributes": True}


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).where(Employee.employee_id == employee_id))
    emp = result.scalar_one_or_none()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


@router.get("/", response_model=list[EmployeeOut])
async def list_employees(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).order_by(Employee.name))
    return result.scalars().all()
