from openai import OpenAI
import os
from dotenv import load_dotenv
import PyPDF2

load_dotenv()

hansard_format = {
  "type": "object",
  "properties": {
    "document_metadata": {
      "type": "object",
      "description": "High-level metadata about the Hansard document.",
      "properties": {
        "chamber": {
          "type": "string",
          "enum": ["SENATE", "HOUSE_OF_REPRESENTATIVES"],
          "description": "The parliamentary chamber."
        },
        "date": {
          "type": "string",
          "format": "date",
          "description": "The date of the proceedings, in YYYY-MM-DD format."
        },
        "parliament_session": {
          "type": "string",
          "description": "The parliament and session number (e.g., 'FORTY-EIGHTH PARLIAMENT, FIRST SESSION')."
        }
      },
      "required": ["chamber", "date", "parliament_session"]
    },
    "proceedings": {
      "type": "array",
      "description": "A list of all proceedings that occurred during the day, in chronological order.",
      "items": {
        "type": "object",
        "properties": {
          "sequence_id": {
            "type": "integer",
            "description": "The chronological order of the proceeding in the document."
          },
          "type": {
            "type": "string",
            "enum": ["DOCUMENTS", "BILLS", "BUSINESS", "MOTIONS", "NOTICES", "COMMITTEES", "QUESTIONS_WITHOUT_NOTICE", "STATEMENTS_BY_SENATORS", "ADJOURNMENT"],
            "description": "The general category of the proceeding from the Table of Contents."
          },
          "title": {
            "type": "string",
            "description": "The specific title of the bill, motion, or topic being discussed."
          },
          "stage": {
            "type": ["string", "null"],
            "description": "The procedural stage if applicable (e.g., 'Second Reading', 'In Committee'). Null if not applicable."
          },
          "summary": {
            "type": "string",
            "description": "A 2-3 sentence high-level summary of the entire proceeding, including the key issue and outcome if any."
          },
          "key_topics": {
            "type": "array",
            "description": "An array of 5-7 key noun phrases or topics discussed in this proceeding.",
            "items": { "type": "string" }
          },
          "interventions": {
            "type": "array",
            "description": "A list of speeches or significant comments made during the proceeding.",
            "items": {
              "type": "object",
              "properties": {
                "speaker_name": { "type": "string" },
                "speaker_title": { "type": "string", "description": "The speaker's title, including electorate or state." },
                "party": { "type": "string", "description": "The speaker's political party." },
                "stance": { "type": "string", "description": "A brief description of their position (e.g., 'In favor', 'Against', 'Questioning')." },
                "speech_summary": { "type": "string", "description": "A 1-2 sentence summary of the speaker's main arguments." }
              },
              "required": ["speaker_name", "party", "stance", "speech_summary"]
            }
          },
          "vote_result": {
            "type": ["object", "null"],
            "description": "Details of any formal vote (Division) that occurred. Null if no vote.",
            "properties": {
              "outcome": { "type": "string", "enum": ["Agreed to", "Negatived"] },
              "ayes_count": { "type": "integer" },
              "noes_count": { "type": "integer" },
              "ayes_members": { "type": "array", "items": { "type": "string" } },
              "noes_members": { "type": "array", "items": { "type": "string" } }
            },
            "required": ["outcome", "ayes_count", "noes_count"]
          }
        },
        "required": ["sequence_id", "type", "title", "summary", "key_topics"]
      }
    }
  },
  "required": ["document_metadata", "proceedings"]
}

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file"""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Extract text from all pages
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n"
                
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return None
    
    return text

pdf_file_path = "documents/Senate_2025_09_04.pdf"
extracted_text = extract_text_from_pdf(pdf_file_path)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY")
)

completion = client.chat.completions.create(
    extra_body={},
    model="z-ai/glm-4.5-air:free",
    messages=[
        { 
            "role": "system", 
            "content": "You are an expert parliamentary analyst specializing in parsing Australian Hansard documents. Your task is to meticulously extract and structure information from the entire transcript according to the provided JSON schema. Identify each distinct proceeding from the Table of Contents and create a corresponding object in the 'proceedings' array."
        },
        { 
            "role": "user", 
            "content": f"Please parse the following Hansard document and provide the output in the specified JSON format. Here is the full text:\n\n{extracted_text}"
        }
    ],
    response_format={
      "type": "json_schema",
      "json_schema": {
        "name": "hansard_summary",
        "strict": True,
        "schema": hansard_format
      }
    },
)

print(completion)
