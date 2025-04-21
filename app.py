from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import supabase
from transformers import pipeline, set_seed
import numpy as np
from datetime import datetime

# Initialize FastAPI app
app = FastAPI(title="Trade Analysis API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Supabase client
def get_supabase_client():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        raise HTTPException(status_code=500, detail="Missing Supabase credentials")
    
    return supabase.create_client(supabase_url, supabase_key)

# Initialize text generation pipeline with distilGPT2
# Using a smaller model to fit within free tier RAM limits
try:
    generator = pipeline('text-generation', model='distilgpt2')
    set_seed(42)  # For reproducibility
except Exception as e:
    print(f"Error loading model: {e}")
    generator = None

# Data models
class Message(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    user_id: str

class TradeAnalysisResult(BaseModel):
    win_rate: float
    avg_profit_loss: float
    strategies: List[str]
    strengths: List[str]
    weaknesses: List[str]
    suggestions: List[str]

# Helper function to extract user ID from Authorization header
async def get_user_id(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    
    # In a real implementation, validate the token with Supabase
    # For now, we'll just extract the user ID from the request body
    return None  # Will be overridden by the request body

# Helper function to analyze trades
def analyze_trades(trades) -> TradeAnalysisResult:
    if not trades:
        return TradeAnalysisResult(
            win_rate=0.0,
            avg_profit_loss=0.0,
            strategies=[],
            strengths=[],
            weaknesses=[],
            suggestions=["Start recording your trades to get personalized analysis."]
        )
    
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
    sampled_trades = trades[:sample_size] if len(trades) <= sample_size else [trades[i] for i in np.random.choice(len(trades), sample_size, replace=False)]
    
    all_notes = " ".join([trade.get('notes', '') for trade in sampled_trades if trade.get('notes')])
    if all_notes:
        if "emotion" in all_notes.lower() or "fear" in all_notes.lower() or "greed" in all_notes.lower():
            weaknesses.append("Emotional trading noted in multiple trades")
            suggestions.append("Work on emotional discipline during trading")
        
        if "plan" in all_notes.lower():
            strengths.append("Evidence of trade planning in notes")
            
    return TradeAnalysisResult(
        win_rate=win_rate,
        avg_profit_loss=avg_pnl,
        strategies=strategies[:5],  # Ensure we don't return too many
        strengths=strengths[:3],    # Limit to top 3
        weaknesses=weaknesses[:3],  # Limit to top 3
        suggestions=suggestions[:3] # Limit to top 3
    )

# Generate trading coach response using distilGPT2
def generate_coach_response(user_message: str, trade_analysis: TradeAnalysisResult) -> str:
    # Create a prompt based on the analysis and user message
    prompt = f"""
You are a professional trading coach giving advice to a trader.
The trader's performance:
- Win rate: {trade_analysis.win_rate:.1%}
- Average P&L: ${trade_analysis.avg_profit_loss:.2f}
- Strategies used: {', '.join(trade_analysis.strategies) if trade_analysis.strategies else 'None recorded'}
- Strengths: {', '.join(trade_analysis.strengths) if trade_analysis.strengths else 'None identified'}
- Weaknesses: {', '.join(trade_analysis.weaknesses) if trade_analysis.weaknesses else 'None identified'}

The trader asks: "{user_message}"

Your helpful advice:
"""
    
    try:
        # If model failed to load, return a fallback response
        if generator is None:
            return "I'm having trouble analyzing your trades right now. Please try again later."
            
        # Generate response (with max length limit to control token usage)
        sequences = generator(prompt, max_length=150, num_return_sequences=1)
        generated_text = sequences[0]['generated_text']
        
        # Extract just the advice part (after "Your helpful advice:")
        advice_part = generated_text.split("Your helpful advice:")[-1].strip()
        
        # Clean up the response
        if not advice_part or len(advice_part) < 10:
            # Fallback if generation is too short or empty
            return "Based on your trading performance, I recommend focusing on consistency and keeping detailed trade notes to identify patterns."
            
        return advice_part
    except Exception as e:
        print(f"Error generating response: {e}")
        return "I'm having trouble analyzing your trades right now. Please try again later."

# Endpoint to get trade statistics
@app.get("/api/trade-analysis", response_model=TradeAnalysisResult)
async def get_trade_analysis(user_id: str, supabase = Depends(get_supabase_client)):
    try:
        # Query trades for the user - limit to 100 recent trades and select only needed columns
        response = supabase.table("trades").select("id,user_id,trade_type,pnl,notes,entry_date").eq("user_id", user_id).order("entry_date", desc=True).limit(100).execute()
        trades = response.data
        
        # Analyze the trades
        analysis = analyze_trades(trades)
        
        # Limit the size of returned data
        if len(analysis.strategies) > 5:
            analysis.strategies = analysis.strategies[:5]
        if len(analysis.strengths) > 3:
            analysis.strengths = analysis.strengths[:3]
        if len(analysis.weaknesses) > 3:
            analysis.weaknesses = analysis.weaknesses[:3]
        if len(analysis.suggestions) > 3:
            analysis.suggestions = analysis.suggestions[:3]
            
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing trades: {str(e)}")

# Chat endpoint
@app.post("/api/chat")
async def chat(request: ChatRequest, supabase = Depends(get_supabase_client)):
    try:
        # Get the last user message
        last_message = None
        for msg in reversed(request.messages):
            if msg.role == "user":
                last_message = msg.content
                break
        
        if not last_message:
            return {"response": "I didn't receive a message to respond to."}
        
        # Get trades for analysis - limit to 100 recent trades to avoid large responses
        response = supabase.table("trades").select("id,user_id,trade_type,pnl,notes,entry_date").eq("user_id", request.user_id).order("entry_date", desc=True).limit(100).execute()
        trades = response.data
        
        # Analyze trades
        analysis = analyze_trades(trades)
        
        # Generate response
        coach_response = generate_coach_response(last_message, analysis)
        
        # Truncate response if it's too long (to avoid Vercel 4.5MB limit)
        if len(coach_response) > 1000:
            coach_response = coach_response[:1000] + "... [response truncated]"
        
        # Limit the number of strategies, strengths, weaknesses, and suggestions
        analysis_dict = analysis.dict()
        if "strategies" in analysis_dict and len(analysis_dict["strategies"]) > 5:
            analysis_dict["strategies"] = analysis_dict["strategies"][:5]
        
        if "strengths" in analysis_dict and len(analysis_dict["strengths"]) > 3:
            analysis_dict["strengths"] = analysis_dict["strengths"][:3]
            
        if "weaknesses" in analysis_dict and len(analysis_dict["weaknesses"]) > 3:
            analysis_dict["weaknesses"] = analysis_dict["weaknesses"][:3]
            
        if "suggestions" in analysis_dict and len(analysis_dict["suggestions"]) > 3:
            analysis_dict["suggestions"] = analysis_dict["suggestions"][:3]
        
        return {
            "response": coach_response,
            "analysis": analysis_dict
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat: {str(e)}")

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 