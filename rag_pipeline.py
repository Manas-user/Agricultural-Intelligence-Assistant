import os
import glob
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
from typing import List, Dict, Any

from langchain_community.document_loaders import (
    PyPDFLoader, 
    Docx2txtLoader, 
    UnstructuredPowerPointLoader,
    TextLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain.schema import Document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Configuration
DATA_DIRS = ["./data/agriwelfare", "./data/krishi"]
CHROMA_DB_DIR = "./chroma_db"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# LLM Configuration
LLM_MODEL = "gemini-1.5-flash"

class RAGPipeline:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        self.vector_db = None
        self.llm = None
        self.qa_chain = None
        
        self.init_llm()
        self.init_vector_db()

    def init_llm(self):
        if "GOOGLE_API_KEY" not in os.environ:
            logging.warning("GOOGLE_API_KEY environment variable not found. LLM answers will fail unless set.")
            return

        self.llm = ChatGoogleGenerativeAI(
            model=LLM_MODEL,
            temperature=0.2,
            convert_system_message_to_human=True
        )

    def init_vector_db(self):
        if os.path.exists(CHROMA_DB_DIR):
            logging.info("Loading existing Chroma database...")
            self.vector_db = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=self.embeddings)
            self.setup_qa_chain()
        else:
            logging.info("Chroma DB not found. Need to run ingestion.")

    def setup_qa_chain(self):
        if not self.llm or not self.vector_db:
            return

        prompt_template = """
        You are a highly knowledgeable AI agricultural assistant specialized in Indian farming schemes, crop welfare, and government policies (especially in Maharashtra).
        Use the following pieces of context to answer the user's question accurately and professionally.

        STRICT RULES:
        1. YOU MUST ANSWER ONLY IN ENGLISH. If the user asks in Marathi or Hindi, translate your knowledge and answer in English.
        2. Your response must be well-structured, using bullet points or clear paragraphs where appropriate.
        3. Your response MUST be detailed and at least 5-6 lines long. Do not provide short or "one-liner" answers.
        4. If the context does not contain the answer, state that you don't know based on the provided information, but do so in English.
        5. Maintain a helpful and authoritative tone.

        Context:
        {context}

        Question: {question}

        Detailed English Answer:
        """
        
        PROMPT = PromptTemplate(
            template=prompt_template, input_variables=["context", "question"]
        )

        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vector_db.as_retriever(search_kwargs={"k": 4}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": PROMPT}
        )

    def get_files_to_ingest(self) -> List[str]:
        all_files = []
        for data_dir in DATA_DIRS:
            if not os.path.exists(data_dir):
                continue
            for root, _, files in os.walk(data_dir):
                for file in files:
                    all_files.append(os.path.join(root, file))
        return all_files

    def load_document(self, file_path: str) -> List[Document]:
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".pdf":
                loader = PyPDFLoader(file_path)
            elif ext in [".docx", ".doc"]:
                loader = Docx2txtLoader(file_path)
            elif ext in [".pptx", ".ppt"]:
                loader = UnstructuredPowerPointLoader(file_path)
            elif ext == ".txt":
                loader = TextLoader(file_path, encoding="utf-8")
            else:
                logging.info(f"Unsupported file type for {file_path}")
                return []
            return loader.load()
        except Exception as e:
            logging.error(f"Error loading {file_path}: {e}")
            return []

    def ingest_documents(self):
        logging.info("Starting document ingestion...")
        files = self.get_files_to_ingest()
        documents = []
        
        for file_path in files:
            docs = self.load_document(file_path)
            if docs:
                documents.extend(docs)

        if not documents:
            logging.warning("No valid documents found to ingest.")
            return

        logging.info(f"Loaded {len(documents)} document pages/sections. Chunking...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_documents(documents)
        
        logging.info(f"Created {len(chunks)} chunks. Building Vector DB...")
        self.vector_db = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            persist_directory=CHROMA_DB_DIR
        )
        self.setup_qa_chain()
        logging.info("Ingestion complete and Vector DB persisted.")

    def is_agricultural_query(self, query: str) -> bool:
        """
        Guardrail to check if query is related to agriculture/domain.
        Uses the LLM for a quick classification.
        """
        if not self.llm:
            return True # Fallback if no LLM configured yet

        guardrail_prompt = PromptTemplate(
            input_variables=["query"],
            template="""
            Evaluate if the following query is strictly related to agriculture, farming schemes, crop welfare, or agricultural policies (especially in India/Maharashtra).
            Respond with exactly 'YES' if it is related, or 'NO' if it is about sports, coding, general history, entertainment, or unrelated topics.
            
            Query: {query}
            
            Classification:"""
        )
        
        try:
            chain = guardrail_prompt | self.llm
            response = chain.invoke({"query": query}).content.strip().upper()
            return "YES" in response
        except Exception as e:
            logging.error(f"Guardrail check failed: {e}")
            return True # Allow if guardrail fails

    def query(self, query_text: str) -> Dict[str, Any]:
        if not self.qa_chain:
            return {
                "answer": "The RAG pipeline is not fully initialized. Please ensure GOOGLE_API_KEY is set and documents are ingested.",
                "sources": []
            }

        logging.info(f"Evaluating Guardrail for query: '{query_text}'")
        if not self.is_agricultural_query(query_text):
            return {
                "answer": "I am an agricultural assistant. I can only answer questions related to agricultural welfare and policies.",
                "sources": []
            }

        logging.info("Guardrail passed. Retrieving answer...")
        result = self.qa_chain.invoke({"query": query_text})
        
        answer = result["result"]
        source_docs = result["source_documents"]
        
        sources = list(set([doc.metadata.get("source", "Unknown") for doc in source_docs]))
        
        return {
            "answer": answer,
            "sources": sources
        }

if __name__ == "__main__":
    pipeline = RAGPipeline()
    # Uncomment to test ingestion
    # pipeline.ingest_documents()
    # print(pipeline.query("What are the schemes for crop insurance in Maharashtra?"))
