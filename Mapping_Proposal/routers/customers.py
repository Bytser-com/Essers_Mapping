"""Customers endpoints to manage and list customers on SFTP."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..scripts.errors import StorageError
from ..scripts.storage import ensure_customer_directory, list_customers

router = APIRouter()


class CustomerCreate(BaseModel):
    name: str


@router.get('/customers')
async def get_customers():
    """Retrieve list of all customers currently stored on SFTP."""
    try:
        customers = list_customers()
        return {'customers': customers}
    except StorageError as exc:
        raise HTTPException(status_code=500, detail=f'Ophalen van klanten mislukt: {exc}') from exc


@router.post('/customers', status_code=201)
async def create_customer(customer: CustomerCreate):
    """Explicitly create a customer folder on SFTP."""
    try:
        path = ensure_customer_directory(customer.name)
        return {'customer_name': customer.name.strip(), 'path': path}
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
