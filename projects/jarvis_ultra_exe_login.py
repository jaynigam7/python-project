import json
import os
import threading
import time
from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox
import sqlite3

import google.generativeai as genai
import speech_recognition as sr
import pyttsx3
from langdetect import detect

import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet


# ===================== GEMINI API KEY =====================
GEMINI_API_KEY = "AIzaSyA8Rrz2TMqcexs9hD-PCH1z3z5E9rtNT5A"
MODEL_NAME = "gemini-1.5-flash"
# ==========================================================

DB_FILE = "chat_history.db"
WAKE_WORD = "jarvis"
MIN_SECONDS_BETWEEN_MESSAGES = 2.0


# ------------------ Database ------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user TEXT,
            sender TEXT,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_chat_db(user, sender, message):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chats(timestamp, user, sender, message) VALUES(?,?,?,?)",
        (datetime.now().strftime("%d-%m-%Y %H:%M:%S"), user, sender, message)
    )
    conn.commit()
    conn.close()


def fetch_chats(user=None, sender=None, keyword=None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    query = "SELECT timestamp, user, sender, message FROM chats WHERE 1=1"
    params = []

    if user and user != "all":
        query += " AND user=?"
        params.append(user)

    if sender and sender != "all":
        query += " AND sender=?"
        params.append(sender)

    if keyword and keyword.strip():
        query += " AND message LIKE ?"
        params.append(f"%{keyword.strip()}%")

    query += " ORDER BY id ASC"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


# ------------------ Export ------------------
def export_pdf(filepath, rows):
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph("Chat Export - Jarvis Ultra", styles["Title"]))
    story.append(Spacer(1, 12))

    for ts, user, sender, msg in rows:
        story.append(Paragraph(f"<b>{ts} [{user}] {sender.upper()}:</b> {msg}", styles["BodyText"]))
        story.append(Spacer(1, 8))

    doc = SimpleDocTemplate(filepath, pagesize=A4)
    doc.build(story)


def export_txt(filepath, rows):
    with open(filepath, "w", encoding="utf-8") as f:
        for ts, user, sender, msg in rows:
            f.write(f"{ts} [{user}] {sender.upper()}: {msg}\n")


def export_csv(filepath, rows):
    df = pd.DataFrame(rows, columns=["timestamp", "user", "sender", "message"])
    df.to_csv(filepath, index=False, encoding="utf-8")


# ------------------ Profiles Memory ------------------
def memory_file_for_user(username):
    return f"memory_{username.lower()}.json"


def load_memory(username):
    path = memory_file_for_user(username)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"name": username.title(), "likes": [], "chat_history": [], "notes": []}


def save_memory(username, memory):
    path = memory_file_for_user(username)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=4)


# ------------------ Mood + Language ------------------
def detect_mood(user_text):
    t = user_text.lower()
    happy = ["happy", "great", "awesome", "good", "nice", "love", "excited"]
    sad = ["sad", "bad", "depressed", "tired", "cry", "lonely", "upset"]
    angry = ["angry", "mad", "hate", "irritated", "frustrated"]

    if any(w in t for w in happy):
        return "happy"
    if any(w in t for w in sad):
        return "sad"
    if any(w in t for w in angry):
        return "angry"
    return "neutral"


def detect_language(text):
    try:
        lang = detect(text)
        return lang if lang in ["hi", "en"] else "en"
    except:
        return "en"


# ------------------ Plugins ------------------
def run_plugin(user_text):
    t = user_text.lower().strip()

    if t.startswith("calc "):
        expr = t.replace("calc", "").strip()
        try:
            result = eval(expr, {"__builtins__": {}})
            return f"🧮 Result: {result}"
        except:
            return "⚠️ Invalid calculation. Example: calc 5*10+2"

    if t.startswith("sql "):
        q = t.replace("sql", "").strip()
        return f"🗃️ SQL Tip: Try this query:\n{q}"

    return None


# ------------------ Local Commands ------------------
def local_reply(user_text, memory, current_user):
    t = user_text.lower().strip()

    if t == "/help":
        return f"""Commands:
/help
/time
/export
/exit

Notes:
note <text>
show notes

Voice:
Wake word: "{WAKE_WORD}" (when Wake ON)
Always Listening: toggle ON/OFF
"""

    if t == "/time":
        return f"🕒 {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"

    if "my name is" in t:
        name = t.split("my name is")[-1].strip().title()
        memory["name"] = name
        return f"Nice to meet you {name}! 😄"

    if "i like" in t:
        thing = t.split("i like")[-1].strip().lower()
        if thing and thing not in memory["likes"]:
            memory["likes"].append(thing)
        return f"Saved! You like: {thing} 🧠"

    if t.startswith("note "):
        note_text = t.replace("note", "").strip()
        if note_text:
            memory.setdefault("notes", [])
            memory["notes"].append(note_text)
            return f"📝 Saved note: {note_text}"

    if t == "show notes":
        notes = memory.get("notes", [])
        if not notes:
            return "📝 No notes saved yet."
        return "📝 Your notes:\n" + "\n".join([f"- {n}" for n in notes])

    return None


# ------------------ Gemini Reply ------------------
def gemini_reply(user_text, memory):
    name = memory.get("name", "friend")
    mood = detect_mood(user_text)
    likes = memory.get("likes", [])

    lang = detect_language(user_text)
    language_rule = "Reply in Hindi (Hinglish allowed)." if lang == "hi" else "Reply in English."

    last_chats = memory.get("chat_history", [])[-6:]
    chat_context = "\n".join([f"User: {c}" for c in last_chats])

    system_prompt = f"""
You are Jarvis Ultra, a friendly assistant.
User name: {name}
User mood: {mood}
User likes: {likes}

Rules:
- short, clear, helpful
- {language_rule}
"""

    final_prompt = f"{system_prompt}\n\nContext:\n{chat_context}\n\nUser: {user_text}\nBot:"

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)
    res = model.generate_content(final_prompt)
    return res.text.strip()


# ------------------ Voice ------------------
engine = pyttsx3.init()
engine.setProperty("rate", 170)


def speak(text):
    try:
        engine.say(text)
        engine.runAndWait()
    except:
        pass


def listen_voice_once(timeout=4, phrase_time_limit=6):
    rec = sr.Recognizer()
    rec.energy_threshold = 300
    rec.dynamic_energy_threshold = True

    with sr.Microphone() as src:
        rec.adjust_for_ambient_noise(src, duration=0.6)
        try:
            audio = rec.listen(src, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except:
            return ""

    try:
        text = rec.recognize_google(audio)
        if len(text.strip()) < 2:
            return ""
        return text
    except:
        return ""


# ====================== MAIN CHATBOT WINDOW ======================
class JarvisUltraGUI:
    def __init__(self, root, username):
        self.root = root
        self.root.title(f"Jarvis Ultra 🤖 | User: {username}")
        self.root.geometry("950x720")

        init_db()

        self.current_user = username.lower()
        self.memory = load_memory(self.current_user)

        # Dark theme default
        self.set_dark_theme()
        self.root.configure(bg=self.bg)

        # Chat area
        self.chat_area = scrolledtext.ScrolledText(
            root, wrap=tk.WORD, font=("Consolas", 12),
            bg=self.text_bg, fg=self.text_fg, insertbackground=self.text_fg
        )
        self.chat_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.chat_area.config(state=tk.DISABLED)

        # Search panel
        search_frame = tk.Frame(root, bg=self.bg)
        search_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(search_frame, text="Search:", bg=self.bg, fg=self.text_fg).pack(side=tk.LEFT)
        self.search_entry = tk.Entry(search_frame, bg=self.text_bg, fg=self.text_fg, insertbackground=self.text_fg)
        self.search_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.sender_var = tk.StringVar(value="all")
        sender_menu = tk.OptionMenu(search_frame, self.sender_var, "all", "user", "bot")
        sender_menu.config(bg=self.btn_bg, fg=self.btn_fg)
        sender_menu.pack(side=tk.LEFT, padx=5)

        tk.Button(search_frame, text="Go 🔍", bg=self.btn_bg, fg=self.btn_fg, command=self.search_db).pack(side=tk.LEFT, padx=5)
        tk.Button(search_frame, text="Refresh ♻️", bg=self.btn_bg, fg=self.btn_fg, command=self.refresh_chat).pack(side=tk.LEFT, padx=5)

        # Input
        self.user_input = tk.Entry(
            root, font=("Consolas", 12),
            bg=self.text_bg, fg=self.text_fg, insertbackground=self.text_fg
        )
        self.user_input.pack(padx=10, pady=5, fill=tk.X)
        self.user_input.bind("<Return>", self.send_message)

        # Buttons
        btn_frame = tk.Frame(root, bg=self.bg)
        btn_frame.pack(pady=5)

        tk.Button(btn_frame, text="Send 📩", bg=self.btn_bg, fg=self.btn_fg, command=self.send_message).grid(row=0, column=0, padx=5)
        tk.Button(btn_frame, text="Voice 🎙️", bg=self.btn_bg, fg=self.btn_fg, command=self.voice_message).grid(row=0, column=1, padx=5)

        self.always_listen = False
        self.last_voice_time = 0.0
        self.always_btn = tk.Button(btn_frame, text="Always OFF 🎧", bg=self.btn_bg, fg=self.btn_fg, command=self.toggle_always_listen)
        self.always_btn.grid(row=0, column=2, padx=5)

        self.wake_mode = False
        self.wake_btn = tk.Button(btn_frame, text="Wake OFF 🔴", bg=self.btn_bg, fg=self.btn_fg, command=self.toggle_wake)
        self.wake_btn.grid(row=0, column=3, padx=5)

        tk.Button(btn_frame, text="Export 📤", bg=self.btn_bg, fg=self.btn_fg, command=self.export_menu).grid(row=0, column=4, padx=5)
        tk.Button(btn_frame, text="Analytics 📊", bg=self.btn_bg, fg=self.btn_fg, command=self.show_analytics).grid(row=0, column=5, padx=5)
        tk.Button(btn_frame, text="Theme 🌗", bg=self.btn_bg, fg=self.btn_fg, command=self.toggle_theme).grid(row=0, column=6, padx=5)
        tk.Button(btn_frame, text="Exit ❌", bg=self.btn_bg, fg=self.btn_fg, command=self.exit_app).grid(row=0, column=7, padx=5)

        self.add_bot(f"Jarvis Ultra online 😄 | Welcome {username} | type /help")
        self.refresh_chat()

    # ---------- Themes ----------
    def set_dark_theme(self):
        self.bg = "#121212"
        self.text_bg = "#1E1E1E"
        self.text_fg = "#FFFFFF"
        self.btn_bg = "#2D2D2D"
        self.btn_fg = "#FFFFFF"

    def set_light_theme(self):
        self.bg = "#F5F5F5"
        self.text_bg = "#FFFFFF"
        self.text_fg = "#000000"
        self.btn_bg = "#DDDDDD"
        self.btn_fg = "#000000"

    def apply_theme(self):
        self.root.configure(bg=self.bg)
        self.chat_area.config(bg=self.text_bg, fg=self.text_fg, insertbackground=self.text_fg)
        self.user_input.config(bg=self.text_bg, fg=self.text_fg, insertbackground=self.text_fg)

    def toggle_theme(self):
        if self.bg == "#121212":
            self.set_light_theme()
        else:
            self.set_dark_theme()
        self.apply_theme()
        self.add_bot("🌗 Theme switched!")

    # ---------- UI Helpers ----------
    def add_user(self, msg):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"\n🧑 [{self.current_user}] {msg}\n")
        self.chat_area.config(state=tk.DISABLED)
        self.chat_area.yview(tk.END)

    def add_bot(self, msg):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"\n🤖 Bot: {msg}\n")
        self.chat_area.config(state=tk.DISABLED)
        self.chat_area.yview(tk.END)

    # ---------- Core Send ----------
    def send_message(self, event=None):
        msg = self.user_input.get().strip()
        if not msg:
            return

        self.user_input.delete(0, tk.END)
        self.add_user(msg)
        save_chat_db(self.current_user, "user", msg)

        if msg.lower() == "/exit":
            self.exit_app()
            return

        if msg.lower() == "/export":
            self.export_menu()
            return

        # Memory history
        self.memory["chat_history"].append(msg)
        save_memory(self.current_user, self.memory)

        # Plugins first
        plugin_ans = run_plugin(msg)
        if plugin_ans:
            self.add_bot(plugin_ans)
            save_chat_db(self.current_user, "bot", plugin_ans)
            speak(plugin_ans)
            return

        # Local reply
        local = local_reply(msg, self.memory, self.current_user)
        if local:
            self.add_bot(local)
            save_chat_db(self.current_user, "bot", local)
            speak(local)
            save_memory(self.current_user, self.memory)
            return

        threading.Thread(target=self.ai_thread, args=(msg,), daemon=True).start()

    def ai_thread(self, msg):
        try:
            reply = gemini_reply(msg, self.memory)
        except Exception as e:
            reply = f"⚠️ Gemini error: {e}"

        if self.memory.get("likes") and "like" not in msg.lower():
            reply += f"\n\n(🧠 I remember you like: {self.memory['likes'][-1]})"

        self.add_bot(reply)
        save_chat_db(self.current_user, "bot", reply)
        speak(reply)

    # ---------- Voice ----------
    def voice_message(self):
        self.add_bot("🎙️ Listening...")
        threading.Thread(target=self.voice_thread, daemon=True).start()

    def voice_thread(self):
        text = listen_voice_once()
        if not text.strip():
            self.add_bot("⚠️ Could not hear. Try again.")
            return

        if self.wake_mode and not text.lower().startswith(WAKE_WORD):
            self.add_bot(f"🛑 Wake ON: start with '{WAKE_WORD}'")
            return

        if self.wake_mode:
            text = text[len(WAKE_WORD):].strip()

        self.user_input.insert(0, text)
        self.send_message()

    def toggle_always_listen(self):
        self.always_listen = not self.always_listen
        self.always_btn.config(text=("Always ON 🎧" if self.always_listen else "Always OFF 🎧"))

        if self.always_listen:
            self.add_bot("🎧 Always listening started...")
            threading.Thread(target=self.always_loop, daemon=True).start()
        else:
            self.add_bot("🛑 Always listening stopped.")

    def always_loop(self):
        while self.always_listen:
            text = listen_voice_once(timeout=3, phrase_time_limit=5)
            if not text.strip():
                continue

            now = time.time()
            if now - self.last_voice_time < MIN_SECONDS_BETWEEN_MESSAGES:
                continue
            self.last_voice_time = now

            if self.wake_mode:
                if not text.lower().startswith(WAKE_WORD):
                    continue
                text = text[len(WAKE_WORD):].strip()

            self.user_input.delete(0, tk.END)
            self.user_input.insert(0, text)
            self.send_message()

    def toggle_wake(self):
        self.wake_mode = not self.wake_mode
        self.wake_btn.config(text=("Wake ON 🟢" if self.wake_mode else "Wake OFF 🔴"))
        self.add_bot(f"Wake word {'enabled' if self.wake_mode else 'disabled'}.")

    # ---------- Search / Refresh ----------
    def refresh_chat(self):
        rows = fetch_chats(user=self.current_user, sender="all", keyword=None)
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.delete(1.0, tk.END)
        self.chat_area.config(state=tk.DISABLED)

        self.add_bot(f"Chat loaded for user: {self.current_user}")

        for ts, user, sender, msg in rows[-180:]:
            if sender == "user":
                self.chat_area.config(state=tk.NORMAL)
                self.chat_area.insert(tk.END, f"\n🧑 [{user}] {msg}\n")
                self.chat_area.config(state=tk.DISABLED)
            else:
                self.chat_area.config(state=tk.NORMAL)
                self.chat_area.insert(tk.END, f"\n🤖 Bot: {msg}\n")
                self.chat_area.config(state=tk.DISABLED)

        self.chat_area.yview(tk.END)

    def search_db(self):
        keyword = self.search_entry.get().strip()
        sender = self.sender_var.get()

        rows = fetch_chats(user=self.current_user, sender=sender, keyword=keyword)

        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.delete(1.0, tk.END)
        self.chat_area.config(state=tk.DISABLED)

        self.add_bot(f"🔍 Search: '{keyword}' | sender={sender} | user={self.current_user}")

        for ts, user, sender, msg in rows[-200:]:
            if sender == "user":
                self.chat_area.config(state=tk.NORMAL)
                self.chat_area.insert(tk.END, f"\n🧑 [{user}] {msg}\n")
                self.chat_area.config(state=tk.DISABLED)
            else:
                self.chat_area.config(state=tk.NORMAL)
                self.chat_area.insert(tk.END, f"\n🤖 Bot: {msg}\n")
                self.chat_area.config(state=tk.DISABLED)

        self.chat_area.yview(tk.END)

    # ---------- Export ----------
    def export_menu(self):
        rows = fetch_chats(user=self.current_user, sender="all", keyword=None)
        if not rows:
            messagebox.showwarning("No Data", "No chats to export.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Export Chat",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("TXT", "*.txt"), ("CSV", "*.csv")]
        )
        if not filepath:
            return

        try:
            if filepath.endswith(".pdf"):
                export_pdf(filepath, rows)
            elif filepath.endswith(".txt"):
                export_txt(filepath, rows)
            elif filepath.endswith(".csv"):
                export_csv(filepath, rows)
            else:
                export_txt(filepath, rows)

            messagebox.showinfo("Export Success", f"Exported to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Failed", str(e))

    # ---------- Analytics ----------
    def show_analytics(self):
        rows = fetch_chats(user=self.current_user, sender="all", keyword=None)

        total = len(rows)
        user_msgs = len([r for r in rows if r[2] == "user"])
        bot_msgs = len([r for r in rows if r[2] == "bot"])

        words = {}
        for _, _, sender, msg in rows:
            if sender == "user":
                for w in msg.lower().split():
                    w = "".join([c for c in w if c.isalnum()])
                    if len(w) >= 3:
                        words[w] = words.get(w, 0) + 1

        top_words = sorted(words.items(), key=lambda x: x[1], reverse=True)[:10]
        top_words_str = "\n".join([f"{w} -> {c}" for w, c in top_words]) if top_words else "No words found."

        report = f"""📊 Analytics Report
User: {self.current_user}

Total messages: {total}
User messages: {user_msgs}
Bot messages: {bot_msgs}

Top words (user):
{top_words_str}
"""
        messagebox.showinfo("Analytics", report)

    def exit_app(self):
        self.always_listen = False
        self.root.destroy()


# ====================== LOGIN WINDOW ======================
class LoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Jarvis Login 🔐")
        self.root.geometry("400x250")
        self.root.configure(bg="#121212")

        tk.Label(root, text="Jarvis Ultra Login", font=("Consolas", 18, "bold"),
                 bg="#121212", fg="white").pack(pady=15)

        tk.Label(root, text="Enter Username:", font=("Consolas", 12),
                 bg="#121212", fg="white").pack(pady=5)

        self.username_entry = tk.Entry(root, font=("Consolas", 12), width=25)
        self.username_entry.pack(pady=5)
        self.username_entry.focus()

        tk.Button(root, text="Login ✅", font=("Consolas", 12),
                  command=self.login).pack(pady=15)

        tk.Button(root, text="Exit ❌", font=("Consolas", 12),
                  command=root.destroy).pack()

    def login(self):
        username = self.username_entry.get().strip()
        if not username:
            messagebox.showwarning("Error", "Please enter a username!")
            return

        # Close login window
        self.root.destroy()

        # Open chatbot window
        main_root = tk.Tk()
        JarvisUltraGUI(main_root, username)
        main_root.mainloop()


# ------------------ Run App ------------------
if __name__ == "__main__":
    if "PASTE_YOUR_GEMINI_API_KEY_HERE" in GEMINI_API_KEY:
        print("❌ Paste your Gemini API key first in the code!")
    else:
        root = tk.Tk()
        LoginWindow(root)
        root.mainloop()
