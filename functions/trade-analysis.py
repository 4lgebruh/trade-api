from http.server import BaseHTTPRequestHandler
import json
import os
from urllib.parse import parse_qs
import supabase

# Try importing transformers, with fallback if it fails
try:
    from transformers import pipeline
    HAS_TRANSFORMERS = True
    print("Successfully loaded transformers library")
    
    # Initialize text generation pipeline with small model specifically designed for text generation
    try:
        generator = pipeline('text-generation', model='distilgpt2', max_length=100)
        print("Successfully loaded distilgpt2 model")
    except Exception as e:
        print(f"Error loading model: {e}")
        generator = None
        HAS_TRANSFORMERS = False
except ImportError:
    print("Transformers library not available, using fallback mode")
    HAS_TRANSFORMERS = False
    generator = None

# Helper function to analyze trades
def analyze_trades(trades):
    if not trades:
        return {
            "win_rate": 0.0,
            "avg_profit_loss": 0.0,
            "strategies": [],
            "strengths": [],
            "weaknesses": [],
            "suggestions": ["Start recording your trades to get personalized analysis."]
        }
    
    # Calculate win rate
    profitable_trades = sum(1 for trade in trades if trade.get('pnl', 0) > 0)
    win_rate = profitable_trades / len(trades) if trades else 0
    
    # Calculate average profit/loss
    total_pnl = sum(trade.get('pnl', 0) for trade in trades)
    avg_pnl = total_pnl / len(trades) if trades else 0
    
    # Extract unique strategies - limit to top 5
    strategies_count = {}
    for trade in trades:
        strategy = trade.get('trade_type', '').strip()
        if strategy:
            strategies_count[strategy] = strategies_count.get(strategy, 0) + 1
    
    # Get most common strategies first
    strategies = sorted(strategies_count.keys(), key=lambda s: strategies_count[s], reverse=True)[:5]
    
    # Generate strengths, weaknesses and suggestions based on the data
    strengths = []
    weaknesses = []
    suggestions = []
    
    # Basic analysis rules
    if win_rate > 0.5:
        strengths.append("Above 50% win rate")
    else:
        weaknesses.append("Below 50% win rate")
        suggestions.append("Focus on improving your win rate by reviewing losing trades")
    
    if avg_pnl > 0:
        strengths.append("Positive average P&L")
    else:
        weaknesses.append("Negative average P&L")
        suggestions.append("Work on improving your average profit per trade")
    
    if len(strategies) > 2:
        strengths.append(f"Diverse trading approaches ({len(strategies)} different strategies)")
    else:
        suggestions.append("Consider exploring more trading strategies to diversify your approach")
    
    # Look for patterns in notes - use sampling for efficiency with large datasets
    sample_size = min(50, len(trades))
    sampled_trades = trades[:sample_size]
    
    all_notes = " ".join([trade.get('notes', '') for trade in sampled_trades if trade.get('notes')])
    if all_notes:
        if "emotion" in all_notes.lower() or "fear" in all_notes.lower() or "greed" in all_notes.lower():
            weaknesses.append("Emotional trading noted in multiple trades")
            suggestions.append("Work on emotional discipline during trading")
        
        if "plan" in all_notes.lower():
            strengths.append("Evidence of trade planning in notes")
            
    return {
        "win_rate": win_rate,
        "avg_profit_loss": avg_pnl,
        "strategies": strategies[:5],  # Ensure we don't return too many
        "strengths": strengths[:3],    # Limit to top 3
        "weaknesses": weaknesses[:3],  # Limit to top 3
        "suggestions": suggestions[:3] # Limit to top 3
    }

# Generate trading coach response using transformers if available, fallback to templates if not
def generate_coach_response(user_message, trade_analysis):
    # Try AI-generated response if transformers is available
    if HAS_TRANSFORMERS and generator is not None:
        try:
            # Create a prompt based on the analysis and user message
            win_rate_percent = round(trade_analysis["win_rate"] * 100, 1)
            avg_pnl = trade_analysis["avg_profit_loss"]
            strategies = ', '.join(trade_analysis["strategies"]) if trade_analysis["strategies"] else 'None recorded'
            strengths = ', '.join(trade_analysis["strengths"]) if trade_analysis["strengths"] else 'None identified'
            weaknesses = ', '.join(trade_analysis["weaknesses"]) if trade_analysis["weaknesses"] else 'None identified'
            
            prompt = f"""
As a professional trading coach, give advice to a trader with:
- Win rate: {win_rate_percent}%
- Average P&L: ${avg_pnl:.2f}
- Strategies: {strategies}
- Strengths: {strengths}
- Weaknesses: {weaknesses}

The trader asks: "{user_message}"

Your helpful advice:"""
            
            # Generate response with transformers
            sequences = generator(prompt, max_length=150, num_return_sequences=1)
            generated_text = sequences[0]['generated_text']
            
            # Extract just the advice part
            advice_part = generated_text.split("Your helpful advice:")[-1].strip()
            
            # Clean up the response
            if advice_part and len(advice_part) >= 10:
                return advice_part[:500]  # Limit response length
                
            # Fallback to templates if generation is empty or too short
            print("AI generation produced too short response, using fallback")
        except Exception as e:
            print(f"Error generating AI response: {e}")
    
    # Fallback to template-based response
    # Create a personalized response based on the analysis
    win_rate_percent = round(trade_analysis["win_rate"] * 100, 1)
    avg_pnl = trade_analysis["avg_profit_loss"]
    
    responses = {
        "how am i doing": f"Based on your trading metrics, you have a {win_rate_percent}% win rate with an average P&L of ${avg_pnl:.2f}. " + 
                        ("Your consistent positive results show good trading discipline. " if avg_pnl > 0 else "Focus on improving your risk management to achieve positive results. "),
        
        "what should i improve": "Based on your trading data, I recommend: " + 
                              (", ".join(trade_analysis["suggestions"]) if trade_analysis["suggestions"] else "Keeping detailed notes on each trade to identify patterns."),
        
        "what are my strengths": "Your trading strengths include: " + 
                              (", ".join(trade_analysis["strengths"]) if trade_analysis["strengths"] else "Not enough data to determine specific strengths yet."),
        
        "what are my weaknesses": "Areas for improvement include: " + 
                               (", ".join(trade_analysis["weaknesses"]) if trade_analysis["weaknesses"] else "Not enough data to determine specific weaknesses yet.")
    }
    
    # Default response if no specific match
    default_response = f"Based on your trading history with a {win_rate_percent}% win rate and ${avg_pnl:.2f} average P&L, "
    default_response += "I recommend focusing on consistency and keeping detailed trade notes."
    
    # Find the best matching response
    for key, response in responses.items():
        if key in user_message.lower():
            return response
    
    return default_response

def query_supabase(user_id):
    # Initialize Supabase client
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        return {"error": "Missing Supabase credentials"}
    
    try:
        client = supabase.create_client(supabase_url, supabase_key)
        # Query trades for the user - limit to 100 recent trades and select only needed columns
        response = client.table("trades").select("id,user_id,trade_type,pnl,notes,entry_date").eq("user_id", user_id).order("entry_date", desc=True).limit(100).execute()
        return {"data": response.data}
    except Exception as e:
        return {"error": str(e)}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Parse query parameters
            params = parse_qs(self.path.split('?')[1]) if '?' in self.path else {}
            user_id = params.get('user_id', [''])[0]
            
            if not user_id:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing user_id parameter"}).encode())
                return
            
            # Query trades from Supabase
            result = query_supabase(user_id)
            
            if "error" in result:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                return
            
            # Analyze trades
            trades = result.get("data", [])
            analysis = analyze_trades(trades)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(analysis).encode())
        
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
    
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            request_data = json.loads(post_data.decode())
            
            user_id = request_data.get('user_id')
            messages = request_data.get('messages', [])
            
            if not user_id:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing user_id"}).encode())
                return
            
            # Get the last user message
            last_message = None
            for msg in reversed(messages):
                if msg.get('role') == "user":
                    last_message = msg.get('content')
                    break
            
            if not last_message:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "No user message found"}).encode())
                return
            
            # Query trades from Supabase
            result = query_supabase(user_id)
            
            if "error" in result:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
                return
            
            # Analyze trades
            trades = result.get("data", [])
            analysis = analyze_trades(trades)
            
            # Generate coach response
            coach_response = generate_coach_response(last_message, analysis)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "response": coach_response,
                "analysis": analysis
            }).encode())
        
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers() 