import base64
from typing import Optional

from dotenv import load_dotenv
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from nltk.tokenize import sent_tokenize, word_tokenize
from openai import OpenAI
from pydantic import BaseModel, Field

# Import-time env loading keeps the OpenAI client and LangChain models
# configured no matter which entrypoint imports this shared module.
load_dotenv()

