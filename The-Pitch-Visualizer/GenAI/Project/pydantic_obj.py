from modules import *
parser = StrOutputParser()
# Free-form text is used for plain prompt outputs, while the Pydantic parsers
# below enforce the structured JSON shape we expect from the models.

# Define the Pydantic model
class PromptNeeded(BaseModel):
    c1: str = Field(description="First image description")
    c2: str = Field(description="Second image description")
    c3: str = Field(description="Third image description")
    c4: Optional[str] = Field(default=None, description="Fourth description")
    c5: Optional[str] = Field(default=None, description="Fifth description")

parser2 = PydanticOutputParser(pydantic_object=PromptNeeded)

class Memory(BaseModel):
    environment: str = Field(
        description="Whole environment/background details of the image"
    )
    look: str = Field(
        description="Features of the main subject: looks, dress, hair, expression, etc."
    )
    picture_style: str = Field(
        description="Art style, lighting, color palette, rendering style"
    )
    miscellaneous: str = Field(
        description="Any other details useful for consistent image regeneration"
    )
memory_parser = PydanticOutputParser(pydantic_object=Memory)

prompt_memory = PromptTemplate(
    template="""From this image extract the environment details, look of the person or highlighted thing in the picture and picture style details for better memory for next time image generation. Also extract any other details that can be helpful for image generation.""",
    partial_variables={'instruction':parser2.get_format_instructions()}
)

prompt_text = """
From this image extract the following details for consistent image generation:
- Environment/background details
- Look of the person or main subject (clothes, hair, expression, etc.)
- Art style, lighting, color tone of the image
- Any other details useful for recreating next images consistently

{instruction}
"""

prompt_memory = PromptTemplate(
    template=prompt_text,
    # This prompt is static; only the parser instructions are injected.
    input_variables=[],
    partial_variables={"instruction": memory_parser.get_format_instructions()}
)
