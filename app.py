"""
Yumee Signaling Server
======================
This server manages user connections and relays WebRTC signaling data
between peers for voice, video, and screen sharing.

Hosted on Render.com - always online for your friends to connect.
"""

from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import os
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'yumee-secret-key-change-in-production')

# Enable CORS for all origins (needed for WebSocket connections)
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialize SocketIO with gevent for production (works with Gunicorn)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    manage_session=False
)

# Store connected users: {socket_id: {"name": display_name, "sid": socket_id}}
connected_users = {}

# Store room information for calls: {room_id: [user1_sid, user2_sid]}
active_rooms = {}


@app.route('/')
def index():
    """Health check endpoint."""
    return {
        "status": "online",
        "service": "Yumee Signaling Server",
        "connected_users": len(connected_users),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.route('/health')
def health():
    """Simple health check for monitoring."""
    return {"status": "healthy", "users_online": len(connected_users)}


# ==================== SOCKET EVENT HANDLERS ====================

@socketio.on('connect')
def handle_connect():
    """Handle new client connection."""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'sid': request.sid, 'message': 'Connected to Yumee server'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection - cleanup user from lists."""
    sid = request.sid
    logger.info(f"Client disconnected: {sid}")
    
    if sid in connected_users:
        user_name = connected_users[sid]['name']
        del connected_users[sid]
        
        # Notify all other users that someone left
        emit('user_left', {
            'name': user_name,
            'sid': sid
        }, broadcast=True, include_self=False)
        
        # Update everyone's user list
        broadcast_user_list()
        
        # Clean up any rooms this user was in
        cleanup_user_rooms(sid)


@socketio.on('register')
def handle_register(data):
    """
    Register a user with their display name.
    Called when client first connects with their chosen name.
    """
    try:
        display_name = data.get('name', 'Anonymous').strip()
        
        # Validate name
        if not display_name or len(display_name) > 30:
            display_name = 'Anonymous'
        
        sid = request.sid
        
        # Store user info
        connected_users[sid] = {
            'name': display_name,
            'sid': sid,
            'joined_at': datetime.utcnow().isoformat()
        }
        
        logger.info(f"User registered: {display_name} ({sid})")
        
        # Confirm registration to the user
        emit('registered', {
            'success': True,
            'name': display_name,
            'sid': sid
        })
        
        # Notify others that a new user joined
        emit('user_joined', {
            'name': display_name,
            'sid': sid
        }, broadcast=True, include_self=False)
        
        # Send the complete user list to the newly connected client
        broadcast_user_list()
        
    except Exception as e:
        logger.error(f"Error in register: {e}")
        emit('registered', {'success': False, 'error': str(e)})


@socketio.on('get_users')
def handle_get_users():
    """Send the list of connected users to the requesting client."""
    broadcast_user_list(to_sid=request.sid)


def broadcast_user_list(to_sid=None):
    """
    Broadcast the list of connected users.
    If to_sid is provided, only send to that user. Otherwise broadcast to all.
    """
    user_list = [
        {'name': info['name'], 'sid': sid}
        for sid, info in connected_users.items()
    ]
    
    payload = {'users': user_list}
    
    if to_sid:
        emit('user_list', payload, room=to_sid)
    else:
        emit('user_list', payload, broadcast=True)


# ==================== WEBRTC SIGNALING ====================

@socketio.on('call_user')
def handle_call_user(data):
    """
    Initiate a call to another user.
    Creates a unique room for the call.
    """
    try:
        target_sid = data.get('target_sid')
        caller_sid = request.sid
        
        if target_sid not in connected_users:
            emit('call_error', {'error': 'User is offline'})
            return
        
        if caller_sid == target_sid:
            emit('call_error', {'error': 'Cannot call yourself'})
            return
        
        # Create a unique room ID
        room_id = f"call_{min(caller_sid, target_sid)}_{max(caller_sid, target_sid)}"
        
        # Join both users to the room
        join_room(room_id, sid=caller_sid)
        join_room(room_id, sid=target_sid)
        
        active_rooms[room_id] = [caller_sid, target_sid]
        
        caller_name = connected_users[caller_sid]['name']
        target_name = connected_users[target_sid]['name']
        
        logger.info(f"Call initiated: {caller_name} -> {target_name}, room: {room_id}")
        
        # Notify the target user about incoming call
        emit('incoming_call', {
            'caller_sid': caller_sid,
            'caller_name': caller_name,
            'room_id': room_id
        }, room=target_sid)
        
        # Confirm to caller
        emit('call_initiated', {
            'target_sid': target_sid,
            'target_name': target_name,
            'room_id': room_id
        })
        
    except Exception as e:
        logger.error(f"Error in call_user: {e}")
        emit('call_error', {'error': str(e)})


@socketio.on('accept_call')
def handle_accept_call(data):
    """Accept an incoming call."""
    try:
        room_id = data.get('room_id')
        accepter_sid = request.sid
        
        if room_id not in active_rooms:
            emit('call_error', {'error': 'Call no longer exists'})
            return
        
        # Find the caller (the other person in the room)
        room_users = active_rooms[room_id]
        caller_sid = [u for u in room_users if u != accepter_sid][0]
        
        accepter_name = connected_users[accepter_sid]['name']
        
        logger.info(f"Call accepted by {accepter_name}")
        
        # Notify both users that call is connected
        emit('call_accepted', {
            'accepter_sid': accepter_sid,
            'accepter_name': accepter_name,
            'room_id': room_id
        }, room=room_id)
        
    except Exception as e:
        logger.error(f"Error in accept_call: {e}")
        emit('call_error', {'error': str(e)})


@socketio.on('reject_call')
def handle_reject_call(data):
    """Reject an incoming call."""
    try:
        room_id = data.get('room_id')
        rejecter_sid = request.sid
        
        if room_id in active_rooms:
            room_users = active_rooms[room_id]
            caller_sid = [u for u in room_users if u != rejecter_sid][0]
            
            rejecter_name = connected_users[rejecter_sid]['name']
            
            logger.info(f"Call rejected by {rejecter_name}")
            
            # Notify the caller
            emit('call_rejected', {
                'rejecter_name': rejecter_name
            }, room=caller_sid)
            
            # Clean up the room
            cleanup_room(room_id)
            
    except Exception as e:
        logger.error(f"Error in reject_call: {e}")


@socketio.on('end_call')
def handle_end_call(data):
    """End an active call."""
    try:
        room_id = data.get('room_id')
        ender_sid = request.sid
        
        if room_id in active_rooms:
            ender_name = connected_users.get(ender_sid, {}).get('name', 'Someone')
            
            logger.info(f"Call ended by {ender_name}")
            
            # Notify everyone in the room
            emit('call_ended', {
                'ender_name': ender_name
            }, room=room_id)
            
            # Clean up the room
            cleanup_room(room_id)
            
    except Exception as e:
        logger.error(f"Error in end_call: {e}")


# ==================== WEBRTC SIGNALING MESSAGES ====================

@socketio.on('offer')
def handle_offer(data):
    """
    Relay WebRTC offer from one peer to another.
    This contains the SDP (Session Description Protocol) data.
    """
    try:
        target_sid = data.get('target_sid')
        offer = data.get('offer')
        
        if target_sid and target_sid in connected_users:
            emit('offer', {
                'offer': offer,
                'sender_sid': request.sid,
                'sender_name': connected_users[request.sid]['name']
            }, room=target_sid)
            logger.debug(f"Offer relayed from {request.sid} to {target_sid}")
            
    except Exception as e:
        logger.error(f"Error in offer: {e}")


@socketio.on('answer')
def handle_answer(data):
    """
    Relay WebRTC answer from one peer to another.
    This is the response to an offer.
    """
    try:
        target_sid = data.get('target_sid')
        answer = data.get('answer')
        
        if target_sid and target_sid in connected_users:
            emit('answer', {
                'answer': answer,
                'sender_sid': request.sid
            }, room=target_sid)
            logger.debug(f"Answer relayed from {request.sid} to {target_sid}")
            
    except Exception as e:
        logger.error(f"Error in answer: {e}")


@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    """
    Relay ICE (Interactive Connectivity Establishment) candidates.
    These help peers find the best network path to each other.
    """
    try:
        target_sid = data.get('target_sid')
        candidate = data.get('candidate')
        
        if target_sid and target_sid in connected_users:
            emit('ice_candidate', {
                'candidate': candidate,
                'sender_sid': request.sid
            }, room=target_sid)
            logger.debug(f"ICE candidate relayed from {request.sid} to {target_sid}")
            
    except Exception as e:
        logger.error(f"Error in ice_candidate: {e}")


# ==================== CHAT MESSAGING ====================

@socketio.on('send_message')
def handle_send_message(data):
    """Handle text chat messages between users."""
    try:
        target_sid = data.get('target_sid')
        message = data.get('message', '').strip()
        
        if not message or len(message) > 1000:
            return
            
        sender_sid = request.sid
        sender_name = connected_users.get(sender_sid, {}).get('name', 'Anonymous')
        
        # If target is specified, send private message
        if target_sid and target_sid in connected_users:
            emit('receive_message', {
                'sender_sid': sender_sid,
                'sender_name': sender_name,
                'message': message,
                'private': True
            }, room=target_sid)
            
            # Also show to sender
            emit('receive_message', {
                'sender_sid': sender_sid,
                'sender_name': f"{sender_name} (to {connected_users[target_sid]['name']})",
                'message': message,
                'private': True
            }, room=sender_sid)
        else:
            # Broadcast to all (public message)
            emit('receive_message', {
                'sender_sid': sender_sid,
                'sender_name': sender_name,
                'message': message,
                'private': False
            }, broadcast=True)
            
    except Exception as e:
        logger.error(f"Error in send_message: {e}")


# ==================== UTILITY FUNCTIONS ====================

def cleanup_room(room_id):
    """Remove a room and make users leave it."""
    if room_id in active_rooms:
        users = active_rooms[room_id]
        for user_sid in users:
            leave_room(room_id, sid=user_sid)
        del active_rooms[room_id]
        logger.info(f"Room {room_id} cleaned up")


def cleanup_user_rooms(sid):
    """Clean up all rooms a user was part of."""
    rooms_to_cleanup = []
    for room_id, users in active_rooms.items():
        if sid in users:
            rooms_to_cleanup.append(room_id)
    
    for room_id in rooms_to_cleanup:
        # Notify other user in the room
        other_users = [u for u in active_rooms[room_id] if u != sid]
        for other_sid in other_users:
            emit('call_ended', {
                'ender_name': connected_users.get(sid, {}).get('name', 'Someone'),
                'reason': 'disconnected'
            }, room=other_sid)
        cleanup_room(room_id)


# ==================== MAIN ENTRY POINT ====================

if __name__ == '__main__':
    # Get port from environment (Render sets this) or default to 5000
    port = int(os.environ.get('PORT', 5000))
    
    logger.info(f"Starting Yumee Signaling Server on port {port}")
    logger.info(f"WebSocket endpoint: ws://localhost:{port}/socket.io/")
    
    # Run the server locally (for development/testing)
    # On Render, gunicorn handles this
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False
    )
