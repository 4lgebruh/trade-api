# Trade Analysis API

A lightweight API for analyzing trading performance and providing insights.

## Features

- Trade statistics analysis
- Trading coach responses
- Integration with Supabase for data storage

## Deployment on Netlify

This API is designed to be deployed on Netlify as serverless functions.

### Deployment Steps

1. Create a new site on Netlify from Git
2. Connect to your GitHub repository
3. Configure build settings:
   - Build command: `pip install -r requirements.txt`
   - Publish directory: `.`
4. Add environment variables:
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_SERVICE_KEY`: Your Supabase service key

## API Endpoints

Once deployed, the following endpoints will be available:

- `/.netlify/functions/health`: Health check endpoint
- `/.netlify/functions/trade-analysis?user_id=YOUR_USER_ID`: Get trading performance analysis
- `/.netlify/functions/trade-analysis` (POST): Chat with the trading coach

The API automatically redirects `/api/*` routes to the functions, so you can also use:

- `/api/health`
- `/api/trade-analysis`

## Local Development

1. Install the Netlify CLI:
   ```
   npm install -g netlify-cli
   ```

2. Run the dev server:
   ```
   netlify dev
   ```

## Notes

This is a lightweight version of the trade analysis API, optimized for Netlify deployment without heavy ML dependencies to avoid "data is too long" errors. 