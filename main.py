import asyncio
import argparse
import json
import os
import re
from vertexai.generative_models import GenerativeModel, GenerationConfig
import vertexai
from utils import extract_text_from_pdf, chunk_text, extract_text_from_docx, extract_text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable

# Initialize Vertex AI
def init_vertex_ai():
    try:
        vertexai.init(project="doclearn-470008", location="us-central1")
    except Exception:
        vertexai.init(project="doclearn-470008", location="asia-east1")  # Fallback region

init_vertex_ai()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ResourceExhausted, ServiceUnavailable))
)
async def process_chunk(chunk, role, jurisdiction, model, output_file, is_final_pass=False, total_clauses=0):
    if is_final_pass and total_clauses > 50:
        prompt = (
            f"As a {role} in {jurisdiction}, extract concise numbered clauses from the legal text. Club short clauses under the same topic (e.g., liability, penalties, obligations) into a single clause with combined text. "
            f"Assess their risk (low, medium, high, very high). Very high risk includes clauses with severe financial, legal, or operational impact (e.g., unlimited liability, strict penalties). "
            f"Return a JSON list of objects with: 'clause_number' (string, use the first number if clubbing), 'clause_text' (string, concise and combined for same-topic clauses), "
            f"'clause_risk' (low, medium, high, very high), 'negotiation' ('NIL' for low/medium/high risk, concise negotiation suggestion for very high risk). Ensure valid JSON output. "
            f'Example: [{{"clause_number": "1", "clause_text": "Combined liability clauses...", "clause_risk": "very high", "negotiation": "Limit liability..."}}]. '
            f"Text: {chunk}"
        )
    else:
        prompt = (
            f"As a {role} in {jurisdiction}, extract concise numbered clauses from the legal text. Club short clauses under the same topic (e.g., liability, penalties, obligations) into a single clause with combined text. "
            f"Assess their risk (low, medium, high, very high). Very high risk includes clauses with severe financial, legal, or operational impact (e.g., unlimited liability, strict penalties). "
            f"Return a JSON list of objects with: 'clause_number' (string, use the first number if clubbing), 'clause_text' (string, concise and combined for same-topic clauses), "
            f"'clause_risk' (low, medium, high, very high), 'negotiation' ('NIL' for all risks). Ensure valid JSON output. "
            f'Example: [{{"clause_number": "1", "clause_text": "Combined liability clauses...", "clause_risk": "very high", "negotiation": "NIL"}}]. '
            f"Text: {chunk}"
        )
    try:
        response = await model.generate_content_async(
            prompt,
            generation_config=GenerationConfig(max_output_tokens=4000, temperature=0.2),
            stream=True
        )
        full_response = ""
        async for part in response:
            full_response += part.text
        # Clean response: Remove markdown, extra whitespace
        cleaned_response = re.sub(r'```json\n|```|\n\s*\n', '', full_response).strip()
        try:
            clauses = json.loads(cleaned_response)
            if not clauses:
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"error": "No clauses found in chunk"}) + "\n")
            else:
                if is_final_pass:
                    with open(output_file, "a", encoding="utf-8") as f:
                        for clause in clauses:
                            f.write(json.dumps(clause, ensure_ascii=False) + "\n")
            return clauses
        except json.JSONDecodeError:
            # Fallback: Write chunk as a single clause
            fallback_clause = {
                "clause_number": "unknown",
                "clause_text": chunk[:1000],  # Truncate for safety
                "clause_risk": "medium",
                "negotiation": "NIL"
            }
            if is_final_pass:
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(fallback_clause, ensure_ascii=False) + "\n")
            return [fallback_clause]
    except Exception as e:
        if is_final_pass:
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({"error": f"Processing error: {str(e)}"}) + "\n")
        return []

async def process_document(file_path, role, jurisdiction, chunk_size=1000):
    model = GenerativeModel("gemini-2.0-flash-001")
    output_file = r"E:\Courses\docLearn\backend\output.jsonl"  # Absolute path
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("")
    text = extract_text(file_path)
    if not text:
        with open(output_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"error": "No text extracted from document"}) + "\n")
        return []
    chunks = chunk_text(text, chunk_size)
    all_clauses = []
    # First pass: Collect all clauses
    for chunk in chunks:
        clauses = await process_chunk(chunk, role, jurisdiction, model, output_file, is_final_pass=False)
        all_clauses.extend(clauses)
    # Second pass: If >50 clauses, reprocess for very high risk negotiations
    total_clauses = len([c for c in all_clauses if "error" not in c])
    if total_clauses > 50:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("")  # Clear file for final output
        very_high_clauses = []
        for chunk in chunks:
            clauses = await process_chunk(chunk, role, jurisdiction, model, output_file, is_final_pass=True, total_clauses=total_clauses)
            very_high_clauses.extend([c for c in clauses if c.get("clause_risk") == "very high"])
        # Sort by clause_number and take top 50 very high risk
        very_high_clauses = sorted(very_high_clauses, key=lambda x: x["clause_number"])[:50]
        other_clauses = [c for c in all_clauses if c.get("clause_risk") != "very high" or c in very_high_clauses]
        # Write all clauses to file
        with open(output_file, "a", encoding="utf-8") as f:
            for clause in other_clauses + very_high_clauses:
                if "error" not in clause:
                    f.write(json.dumps(clause, ensure_ascii=False) + "\n")
    else:
        with open(output_file, "a", encoding="utf-8") as f:
            for clause in all_clauses:
                if "error" not in clause:
                    f.write(json.dumps(clause, ensure_ascii=False) + "\n")
    return all_clauses

def main():
    parser = argparse.ArgumentParser(description="Legal Document Analyzer")
    parser.add_argument("--file", required=True, help="Path to PDF/Word file")
    parser.add_argument("--jurisdiction", default="India", help="Jurisdiction (e.g., India)")
    parser.add_argument("--role", default="client", help="User role (e.g., client/vendor/lawyer)")
    args = parser.parse_args()

    asyncio.run(process_document(args.file, args.role, args.jurisdiction))

if __name__ == "__main__":
    main()