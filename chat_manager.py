"""
Chat Manager Module - Persistent Multi-Chat System
Handles saving, loading, and managing multiple chat conversations
"""

import json
import os
from datetime import datetime
from pathlib import Path
import uuid

CHAT_DIR = Path("chat_history")
CHAT_DIR.mkdir(exist_ok=True)


def get_all_chats():
    """Get list of all saved chats with metadata."""
    chats = []
    for file in CHAT_DIR.glob("*.json"):
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                chats.append({
                    'id': file.stem,
                    'name': data.get('name', 'Untitled Chat'),
                    'created': data.get('created', ''),
                    'last_updated': data.get('last_updated', ''),
                    'message_count': len(data.get('messages', []))
                })
        except Exception as e:
            print(f"Error loading chat {file}: {e}")
            continue
    
    # Sort by last updated (most recent first)
    chats.sort(key=lambda x: x.get('last_updated', ''), reverse=True)
    return chats


def create_new_chat(name="New Chat"):
    """Create a new chat and return its ID."""
    chat_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    
    chat_data = {
        'id': chat_id,
        'name': name,
        'created': now,
        'last_updated': now,
        'messages': []
    }
    
    save_chat(chat_id, chat_data)
    return chat_id


def load_chat(chat_id):
    """Load chat history from disk."""
    file_path = CHAT_DIR / f"{chat_id}.json"
    
    if not file_path.exists():
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading chat {chat_id}: {e}")
        return None


def save_chat(chat_id, chat_data):
    """Save chat history to disk."""
    file_path = CHAT_DIR / f"{chat_id}.json"
    
    # Update last_updated timestamp
    chat_data['last_updated'] = datetime.now().isoformat()
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(chat_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving chat {chat_id}: {e}")
        return False


def delete_chat(chat_id):
    """Delete a chat from disk."""
    file_path = CHAT_DIR / f"{chat_id}.json"
    
    try:
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    except Exception as e:
        print(f"Error deleting chat {chat_id}: {e}")
        return False


def rename_chat(chat_id, new_name):
    """Rename an existing chat."""
    chat_data = load_chat(chat_id)
    
    if not chat_data:
        return False
    
    chat_data['name'] = new_name
    return save_chat(chat_id, chat_data)


def add_message_to_chat(chat_id, role, content):
    """Add a message to chat history."""
    chat_data = load_chat(chat_id)
    
    if not chat_data:
        return False
    
    message = {
        'role': role,
        'content': content,
        'timestamp': datetime.now().isoformat()
    }
    
    chat_data['messages'].append(message)
    return save_chat(chat_id, chat_data)


def get_chat_messages(chat_id):
    """Get messages for a specific chat (without timestamps for Claude API)."""
    chat_data = load_chat(chat_id)
    
    if not chat_data:
        return []
    
    # Return messages in format Claude API expects
    return [
        {'role': msg['role'], 'content': msg['content']} 
        for msg in chat_data.get('messages', [])
    ]


def export_chat_as_text(chat_id):
    """Export chat as formatted text."""
    chat_data = load_chat(chat_id)
    
    if not chat_data:
        return None
    
    text = f"Chat: {chat_data['name']}\n"
    text += f"Created: {chat_data['created']}\n"
    text += "=" * 60 + "\n\n"
    
    for msg in chat_data.get('messages', []):
        role = "You" if msg['role'] == 'user' else "Assistant"
        timestamp = msg.get('timestamp', '')[:19].replace('T', ' ')
        text += f"[{timestamp}] {role}:\n{msg['content']}\n\n"
        text += "-" * 60 + "\n\n"
    
    return text


def clear_chat_messages(chat_id):
    """Clear all messages from a chat but keep the chat."""
    chat_data = load_chat(chat_id)
    
    if not chat_data:
        return False
    
    chat_data['messages'] = []
    return save_chat(chat_id, chat_data)
