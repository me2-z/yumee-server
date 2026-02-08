# Yumee Signaling Server

This is the signaling server for **Yumee** - a private communication tool for you and your friends.

## What This Server Does

The signaling server helps Yumee desktop clients:
- Discover who is online
- Establish direct peer-to-peer connections (WebRTC)
- Relay initial handshake messages for voice/video calls
- Send text chat messages

**Important:** The server does NOT handle actual media (audio/video). Media flows directly between peers for privacy and performance.

## API Endpoints

- `GET /` - Server status and health check
- `GET /health` - Simple health check
- WebSocket `/socket.io/` - Real-time communication

## WebSocket Events

### Client → Server
- `register` - Register with display name
- `get_users` - Get list of online users
- `call_user` - Initiate a call
- `accept_call` - Accept incoming call
- `reject_call` - Reject incoming call
- `end_call` - End active call
- `offer` - Send WebRTC offer
- `answer` - Send WebRTC answer
- `ice_candidate` - Send ICE candidate
- `send_message` - Send chat message

### Server → Client
- `connected` - Connection confirmed
- `registered` - Registration confirmed
- `user_list` - List of online users
- `user_joined` - New user joined
- `user_left` - User disconnected
- `incoming_call` - Someone is calling
- `call_initiated` - Your call was initiated
- `call_accepted` - Call was accepted
- `call_rejected` - Call was rejected
- `call_ended` - Call ended
- `offer` - Received WebRTC offer
- `answer` - Received WebRTC answer
- `ice_candidate` - Received ICE candidate
- `receive_message` - Received chat message
- `call_error` - Error in call process

## Deployment on Render.com

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/yumee-server.git
git push -u origin main
```

### Step 2: Deploy on Render
1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Render will auto-detect `render.yaml` and configure everything
5. Click **"Create Web Service"**
6. Wait for deployment (2-3 minutes)
7. Your server URL will be: `https://yumee-server-XXXX.onrender.com`

### Free Tier Limits
- Server sleeps after 15 minutes of inactivity (wakes up on first request)
- 512 MB RAM
- 0.1 CPU
- Perfect for small friend groups!

## Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python server.py

# Server will start on http://localhost:5000
```

## License

Private use only - for you and your friends!
