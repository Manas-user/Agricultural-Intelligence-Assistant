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

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_groq import ChatGroq

from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

# RetrievalQA import used by the current project
from langchain_classic.chains import RetrievalQA

import easyocr
import numpy as np
from pdf2image import convert_from_path


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


# ============================================================
# CONFIGURATION
# ============================================================

DATA_DIRS = [
    "./data/agriwelfare",
    "./data/krishi"
]

CHROMA_DB_DIR = "./chroma_db"

# Multilingual embedding model
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Groq LLM
LLM_MODEL = "openai/gpt-oss-120b"


# ============================================================
# POPPLER CONFIGURATION
# ============================================================

POPPLER_PATH = os.path.expanduser(
    r"~\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\poppler-25.07.0\Library\bin"
)

# Fallback path used by the original project
if not os.path.exists(POPPLER_PATH):
    POPPLER_PATH = os.path.expanduser(
        r"~\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin"
    )


# ============================================================
# RAG PIPELINE
# ============================================================

class RAGPipeline:

    def __init__(self):

        # ----------------------------------------------------
        # Multilingual embeddings
        # ----------------------------------------------------

        self.embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL
        )

        self.vector_db = None
        self.llm = None

        # English chain kept for compatibility
        self.qa_chain = None

        # Separate chains for each answer language
        self.qa_chains = {}

        # ----------------------------------------------------
        # EasyOCR
        # English + Hindi + Marathi
        # ----------------------------------------------------

        logging.info(
            "Initializing EasyOCR for English, Hindi and Marathi..."
        )

        self.ocr_reader = easyocr.Reader(
            ['en', 'hi', 'mr'],
            gpu=False
        )

        # ----------------------------------------------------
        # Initialize LLM
        # ----------------------------------------------------

        self.init_llm()

        # ----------------------------------------------------
        # Initialize ChromaDB
        # ----------------------------------------------------

        self.init_vector_db()


    # ========================================================
    # LLM INITIALIZATION
    # ========================================================

    def init_llm(self):

        if "GROQ_API_KEY" not in os.environ:

            logging.warning(
                "GROQ_API_KEY environment variable not found. "
                "LLM answers will fail unless it is set."
            )

            return

        logging.info(
            f"Initializing Groq LLM with model: {LLM_MODEL}"
        )

        self.llm = ChatGroq(
            model=LLM_MODEL,
            temperature=0.2,
        )

        logging.info(
            "Groq LLM initialized successfully."
        )


    # ========================================================
    # VECTOR DATABASE INITIALIZATION
    # ========================================================

    def init_vector_db(self):

        if (
            os.path.exists(CHROMA_DB_DIR)
            and os.listdir(CHROMA_DB_DIR)
        ):

            logging.info(
                "Loading existing Chroma database..."
            )

            self.vector_db = Chroma(
                persist_directory=CHROMA_DB_DIR,
                embedding_function=self.embeddings
            )

            self.setup_qa_chain()

        else:

            logging.info(
                "Chroma DB not found or empty. "
                "Need to run ingestion."
            )

            self.ingest_documents()


    # ========================================================
    # CREATE LANGUAGE-SPECIFIC QA CHAIN
    # ========================================================

    def create_qa_chain(self, answer_language: str):

        if not self.llm or not self.vector_db:
            return None


        # ----------------------------------------------------
        # ENGLISH PROMPT
        # ----------------------------------------------------

        if answer_language == "English":

            prompt_template = """
You are a highly knowledgeable AI agricultural assistant
specialized in Indian farming schemes, crop welfare,
government policies, and agricultural support programs.

STRICT RULES:

1. Answer ONLY in English.

2. The user's question may be written in English,
   Hindi, Marathi, or a mixture of these languages.
   Understand the question correctly regardless of
   the input language.

3. ONLY use information from the Context below.

4. DO NOT add facts, schemes, statistics, eligibility
   rules, dates, amounts, or details from your own
   general knowledge.

5. Every factual statement in your answer must be
   supported by the provided Context.

6. If the Context does not contain enough information,
   clearly say:
   "Based on the available documents, I could only
   find the following:"
   and provide only the information available in
   the Context.

7. Do not invent missing information.

8. Give a clear, useful and farmer-friendly answer.

9. Use bullet points or short paragraphs where
   appropriate.

10. Give enough detail to properly answer the question.
    Avoid unnecessary repetition.

11. Preserve official scheme names, government
    department names and important technical terms
    accurately.

Context:
{context}

Question:
{question}

Answer:
"""


        # ----------------------------------------------------
        # HINDI PROMPT
        # ----------------------------------------------------

        elif answer_language == "Hindi":

            prompt_template = """
आप भारत में कृषि योजनाओं, किसान कल्याण,
फसल सहायता और सरकारी कृषि नीतियों के विशेषज्ञ
AI कृषि सहायक हैं।

कड़े नियम:

1. उत्तर केवल हिंदी भाषा में दें।
   देवनागरी लिपि का प्रयोग करें।

2. उपयोगकर्ता का प्रश्न अंग्रेज़ी, हिंदी,
   मराठी या इन भाषाओं के मिश्रण में हो सकता है।
   प्रश्न का अर्थ सही तरीके से समझें।

3. उत्तर देने के लिए केवल नीचे दिए गए Context
   की जानकारी का उपयोग करें।

4. अपनी सामान्य जानकारी से कोई तथ्य, योजना,
   आंकड़ा, पात्रता, तारीख, राशि या अन्य जानकारी
   न जोड़ें।

5. आपके उत्तर में दी गई प्रत्येक तथ्यात्मक जानकारी
   नीचे दिए गए Context से समर्थित होनी चाहिए।

6. यदि Context में प्रश्न का पूरा उत्तर उपलब्ध नहीं है,
   तो कहें:
   "उपलब्ध दस्तावेज़ों के आधार पर मुझे निम्नलिखित
   जानकारी मिली है:"
   और केवल उपलब्ध जानकारी दें।

7. जानकारी का अनुमान न लगाएं और कुछ भी न बनाएं।

8. उत्तर किसान के लिए सरल, स्पष्ट और उपयोगी रखें।

9. आवश्यकता होने पर bullet points या छोटे paragraphs
   का उपयोग करें।

10. प्रश्न का पर्याप्त विवरण दें लेकिन अनावश्यक
    दोहराव न करें।

11. सरकारी योजनाओं के आधिकारिक नाम, विभागों के नाम
    और महत्वपूर्ण technical terms को सही रखें।

Context:
{context}

Question:
{question}

उत्तर:
"""


        # ----------------------------------------------------
        # MARATHI PROMPT
        # ----------------------------------------------------

        elif answer_language == "Marathi":

            prompt_template = """
तुम्ही भारतातील कृषी योजना, शेतकरी कल्याण,
पिकांसाठीची मदत आणि सरकारी कृषी धोरणांमध्ये
तज्ज्ञ असलेले AI कृषी सहाय्यक आहात.

कडक नियम:

1. उत्तर फक्त मराठी भाषेत द्या.
   देवनागरी लिपीचा वापर करा.

2. वापरकर्त्याचा प्रश्न इंग्रजी, हिंदी,
   मराठी किंवा या भाषांच्या मिश्रणात असू शकतो.
   प्रश्नाचा अर्थ योग्यरित्या समजून घ्या.

3. उत्तर देण्यासाठी फक्त खाली दिलेल्या Context
   मधील माहितीचा वापर करा.

4. तुमच्या सामान्य ज्ञानातून कोणतेही तथ्य,
   योजना, आकडेवारी, पात्रता, तारीख, रक्कम
   किंवा इतर माहिती जोडू नका.

5. उत्तरातील प्रत्येक तथ्यात्मक माहिती
   खाली दिलेल्या Context मधून समर्थित असावी.

6. जर Context मध्ये प्रश्नाचे पूर्ण उत्तर
   उपलब्ध नसेल, तर असे सांगा:
   "उपलब्ध कागदपत्रांनुसार मला खालील माहिती
   मिळाली आहे:"
   आणि फक्त उपलब्ध माहिती द्या.

7. माहितीचा अंदाज लावू नका आणि कोणतीही
   माहिती स्वतःहून तयार करू नका.

8. उत्तर शेतकऱ्यांसाठी सोपे, स्पष्ट आणि
   उपयुक्त ठेवा.

9. आवश्यक असल्यास bullet points किंवा
   छोटे paragraphs वापरा.

10. प्रश्नाचे पुरेसे स्पष्टीकरण द्या,
    परंतु अनावश्यक पुनरावृत्ती करू नका.

11. सरकारी योजनांची अधिकृत नावे,
    विभागांची नावे आणि महत्त्वाचे technical
    terms अचूक ठेवा.

Context:
{context}

Question:
{question}

उत्तर:
"""


        else:

            # Safety fallback
            logging.warning(
                f"Unknown answer language: {answer_language}. "
                f"Falling back to English."
            )

            answer_language = "English"

            prompt_template = """
You are an AI agricultural assistant specialized
in Indian farming schemes and farmer welfare.

Answer only in English.

ONLY use information from the Context below.
Do not invent facts.

Context:
{context}

Question:
{question}

Answer:
"""


        # ----------------------------------------------------
        # CREATE PROMPT
        # ----------------------------------------------------

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=[
                "context",
                "question"
            ]
        )


        # ----------------------------------------------------
        # CREATE RETRIEVAL QA CHAIN
        # ----------------------------------------------------

        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,

            chain_type="stuff",

            retriever=self.vector_db.as_retriever(
                search_type="mmr",
                search_kwargs={
                    "k": 8,
                    "fetch_k": 20
                }
            ),

            return_source_documents=True,

            chain_type_kwargs={
                "prompt": prompt
            }
        )

        return qa_chain


    # ========================================================
    # SETUP ALL THREE LANGUAGE CHAINS
    # ========================================================

    def setup_qa_chain(self):

        if not self.llm or not self.vector_db:
            return

        logging.info(
            "Setting up multilingual RAG chains..."
        )

        # ----------------------------------------------------
        # English
        # ----------------------------------------------------

        self.qa_chains["English"] = self.create_qa_chain(
            "English"
        )

        # ----------------------------------------------------
        # Hindi
        # ----------------------------------------------------

        self.qa_chains["Hindi"] = self.create_qa_chain(
            "Hindi"
        )

        # ----------------------------------------------------
        # Marathi
        # ----------------------------------------------------

        self.qa_chains["Marathi"] = self.create_qa_chain(
            "Marathi"
        )

        # Keep English chain for backward compatibility
        self.qa_chain = self.qa_chains.get("English")

        logging.info(
            "Multilingual RAG chains ready: "
            "English, Hindi, Marathi"
        )


    # ========================================================
    # GET FILES FOR INGESTION
    # ========================================================

    def get_files_to_ingest(self) -> List[str]:

        all_files = []

        for data_dir in DATA_DIRS:

            if not os.path.exists(data_dir):
                continue

            for root, _, files in os.walk(data_dir):

                for file in files:

                    all_files.append(
                        os.path.join(root, file)
                    )

        return all_files


    # ========================================================
    # DETECT GARBLED PDF TEXT
    # ========================================================

    def has_garbled_text(self, text: str) -> bool:

        """
        Detect garbled Marathi/Hindi text from legacy
        non-Unicode PDF fonts.

        These fonts can produce characters such as:
        Ģ, ȋ, Ǘ, É, Î, etc.
        """

        if not text or len(text.strip()) < 50:
            return False

        garbled_chars = set(
            'ĢȋǗÉÎÅÍĘÁÇÈÊËÌĎĝÂÃÄƺȌȗɕ'
        )

        garbled_count = sum(
            1
            for c in text
            if c in garbled_chars
        )

        ratio = garbled_count / len(text)

        return ratio > 0.01


    # ========================================================
    # PDF CONFIGURATION
    # ========================================================

    MAX_PDF_PAGES = 10


    # ========================================================
    # LOAD PDF + OCR FALLBACK
    # ========================================================

    def load_pdf_with_ocr(
        self,
        file_path: str
    ) -> List[Document]:

        docs = []

        try:

            # ------------------------------------------------
            # First attempt: normal PDF extraction
            # ------------------------------------------------

            loader = PyPDFLoader(file_path)

            docs = loader.load()

            # ------------------------------------------------
            # Limit pages
            # ------------------------------------------------

            if len(docs) > self.MAX_PDF_PAGES:

                logging.info(
                    f"Trimming {file_path} from "
                    f"{len(docs)} to "
                    f"{self.MAX_PDF_PAGES} pages"
                )

                docs = docs[:self.MAX_PDF_PAGES]


            # ------------------------------------------------
            # Check extracted text
            # ------------------------------------------------

            total_text = " ".join(
                doc.page_content.strip()
                for doc in docs
            )

            total_text_length = len(total_text)


            # ------------------------------------------------
            # Normal extraction successful
            # ------------------------------------------------

            if (
                total_text_length > 100
                and not self.has_garbled_text(total_text)
            ):

                logging.info(
                    f"Standard extraction OK for "
                    f"{file_path} "
                    f"({total_text_length} chars, "
                    f"{len(docs)} pages)"
                )

                return docs


            # ------------------------------------------------
            # Garbled text
            # ------------------------------------------------

            if self.has_garbled_text(total_text):

                logging.info(
                    f"Garbled text detected in "
                    f"{file_path}, forcing OCR..."
                )

            else:

                logging.info(
                    f"Too little text in "
                    f"{file_path} "
                    f"({total_text_length} chars), "
                    f"trying OCR..."
                )


        except Exception as e:

            logging.warning(
                f"Standard PDF load failed for "
                f"{file_path}, falling back to OCR: {e}"
            )


        # ====================================================
        # OCR FALLBACK
        # ====================================================

        logging.info(
            f"Running OCR on {file_path}"
        )

        ocr_docs = []

        try:

            images = convert_from_path(
                file_path,
                poppler_path=POPPLER_PATH,
                last_page=self.MAX_PDF_PAGES
            )


            for i, image in enumerate(images):

                img_array = np.array(image)

                results = self.ocr_reader.readtext(
                    img_array,
                    detail=0
                )

                page_text = " ".join(results)


                if page_text.strip():

                    ocr_docs.append(
                        Document(
                            page_content=page_text,
                            metadata={
                                "source": file_path,
                                "page": i,
                                "ocr": True
                            }
                        )
                    )

                    logging.info(
                        f"  OCR page {i}: "
                        f"{len(page_text)} chars extracted"
                    )

                else:

                    logging.warning(
                        f"  OCR page {i}: "
                        f"no text found"
                    )


            if ocr_docs:
                return ocr_docs


            # If OCR failed, return normal extraction
            return docs


        except Exception as e:

            logging.error(
                f"OCR failed for {file_path}: {e}"
            )

            # Last fallback
            return docs


    # ========================================================
    # LOAD DOCUMENT
    # ========================================================

    def load_document(
        self,
        file_path: str
    ) -> List[Document]:

        ext = os.path.splitext(
            file_path
        )[1].lower()

        try:

            # ------------------------------------------------
            # PDF
            # ------------------------------------------------

            if ext == ".pdf":

                return self.load_pdf_with_ocr(
                    file_path
                )


            # ------------------------------------------------
            # DOCX / DOC
            # ------------------------------------------------

            elif ext in [".docx", ".doc"]:

                loader = Docx2txtLoader(
                    file_path
                )

                return loader.load()


            # ------------------------------------------------
            # PowerPoint
            # ------------------------------------------------

            elif ext in [".pptx", ".ppt"]:

                loader = UnstructuredPowerPointLoader(
                    file_path
                )

                return loader.load()


            # ------------------------------------------------
            # TXT
            # ------------------------------------------------

            elif ext == ".txt":

                loader = TextLoader(
                    file_path,
                    encoding="utf-8"
                )

                return loader.load()


            else:

                logging.info(
                    f"Unsupported file type for "
                    f"{file_path}"
                )

                return []


        except Exception as e:

            logging.error(
                f"Error loading {file_path}: {e}"
            )

            return []


    # ========================================================
    # DOCUMENT INGESTION
    # ========================================================

    def ingest_documents(self):

        logging.info(
            "Starting document ingestion..."
        )

        files = self.get_files_to_ingest()

        documents = []


        # ----------------------------------------------------
        # Load every document
        # ----------------------------------------------------

        for file_path in files:

            docs = self.load_document(
                file_path
            )

            if docs:

                documents.extend(docs)


        # ----------------------------------------------------
        # No documents
        # ----------------------------------------------------

        if not documents:

            logging.warning(
                "No valid documents found to ingest."
            )

            return


        logging.info(
            f"Loaded {len(documents)} "
            f"document pages/sections. "
            f"Chunking..."
        )


        # ----------------------------------------------------
        # Multilingual text splitter
        # ----------------------------------------------------

        text_splitter = RecursiveCharacterTextSplitter(

            separators=[
                "\n\n",
                "\n",
                "।",
                ".",
                " ",
                ""
            ],

            chunk_size=1000,

            chunk_overlap=200
        )


        chunks = text_splitter.split_documents(
            documents
        )


        logging.info(
            f"Created {len(chunks)} chunks. "
            f"Building Vector DB..."
        )


        # ----------------------------------------------------
        # Create Chroma DB
        # ----------------------------------------------------

        self.vector_db = Chroma.from_documents(

            documents=chunks,

            embedding=self.embeddings,

            persist_directory=CHROMA_DB_DIR
        )


        # ----------------------------------------------------
        # Setup multilingual chains
        # ----------------------------------------------------

        self.setup_qa_chain()


        logging.info(
            "Ingestion complete and "
            "Vector DB persisted."
        )


    # ========================================================
    # AGRICULTURAL QUERY GUARDRAIL
    # ========================================================

    def is_agricultural_query(
        self,
        query: str
    ) -> bool:

        """
        Multilingual guardrail.

        Checks whether the query is related to:
        agriculture, farming schemes, crop welfare,
        agricultural government policies, or farming.
        """

        if not self.llm:
            return True


        guardrail_prompt = PromptTemplate(

            input_variables=[
                "query"
            ],

            template="""
Evaluate whether the following query is strictly related
to agriculture, farming schemes, crop welfare,
government agricultural policies, farmer welfare,
agricultural programs, or farming techniques.

The query may be written in:
- English
- Hindi
- Marathi
- or a mixture of these languages.

Respond with exactly:

YES

if the query is related to agriculture or farmers.

Respond with exactly:

NO

if it is about unrelated topics such as:
sports, coding, programming, entertainment,
general history, mathematics, or other unrelated topics.

Query:
{query}

Classification:
"""
        )


        try:

            chain = (
                guardrail_prompt
                | self.llm
            )

            response = chain.invoke(
                {
                    "query": query
                }
            ).content.strip().upper()


            return "YES" in response


        except Exception as e:

            logging.error(
                f"Guardrail check failed: {e}"
            )

            # Fail open so legitimate queries
            # are not accidentally blocked
            return True


    # ========================================================
    # NORMALIZE LANGUAGE FROM FRONTEND
    # ========================================================

    def normalize_answer_language(
        self,
        language: str
    ) -> str:

        """
        Converts frontend language codes into
        the internal language names.

        English:
            en
            en-IN
            English

        Hindi:
            hi
            hi-IN
            Hindi

        Marathi:
            mr
            mr-IN
            Marathi
        """

        if not language:
            return "English"


        language = str(
            language
        ).strip().lower()


        # English
        if language in [
            "en",
            "en-in",
            "english"
        ]:

            return "English"


        # Hindi
        if language in [
            "hi",
            "hi-in",
            "hindi"
        ]:

            return "Hindi"


        # Marathi
        if language in [
            "mr",
            "mr-in",
            "marathi"
        ]:

            return "Marathi"


        # Safe fallback
        return "English"


    # ========================================================
    # GUARDRAIL RESPONSE BY LANGUAGE
    # ========================================================

    def get_guardrail_response(
        self,
        answer_language: str
    ) -> str:

        if answer_language == "Hindi":

            return (
                "मैं एक कृषि सहायक हूँ। "
                "मैं केवल खेती, कृषि योजनाओं, "
                "किसानों और कृषि कल्याण से संबंधित "
                "प्रश्नों का उत्तर देता हूँ।"
            )


        if answer_language == "Marathi":

            return (
                "मी एक कृषी सहाय्यक आहे. "
                "मी फक्त शेती, कृषी योजना, "
                "शेतकरी आणि कृषी कल्याणाशी संबंधित "
                "प्रश्नांची उत्तरे देतो."
            )


        return (
            "I am an agricultural assistant. "
            "I only answer questions related to "
            "farming, agricultural schemes, "
            "farmers, and agricultural welfare."
        )


    # ========================================================
    # MAIN QUERY FUNCTION
    # ========================================================

    def query(
        self,
        query_text: str,
        answer_language: str = "English"
    ) -> Dict[str, Any]:

        # ----------------------------------------------------
        # Normalize language
        # ----------------------------------------------------

        answer_language = (
            self.normalize_answer_language(
                answer_language
            )
        )


        # ----------------------------------------------------
        # Validate RAG
        # ----------------------------------------------------

        if not self.qa_chains:

            return {

                "answer": (
                    "The RAG pipeline is not fully "
                    "initialized. Please ensure "
                    "GROQ_API_KEY is set and documents "
                    "are ingested."
                ),

                "sources": [],

                "answer_language": answer_language
            }


        # ----------------------------------------------------
        # Clean query
        # ----------------------------------------------------

        query_text = (
            query_text or ""
        ).strip()


        if not query_text:

            return {

                "answer": (
                    "Please enter a question."
                ),

                "sources": [],

                "answer_language": answer_language
            }


        logging.info(
            f"Evaluating Guardrail for query: "
            f"'{query_text}'"
        )

        logging.info(
            f"Requested answer language: "
            f"{answer_language}"
        )


        # ====================================================
        # AGRICULTURAL GUARDRAIL
        # ====================================================

        if not self.is_agricultural_query(
            query_text
        ):

            return {

                "answer": self.get_guardrail_response(
                    answer_language
                ),

                "sources": [],

                "answer_language": answer_language
            }


        logging.info(
            "Guardrail passed. "
            f"Generating answer in {answer_language}..."
        )


        # ====================================================
        # SELECT LANGUAGE CHAIN
        # ====================================================

        qa_chain = self.qa_chains.get(
            answer_language
        )


        # Safety fallback
        if qa_chain is None:

            logging.warning(
                f"QA chain for {answer_language} "
                f"not found. Falling back to English."
            )

            answer_language = "English"

            qa_chain = self.qa_chains.get(
                "English"
            )


        # ====================================================
        # RAG QUERY
        # ====================================================

        result = qa_chain.invoke(
            {
                "query": query_text
            }
        )


        # ====================================================
        # EXTRACT ANSWER
        # ====================================================

        answer = result.get(
            "result",
            ""
        )


        # ====================================================
        # EXTRACT SOURCES
        # ====================================================

        source_docs = result.get(
            "source_documents",
            []
        )


        sources = list(
            set(
                [
                    doc.metadata.get(
                        "source",
                        "Unknown"
                    )

                    for doc in source_docs
                ]
            )
        )


        # ====================================================
        # RETURN RESPONSE
        # ====================================================

        return {

            "answer": answer,

            "sources": sources,

            "answer_language": answer_language
        }


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    db_exists = (
        os.path.exists(CHROMA_DB_DIR)
        and os.listdir(CHROMA_DB_DIR)
    )


    pipeline = RAGPipeline()


    if not db_exists:

        print(
            "🔄 Running ingestion..."
        )

        pipeline.ingest_documents()


    else:

        print(
            "✅ Using existing DB..."
        )

        pipeline.vector_db = Chroma(

            persist_directory=CHROMA_DB_DIR,

            embedding_function=pipeline.embeddings
        )

        pipeline.setup_qa_chain()