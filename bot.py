"""EKSU Course Compass Bot - Direct API version"""
import requests, time, json, os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

from courses_data import COURSES, FACULTIES, get_courses_by_faculty
from matcher import check_all_courses
from news_data import NEWS_CONTENT
from spelling_map import suggest_correction

MONETIZATION = {
    "unlimited_check_link": os.getenv("UNLIMITED_CHECK_LINK", "https://selar.co/YourUnlimitedCheck"),
    "unlimited_check_price": os.getenv("UNLIMITED_CHECK_PRICE", "N2,000/month"),
}

KNOWN_SUBJECTS = {s.lower().strip() for s in [
    "Accounting", "Agricultural Science", "Animal Husbandry", "Arabic", "Biology", "Book Keeping",
    "Building Technology", "Business Studies", "Catering Craft Practice", "Chemistry",
    "Christian Religious Studies", "Civic Education", "Commerce", "Computer Studies",
    "Data Processing", "Dyeing & Bleaching", "Economics", "Electrical Installation and Maintenance",
    "English Language", "Financial Accounting", "French", "Geography", "Government",
    "Hausa Language", "History", "Home Economics", "Hospitality", "Health Education",
    "Igbo Language", "Information and Communication Technology", "Insurance", "Islamic Religious Studies",
    "Literature", "Marketing", "Mathematics", "Music", "Office Practice", "Painting and Decoration",
    "Photography", "Physical Health Education", "Physics", "Technical Drawing", "Tourism", 
    "Wood Work Technology", "Yoruba"
]}

VALID_GRADES = ["A1", "B2", "B3", "C4", "C5", "C6"]

def api_call(method, payload):
    for _ in range(3):
        try:
            r = requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", json=payload, timeout=15)
            return r.json()
        except:
            time.sleep(1)
    return {"ok": False}

def send(chat_id, text, kb=None):
    p = {"chat_id": chat_id, "text": text}
    if kb: p["reply_markup"] = kb
    return api_call("sendMessage", p)

def edit(chat_id, msg_id, text, kb=None):
    p = {"chat_id": chat_id, "message_id": msg_id, "text": text}
    if kb: p["reply_markup"] = kb
    return api_call("editMessageText", p)

def answer_cb(cb_id):
    api_call("answerCallbackQuery", {"callback_query_id": cb_id})

MENU = {
    "inline_keyboard": [
        [{"text": "Check EKSU Course Requirement", "callback_data": "check"}],
        [{"text": "EKSU Department by Faculty", "callback_data": "faculties"}],
        [{"text": "Premium Plans", "callback_data": "premium"}],
        [{"text": "Latest Admission News", "callback_data": "news"}],
        [{"text": "Contact & Support", "callback_data": "contact"}],
    ]
}

user_data = {}

def handle_message(chat_id, text):
    if text == "/start":
        user_data.pop(chat_id, None)
        send(chat_id, "Welcome to EKSU Course Compass!\n\nI help prospective EKSU students discover which courses they qualify for based on your JAMB score, subject combination, and O'Level results.\n\nSelect an option below:", MENU)
        return

    ud = user_data.get(chat_id)
    if not ud:
        send(chat_id, "Send /start to begin.")
        return

    state = ud.get("state")

    if state == "score":
        if not text.strip().isdigit():
            send(chat_id, "Enter a valid number (0-400):")
            return
        s = int(text.strip())
        if s < 0 or s > 400:
            send(chat_id, "Score must be 0-400. Try again:")
            return
        ud["score"] = s
        ud["state"] = "jamb"
        send(chat_id, f"Score: {s}\n\nEnter your 3 JAMB subjects (English Language is automatic).\nSeparate with commas.\n\nExample: Physics, Chemistry, Biology")

    elif state == "jamb":
        subs = [x.strip().lower() for x in text.split(",") if x.strip()]
        if any(x in ("english", "english language") for x in subs):
            send(chat_id, "English Language is already counted! Enter only your other 3 subjects.\nExample: Physics, Chemistry, Biology")
            return
        if len(subs) < 3:
            send(chat_id, "You need 3 subjects. Example: Physics, Chemistry, Biology")
            return
        if len(subs) > 3:
            subs = subs[:3]
        bad = [s for s in subs if s not in KNOWN_SUBJECTS]
        if bad:
            msg = f"Unknown: {', '.join(bad)}\nCheck spelling."
            suggestions = [suggest_correction(s) for s in bad]
            valid_suggestions = [s for s in suggestions if s]
            if valid_suggestions:
                msg += "\nDo you mean: " + " and ".join(valid_suggestions) + "?"
            msg += "\n\nExample: Physics, Chemistry, Biology"
            send(chat_id, msg)
            return
        ud["jamb"] = ["English Language"] + [s.title() for s in subs]
        ud["state"] = "olevel"
        send(chat_id, "Now enter your 5 O'Level credits.\nFormat: Subject-Grade, separated by commas\n\nExample: English Language-A1, Mathematics-B2, Biology-C4, Chemistry-B3, Physics-A1\n\nGrades: A1 B2 B3 C4 C5 C6")

    elif state == "olevel":
        pairs = [p.strip() for p in text.split(",") if p.strip()]
        if len(pairs) < 5:
            send(chat_id, f"Only {len(pairs)} entries. Need 5. Try again.")
            return
        ol = {}
        errs = []
        for p in pairs:
            if "-" not in p:
                errs.append(f"'{p}' - use Subject-Grade format"); continue
            parts = p.split("-", 1)
            subj, grade = parts[0].strip().lower(), parts[1].strip().upper()
            if subj not in KNOWN_SUBJECTS:
                suggestion = suggest_correction(subj)
                err_msg = f"'{parts[0].strip()}' - unknown subject"
                if suggestion:
                    err_msg += f" (did you mean {suggestion}?)"
                errs.append(err_msg); continue
            if grade not in VALID_GRADES:
                errs.append(f"'{grade}' - invalid"); continue
            ol[subj] = grade
        if errs:
            send(chat_id, "Errors:\n" + "\n".join(errs[:5]) + "\n\nTry again:")
            return
        if len(ol) < 5:
            send(chat_id, f"Only {len(ol)} valid. Need 5. Try again.")
            return
        ud["olevel"] = ol
        ud["state"] = "sitting"
        kb = {"inline_keyboard": [[{"text": "1 Sitting", "callback_data": "sit1"}], [{"text": "2 Sittings", "callback_data": "sit2"}]]}
        send(chat_id, "How many sittings? (max 2)", kb)

PRIORITY_FACULTIES = ["College of Medicine", "Pharmacy", "Basic Medical Sciences", "Law"]


def group_by_faculty(courses, fac_order, priority=None):
    groups = {}
    for c in courses:
        groups.setdefault(c["faculty"], []).append(c)
    lines = []
    seen = set()
    for fac in (priority or []):
        if fac in groups:
            lines.append(f"● {fac}:")
            for c in groups[fac]:
                lines.append(f"  - {c['name']}, cut-off: {c['cut_off']}")
            seen.add(fac)
    for fac in fac_order:
        if fac in groups and fac not in seen:
            lines.append(f"● {fac}:")
            for c in groups[fac]:
                lines.append(f"  - {c['name']}, cut-off: {c['cut_off']}")
    return lines


def show_results(chat_id, msg_id, ud):
    s = ud["score"]
    j = ud["jamb"]
    ol = ud["olevel"]
    sit = ud["sittings"]
    r = check_all_courses(s, j, ol, sit)

    ol_str = ", ".join(f"{subj.title()}({grade})" for subj, grade in ol.items())
    parts = [f"YOUR RESULTS\nScore: {s} | JAMB: {', '.join(j)} | Sittings: {sit}\nO'Level: {ol_str}"]

    if r["qualified"]:
        sec = [f"YOU QUALIFY ({len(r['qualified'])}):"]
        sec.extend(group_by_faculty(r["qualified"], FACULTIES, PRIORITY_FACULTIES))
        parts.append("\n".join(sec))
    else:
        parts.append("No fully qualified courses.")

    if r["jamb_only"]:
        lines = [f"NEARLY QUALIFY- OLevel issue ({len(r['jamb_only'])}):"]
        groups = {}
        for item in r["jamb_only"]:
            groups.setdefault(item["course"]["faculty"], []).append(item)
        for fac in FACULTIES:
            if fac in groups:
                lines.append(f"● {fac}:")
                for item in groups[fac]:
                    lines.append(f"  - {item['course']['name']}, missing: {', '.join(item['missing_subjects'])}")
        parts.append("\n".join(lines))

    if r["score_low"]:
        lines = [f"SCORE LOW ({len(r['score_low'])}):"]
        groups = {}
        for c in r["score_low"]:
            groups.setdefault(c["faculty"], []).append(c)
        for fac in FACULTIES:
            if fac in groups:
                lines.append(f"● {fac}:")
                for c in groups[fac]:
                    lines.append(f"  - {c['name']}, needs: {c['cut_off']}")
        parts.append("\n".join(lines))

    parts.append(f"GET EXCLUSIVE HELP:\n- Check Unlimited Requirements - {MONETIZATION['unlimited_check_price']}")

    msg = "\n\n".join(parts)

    kb = {"inline_keyboard": [
        [{"text": "Check Again", "callback_data": "check"}],
        [{"text": "Unlimited Check", "url": MONETIZATION["unlimited_check_link"]}],
        [{"text": "Menu", "callback_data": "menu"}],
    ]}
    edit(chat_id, msg_id, msg, kb)

def show_faculty_courses(chat_id, msg_id, fac_idx, page=0):
    faculty_name = FACULTIES[fac_idx]
    courses = get_courses_by_faculty(faculty_name)
    if not courses:
        edit(chat_id, msg_id, f"No courses found for {faculty_name}.")
        return

    entries = []
    for i, c in enumerate(courses, 1):
        entries.append(f"{i}. {c['name']}\n   Duration: {c['duration']}\n   Description: {c['description']}")

    pages = []
    cur = []
    cur_len = len(f"{faculty_name.upper()} ({len(courses)} courses)\n\n")
    for e in entries:
        elen = len(e) + 2
        if cur_len + elen > 4000 and cur:
            pages.append(cur)
            cur = [e]
            cur_len = len(f"{faculty_name.upper()} ({len(courses)} courses)\n\n") + elen
        else:
            cur.append(e)
            cur_len += elen
    if cur:
        pages.append(cur)

    if page >= len(pages):
        page = 0

    header = f"{faculty_name.upper()} ({len(courses)} courses)"
    if len(pages) > 1:
        header += f" — Page {page+1}/{len(pages)}"
    msg = header + "\n\n" + "\n\n".join(pages[page])

    kb_rows = []
    nav = []
    if page > 0:
        nav.append({"text": "◀ Prev", "callback_data": f"fac_{fac_idx}_p{page-1}"})
    if page < len(pages) - 1:
        nav.append({"text": "Next ▶", "callback_data": f"fac_{fac_idx}_p{page+1}"})
    if nav:
        kb_rows.append(nav)
    kb_rows.append([{"text": "Back to Faculties", "callback_data": "faculties"}])
    kb_rows.append([{"text": "Menu", "callback_data": "menu"}])
    edit(chat_id, msg_id, msg, {"inline_keyboard": kb_rows})

def handle_callback(chat_id, msg_id, data, cb_id):
    answer_cb(cb_id)
    if data == "menu":
        user_data.pop(chat_id, None)
        edit(chat_id, msg_id, "Welcome back!", MENU)
    elif data == "check":
        user_data[chat_id] = {"state": "score"}
        edit(chat_id, msg_id, "Enter your JAMB Score (0-400):")
    elif data == "premium":
        t = (
            "PREMIUM PLAN\n\n"
            "Check Unlimited Requirements\n"
            f"- {MONETIZATION['unlimited_check_price']}\n"
            "- Check as many courses as you want\n"
            "- Compare different combinations\n\n"
            "Click below to subscribe:"
        )
        kb = {"inline_keyboard": [
            [{"text": "Check Unlimited Requirements", "url": MONETIZATION["unlimited_check_link"]}],
            [{"text": "Back", "callback_data": "menu"}]
        ]}
        edit(chat_id, msg_id, t, kb)
    elif data == "news":
        kb = {"inline_keyboard": [[{"text": "Back", "callback_data": "menu"}]]}
        edit(chat_id, msg_id, NEWS_CONTENT, kb)
    elif data == "contact":
        t = (
            "Visit the Admissions Office,\n"
            "Ekiti State University,\n"
            "Email: admissions.office@eksu.edu.ng"
        )
        kb = {"inline_keyboard": [[{"text": "Back", "callback_data": "menu"}]]}
        edit(chat_id, msg_id, t, kb)
    elif data == "faculties":
        kb_rows = []
        for i, fac in enumerate(FACULTIES):
            kb_rows.append([{"text": fac, "callback_data": f"fac_{i}"}])
        kb_rows.append([{"text": "Back", "callback_data": "menu"}])
        kb = {"inline_keyboard": kb_rows}
        edit(chat_id, msg_id, "SELECT A FACULTY", kb)
    elif data.startswith("fac_"):
        parts = data.split("_")
        idx = int(parts[1])
        page = int(parts[2][1:]) if len(parts) > 2 and parts[2].startswith("p") else 0
        show_faculty_courses(chat_id, msg_id, idx, page)
    elif data == "sit1":
        if chat_id in user_data:
            user_data[chat_id]["sittings"] = 1
            show_results(chat_id, msg_id, user_data[chat_id])
    elif data == "sit2":
        if chat_id in user_data:
            user_data[chat_id]["sittings"] = 2
            show_results(chat_id, msg_id, user_data[chat_id])

def main():
    if not TOKEN or TOKEN == "your_telegram_bot_token_here":
        print("ERROR: Missing BOT_TOKEN in .env"); return

    import threading, http.server

    port = int(os.getenv("PORT", 10000))

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(s):
            s.send_response(200)
            s.end_headers()
            s.wfile.write(b"ok")
        def log_message(s, *a): pass

    httpd = http.server.HTTPServer(("0.0.0.0", port), H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"Bot running on port {port}. Send /start to @EKSUCourseCompassBot", flush=True)

    offset = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35)
            data = r.json()
            if not data.get("ok"): continue

            for u in data.get("result", []):
                offset = u["update_id"] + 1

                if "callback_query" in u:
                    cb = u["callback_query"]
                    handle_callback(cb["message"]["chat"]["id"], cb["message"]["message_id"], cb["data"], cb["id"])
                elif "message" in u:
                    m = u["message"]
                    handle_message(m["chat"]["id"], m.get("text", ""))
        except requests.exceptions.Timeout:
            print(".", end="", flush=True)
        except Exception as e:
            print(f"\nE: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
