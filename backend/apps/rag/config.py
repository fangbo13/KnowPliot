"""RAG configuration constants."""

from django.conf import settings

# Chunking
CHUNK_SIZE = settings.RAG_CHUNK_SIZE
CHUNK_OVERLAP = settings.RAG_CHUNK_OVERLAP

# Retrieval
TOP_K = settings.RAG_TOP_K
SIMILARITY_THRESHOLD = settings.RAG_SIMILARITY_THRESHOLD

# Models
LLM_MODEL = settings.RAG_LLM_MODEL
EMBEDDING_MODEL = settings.RAG_EMBEDDING_MODEL
EMBEDDING_DIM = settings.RAG_EMBEDDING_DIM

# DashScope / LiteLLM
API_KEY = settings.DASHSCOPE_API_KEY
BASE_URL = settings.LITELLM_BASE_URL
