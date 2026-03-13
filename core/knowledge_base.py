import os
from typing import List, Dict, Optional
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class KnowledgeBase: # Renamed from CloudKnowledgeBase to match your engine
    def __init__(self):
        url: str = os.environ.get("SUPABASE_URL")
        key: str = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            print("WARNING: Supabase credentials missing in .env")
        self.supabase: Client = create_client(url, key)

    def register_document(self, metadata: Dict) -> str:
        """Saves document details to the Supabase 'document_registry' table."""
        try:
            response = self.supabase.table("document_registry").insert(metadata).execute()
            return response.data[0]['id']
        except Exception as e:
            print(f"Error registering document: {e}")
            return ""

    def search_knowledge(self, query: str, category: Optional[str] = None):
        """Finds relevant docs in the cloud."""
        query_builder = self.supabase.table("document_registry").select("*")
        if category:
            query_builder = query_builder.eq("category", category)

        response = query_builder.ilike("summary", f"%{query}%").execute()
        return response.data