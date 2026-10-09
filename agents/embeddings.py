"""
agents/embeddings.py
─────────────────────────────────────────────────────────────────────────────
Embedding model settings shared by the crawler (card vectors) and
compare_node (spend-profile vectors). Both sides must use the same model
and size or vector search compares unrelated spaces.

text-embedding-004 was retired by Google; gemini-embedding-001 supports
truncating to 768 dimensions, which keeps the existing Atlas index.
─────────────────────────────────────────────────────────────────────────────
"""

EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
