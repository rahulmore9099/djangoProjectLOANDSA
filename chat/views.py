from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import requests
import json
import pandas as pd
import logging
import os
import re
import traceback

logger = logging.getLogger(__name__)

# ==================== BASE DIR ====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ==================== OLLAMA CONFIG ====================
OLLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "tinyllama"

SYSTEM_PROMPT = (
    "You are Neuro, a friendly banking assistant. "
    "Reply in a warm, conversational tone. "
    "Keep responses short (2-4 sentences). "
    "Use emojis occasionally. "
    "Never make up bank data."
)

# ==================== LOAD CSV ====================
CSV_PATH = os.path.join(BASE_DIR, "chat", "bank_loans.csv")
try:
    BANKS_DATA = pd.read_csv(CSV_PATH)
    print(f"✅ Loaded {len(BANKS_DATA)} bank records")
    print(f"✅ Columns: {list(BANKS_DATA.columns)}")
except Exception as e:
    print(f"❌ Error loading CSV: {e}")
    BANKS_DATA = pd.DataFrame()

# ==================== CHAT PAGE ====================
def chat_page(request):
    return render(request, "chat.html")

# ==================== HELPER FUNCTIONS ====================
def extract_salary(text):
    """Extract salary from text - more robust"""
    try:
        patterns = [
            r'earning\s+(\d+)',
            r'earn[s]?\s+(?:rs\.?|₹)?\s*(\d+)',
            r'salary[:\s]*(?:rs\.?|₹)?\s*(\d+)',
            r'(\d{5,6})\s*(?:per\s+month|monthly|salary)?'
        ]
        
        text_lower = text.lower()
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                salary = int(match.group(1))
                # Handle 'k' notation
                if 'k' in text_lower and salary < 1000:
                    salary *= 1000
                # If less than 1000, assume it's in thousands
                elif salary < 1000:
                    salary *= 1000
                return salary
    except Exception as e:
        print(f"Error extracting salary: {e}")
    return None

def detect_loan_type(text):
    """Detect loan type from text"""
    try:
        text_lower = text.lower()
        if any(word in text_lower for word in ['car', 'vehicle', 'auto', 'buy car']):
            return "Car"
        if any(word in text_lower for word in ['home', 'house', 'property', 'housing']):
            return "Home"
        if any(word in text_lower for word in ['personal']):
            return "Personal"
    except Exception as e:
        print(f"Error detecting loan type: {e}")
    return None

def is_greeting(text):
    """Check if message is just a greeting"""
    try:
        greetings = ['hi', 'hello', 'hey', 'good morning', 'good afternoon', 
                     'good evening', 'namaste', 'hola', 'sup', 'yo', 'hii', 'helloo']
        text_lower = text.lower().strip()
        text_clean = text_lower.replace('!', '').replace('?', '').replace('.', '').strip()
        
        words = text_clean.split()
        if len(words) <= 3:
            has_greeting = any(greet == word for greet in greetings for word in words)
            has_loan_keyword = any(keyword in text_clean for keyword in ['loan', 'emi', 'borrow', 'salary', 'earn', 'need'])
            return has_greeting and not has_loan_keyword
    except Exception as e:
        print(f"Error in greeting check: {e}")
    return False

def is_loan_query(text):
    """Check if message is about loans"""
    try:
        text_lower = text.lower()
        has_loan_keyword = any(word in text_lower for word in ['loan', 'emi', 'borrow', 'finance', 'need buy', 'want buy'])
        has_type = any(word in text_lower for word in ['car', 'home', 'personal', 'vehicle', 'house'])
        has_salary = any(char.isdigit() for char in text) or any(word in text_lower for word in ['salary', 'earn', 'income'])
        
        return (has_loan_keyword or has_type) and has_salary
    except Exception as e:
        print(f"Error in loan query check: {e}")
    return False

# ==================== CSV LOGIC ====================
def handle_bank_query(user_message):
    """Handle bank queries with CSV data - WITH TABLES"""
    try:
        if BANKS_DATA.empty:
            print("❌ BANKS_DATA is empty!")
            return None
        
        salary = extract_salary(user_message)
        loan_type = detect_loan_type(user_message)
        
        print(f"🔍 Extracted - Salary: {salary}, Loan Type: {loan_type}")

        if not loan_type:
            print("❌ No loan type detected")
            return None

        # Filter by loan type - handle both column name possibilities
        if "Loan_Type" in BANKS_DATA.columns:
            df = BANKS_DATA[BANKS_DATA["Loan_Type"].str.lower() == loan_type.lower()].copy()
        elif "Loan Type" in BANKS_DATA.columns:
            df = BANKS_DATA[BANKS_DATA["Loan Type"].str.lower() == loan_type.lower()].copy()
        else:
            print(f"❌ Loan type column not found! Available columns: {list(BANKS_DATA.columns)}")
            return None

        print(f"📊 Found {len(df)} loans of type {loan_type}")

        # Filter by salary if provided
        if salary:
            if "Min_Salary" in df.columns:
                df = df[pd.to_numeric(df["Min_Salary"], errors='coerce') <= salary]
            elif "Min Salary" in df.columns:
                df = df[pd.to_numeric(df["Min Salary"], errors='coerce') <= salary]

        if df.empty:
            print(f"❌ No loans found matching criteria")
            return f"""<div class='ai-response'>
<p><strong>⚠️ No {loan_type.lower()} loans found matching your salary of ₹{salary:,}.</strong></p>
<p>Try a different loan type or consider a co-applicant! 😊</p>
</div>"""

        # Sort by interest rate
        interest_col = "Interest_Rate" if "Interest_Rate" in df.columns else "Interest Rate (%)"
        if interest_col in df.columns:
            df = df.sort_values(by=interest_col)
        best = df.iloc[0]
        
        print(f"✅ Best loan found: {best.get('Bank', 'Unknown Bank')}")

        # Build response with safe column access
        def safe_get(row, *possible_names, default="N/A"):
            for name in possible_names:
                if name in row and pd.notna(row[name]):
                    return row[name]
            return default

        # Create table for best loan details
        bank_name = safe_get(best, "Bank")
        interest_rate = safe_get(best, "Interest_Rate", "Interest Rate (%)")
        interest_type = safe_get(best, "Interest_Type", "Interest Type", default="Fixed")
        tenure = safe_get(best, "Tenure")
        processing_fee = safe_get(best, "Processing_Fee", "Processing Fee (%)")
        max_loan = safe_get(best, "Max_Loan_Amount", "Max Loan Amount")
        min_salary = safe_get(best, "Min_Salary", "Min Salary")
        
        # Create comparison table for top 3-5 loans
        top_n = min(5, len(df))
        comparison_rows = ""
        for i in range(top_n):
            bank = df.iloc[i]
            row_class = "highlight" if i == 0 else ""
            bank_name_val = safe_get(bank, "Bank", "Bank Name", "Bank")
            interest_val = safe_get(bank, "Interest_Rate", "Interest Rate (%)")
            fee_val = safe_get(bank, "Processing_Fee", "Processing Fee (%)")
            tenure_val = safe_get(bank, "Tenure")
            max_loan_val = safe_get(bank, "Max_Loan_Amount", "Max Loan Amount")
            
            comparison_rows += f"""
            <tr class="{row_class}">
                <td>{i+1}. {bank_name_val}</td>
                <td class="interest-cell">{interest_val}%</td>
                <td>{tenure_val}</td>
                <td class="fee-cell">{fee_val}%</td>
                <td>₹{str(max_loan_val).replace('.0', '')}</td>
            </tr>
            """

        # Create documents list if available
        documents = safe_get(best, "Required_Documents", "Required Documents")
        documents_html = ""
        if documents and documents != "N/A":
            doc_items = documents.split(",") if "," in documents else [documents]
            documents_html = "<ul style='margin: 8px 0; padding-left: 20px;'>"
            for doc in doc_items:
                documents_html += f"<li style='margin: 4px 0;'>{doc.strip()}</li>"
            documents_html += "</ul>"

        response = f"""<div class="ai-response">
<p><strong>✅ Best {loan_type} Loan for You:</strong></p>

<table class="bank-table">
    <thead>
        <tr>
            <th>Bank</th>
            <th>Interest Rate</th>
            <th>Tenure</th>
            <th>Processing Fee</th>
            <th>Max Loan</th>
            <th>Min Salary</th>
        </tr>
    </thead>
    <tbody>
        <tr class="highlight">
            <td><strong>{bank_name}</strong></td>
            <td class="interest-cell"><strong>{interest_rate}%</strong> ({interest_type})</td>
            <td>{tenure} years</td>
            <td class="fee-cell">{processing_fee}%</td>
            <td>₹{str(max_loan).replace('.0', '')}</td>
            <td>₹{str(min_salary).replace('.0', '')}</td>
        </tr>
    </tbody>
</table>

<div class="comparison-section">
    <p><strong>📊 Top {top_n} {loan_type} Loans Comparison:</strong></p>
    <table class="bank-table">
        <thead>
            <tr>
                <th>Bank</th>
                <th>Interest Rate</th>
                <th>Tenure</th>
                <th>Processing Fee</th>
                <th>Max Loan</th>
            </tr>
        </thead>
        <tbody>
            {comparison_rows}
        </tbody>
    </table>
</div>

<p><strong>📋 Documents Needed:</strong><br>
{documents_html if documents_html else documents}</p>

<p><strong>💡 Recommendation:</strong> {bank_name} offers the best rate at {interest_rate}%. 
Your salary of ₹{salary:,} qualifies you for up to ₹{str(max_loan).replace('.0', '')} loan. 🚀</p>

<p style="font-size: 12px; color: #666; margin-top: 10px;">
    <i>Note: Rates are subject to change. Contact bank for latest details.</i>
</p>
</div>"""
        
        return response

    except Exception as e:
        print(f"❌ ERROR in handle_bank_query: {e}")
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return None

# ==================== OLLAMA FALLBACK (FIXED) ====================
def get_ollama_response(user_message):
    """Get Ollama AI response - FIXED PROMPT & TIMEOUT"""
    try:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": f"{SYSTEM_PROMPT}\n\nUser: {user_message}\nAssistant:",
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": 120,
                "num_ctx": 512,
            }
        }

        response = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
        response.raise_for_status()

        reply = response.json().get("response", "").strip()

        # 🔥 CLEAN unwanted lines (FIX 1)
        reply = re.sub(r"(User:.*|Neuro:.*|Assistant:.*)", "", reply, flags=re.IGNORECASE).strip()

        return reply if reply else None

    except requests.exceptions.Timeout:
        print(f"❌ Ollama timeout (>30 sec)")
        logger.error("Ollama timeout")
        return None
    except Exception as e:
        print(f"❌ Ollama error: {e}")
        logger.error(f"Ollama error: {e}")
        return None

# ==================== HYBRID RESPONSE ====================
def generate_response(user_message):
    """Generate hybrid response with full error handling"""
    try:
        print(f"\n📨 Processing message: {user_message}")
        
        # 1️⃣ Greeting → Ollama
        if is_greeting(user_message):
            print("✅ Detected as greeting")
            ollama_reply = get_ollama_response(user_message)
            if ollama_reply:
                return f"""<div class="ai-response">
<p>{ollama_reply}</p>
<p style="margin-top: 12px;"><strong>💡 I can help with:</strong> Car loans, Home loans, Personal loans!</p>
<p style="font-size: 13px; color: #666;">Try: "I earn 35000, need car loan"</p>
</div>"""
            return """<div class="ai-response">
<p><strong>Hello! 👋 I'm Neuro, your banking assistant.</strong></p>
<p>I can help you find the best loans! Just tell me your salary and loan type.</p>
<p style="margin-top: 10px; font-size: 13px;"><strong>Example:</strong> "I earn 30000, need car loan"</p>
</div>"""
        
        # 2️⃣ Loan Query → CSV with Tables
        if is_loan_query(user_message):
            print("✅ Detected as loan query")
            csv_reply = handle_bank_query(user_message)
            if csv_reply:
                return csv_reply
            
            print("⚠️ No CSV match, providing guidance")
            return """<div class="ai-response">
<p>I'd love to help! Please tell me:</p>
<ul class="chat-list">
<li>Your monthly salary (e.g., "I earn 35000")</li>
<li>What loan you need: Car / Home / Personal</li>
</ul>
<p style="margin-top: 10px;"><strong>Example:</strong> "I earn 40000, need home loan"</p>
</div>"""
        
        # 3️⃣ If asking for all banks
        if "all banks" in user_message.lower() or "compare" in user_message.lower():
            print("✅ Detected as compare banks query")
            csv_reply = handle_bank_query(user_message)
            if csv_reply:
                return csv_reply
        
        # 4️⃣ General Question → Ollama
        print("✅ Treating as general question")
        ollama_reply = get_ollama_response(user_message)
        if ollama_reply:
            return f'<div class="ai-response"><p>{ollama_reply}</p></div>'
        
        return """<div class="ai-response">
<p>I'm here to help with loans! 😊 Ask me about car loans, home loans, or personal loans.</p>
</div>"""
        
    except Exception as e:
        print(f"❌ ERROR in generate_response: {e}")
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return f"<div class='warning-box'><strong>Error:</strong> {str(e)}</div>"

# ==================== CHAT API (FIXED) ====================
@csrf_exempt
def chat_api(request):
    """Chat API endpoint with full error handling"""
    try:
        if request.method != 'POST':
            return JsonResponse({"reply": "<p>Method not allowed.</p>"}, status=405)
        
        data = json.loads(request.body.decode("utf-8"))
        user_message = data.get("message", "").strip()
        
        if not user_message:
            return JsonResponse({"reply": "<p>Please type a message! 😊</p>"}, status=400)

        # 🔧 FIX 3: Handle ping properly (don't send to Ollama)
        if user_message.lower() == "ping":
            return JsonResponse({"reply": "<p>✅ Connected</p>"})

        print(f"\n{'='*50}")
        print(f"📥 Received message: {user_message}")
        
        response = generate_response(user_message)
        
        print(f"📤 Sending response: {response[:100]}...")
        print(f"{'='*50}\n")
        
        return JsonResponse({"reply": response})
        
    except Exception as e:
        print(f"❌ FATAL ERROR in chat_api: {e}")
        print(f"❌ Full traceback: {traceback.format_exc()}")
        logger.error(f"Fatal error: {e}")
        return JsonResponse({
            "reply": f"<div class='warning-box'><strong>⚠️ Server Error:</strong> {str(e)}</div>"
        }, status=500)