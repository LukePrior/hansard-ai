from openai import OpenAI
import os
from dotenv import load_dotenv
import PyPDF2
import json

load_dotenv()

# --- Schemas ---

# NEW: A simple schema to parse just the Table of Contents
toc_schema = {
    "type": "array",
    "description": "A list of proceedings extracted from the Table of Contents.",
    "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "The title of the proceeding."},
            "page_start": {"type": "integer", "description": "The starting page number."}
        },
        "required": ["title", "page_start"]
    }
}

# MODIFIED: The schema for a SINGLE proceeding item, not the whole document
# We remove the outer structure and just define the "items" part of the original "proceedings" array.
proceeding_item_schema = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["DOCUMENTS", "BILLS", "BUSINESS", "MOTIONS", "NOTICES", "COMMITTEES", "QUESTIONS_WITHOUT_NOTICE", "STATEMENTS_BY_SENATORS", "ADJOURNMENT", "OTHER"],
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
            "description": "A 2-3 sentence high-level summary of this proceeding chunk, including the key issue and outcome if any."
        },
        "key_topics": {
            "type": "array",
            "description": "An array of 5-7 key noun phrases or topics discussed in this proceeding chunk.",
            "items": { "type": "string" }
        },
        "interventions": {
            "type": "array",
            "description": "A list of speeches or significant comments made during the proceeding chunk.",
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
            "description": "Details of any formal vote (Division) that occurred in this chunk. Null if no vote.",
            "properties": {
              "outcome": { "type": "string", "enum": ["Agreed to", "Negatived"] },
              "ayes_count": { "type": "integer" },
              "noes_count": { "type": "integer" },
              "ayes_members": { "type": "array", "items": { "type": "string" } },
              "noes_members": { "type": "array", "items": { "type": "string" } }
            }
        }
    },
    "required": ["type", "title", "summary", "key_topics"]
}

# --- Helper Functions ---

def extract_text_from_pdf_pages(pdf_path, start_page=None, end_page=None):
    """Extract text from a specific range of pages in a PDF file"""
    text = ""
    page_texts = {}
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)
            
            # Use 1-based indexing for user-friendliness, convert to 0-based for PyPDF2
            start = (start_page - 1) if start_page else 0
            end = (end_page) if end_page else num_pages
            
            for page_num in range(start, end):
                if page_num < num_pages:
                    page = pdf_reader.pages[page_num]
                    page_text = page.extract_text()
                    page_texts[page_num + 1] = page_text # Store with 1-based page number
                    text += page_text + "\n"
                
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return None, None
    
    return text, page_texts

def get_llm_response(client, system_prompt, user_prompt, schema, schema_name):
    """Generic function to call the LLM with a JSON schema."""
    try:
        completion = client.chat.completions.create(
            model="qwen/qwen3-235b-a22b:free", # Using a cheaper, faster model for chunked processing is often sufficient
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema
                }
            },
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"LLM API Error: {e}")
        return None

# --- Main Logic ---

pdf_file_path = "documents/Senate_2025_09_04.pdf"
client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.getenv("OPENROUTER_API_KEY"))

# STEP 1: Extract and Parse Table of Contents (e.g., pages 11-14)
print("Step 1: Parsing Table of Contents...")
toc_text, _ = extract_text_from_pdf_pages(pdf_file_path, start_page=1, end_page=20)
if not toc_text:
    exit("Failed to extract ToC text.")

toc_system_prompt = "Extract the proceedings from this Table of Contents. Ignore page headers/footers. List each main item with its starting page number."
toc_user_prompt = f"Table of Contents Text:\n\n{toc_text}"
parsed_toc = get_llm_response(client, toc_system_prompt, toc_user_prompt, toc_schema, "toc_parser")

if not parsed_toc:
    exit("Failed to parse the Table of Contents.")
print(f"Successfully parsed {len(parsed_toc)} items from the ToC.")

print(parsed_toc)

# STEP 2: Process each proceeding individually
print("\nStep 2: Processing each proceeding...")
_, all_page_texts = extract_text_from_pdf_pages(pdf_file_path) # Get all text, indexed by page number
if not all_page_texts:
    exit("Failed to extract full text.")

all_proceedings = []
for i, item in enumerate(parsed_toc):
    start_page = item['page_start']
    # Determine end page by looking at the next item, or end of document for the last item
    end_page = parsed_toc[i + 1]['page_start'] - 1 if i + 1 < len(parsed_toc) else len(all_page_texts)
    
    print(f"  - Processing '{item['title']}' (Pages {start_page}-{end_page})...")
    
    # Concatenate the text for the relevant pages
    chunk_text = ""
    for page_num in range(start_page, end_page + 1):
        chunk_text += all_page_texts.get(page_num, "")

    if not chunk_text.strip():
        print(f"    - WARNING: No text found for pages {start_page}-{end_page}. Skipping.")
        continue
    
    proc_system_prompt = "You are an expert parliamentary analyst. Parse the following Hansard segment and structure the information according to the JSON schema."
    proc_user_prompt = f"Hansard Segment Text:\n\n{chunk_text}"
    
    # This is the call for a single chunk
    parsed_proceeding = get_llm_response(client, proc_system_prompt, proc_user_prompt, proceeding_item_schema, "proceeding_parser")

    print(parsed_proceeding)
    
    if parsed_proceeding:
        # Add the sequence ID from our loop
        parsed_proceeding['sequence_id'] = i + 1
        all_proceedings.append(parsed_proceeding)
    else:
        print(f"    - FAILED to parse proceeding: {item['title']}")


# STEP 3: Assemble the Final JSON
print("\nStep 3: Assembling final JSON document...")

# Extract metadata (usually from the first page)
metadata_text, _ = extract_text_from_pdf_pages(pdf_file_path, start_page=1, end_page=1)
# (For simplicity, we'll hardcode it, but you could use another small LLM call to extract this)
final_metadata = {
    "chamber": "SENATE",
    "date": "2025-09-04",
    "parliament_session": "FORTY-EIGHTH PARLIAMENT, FIRST SESSION"
}

final_json = {
    "document_metadata": final_metadata,
    "proceedings": all_proceedings
}

# Save to file
output_path = "hansard_summary.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(final_json, f, ensure_ascii=False, indent=2)

print(f"\nProcessing complete! Structured summary saved to {output_path}")