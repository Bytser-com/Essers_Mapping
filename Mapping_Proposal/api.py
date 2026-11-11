# ai_tool/api.py
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import proposals

load_dotenv()  

app = FastAPI(title="AI Mapping Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(proposals.router)