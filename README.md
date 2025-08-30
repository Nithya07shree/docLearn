## Setup:
1. Install required libs: pip install -r requirements.txt 
2. Set up Google cloud : enable Vertex AI, create service account, export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
3. Run: python main.py --file doc3.pdf --jurisdiction India --role client

## Input:
File (.pdf or .docx)
Jurisdiction(preferably country name like India, UK, USA...)
Role of User(lawyer/client/vendor ...)

## Output:
 {
    "clause_number": ,
    "clause_text": ,
    "clause_risk": "low/medium/high",
    "negotiation": 
}