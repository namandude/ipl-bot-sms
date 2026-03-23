import re
import time
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from curl_cffi import requests as cf_requests

# ── Email credentials ──────────────────────────────────────────────────────────
GMAIL_USER     = "iplnotify18@gmail.com"
GMAIL_PASSWORD = "amts wjks eica qypw"   # app password
ALERT_EMAIL    = "iplnotify18@gmail.com"  # your own fallback alert

# ── Google Apps Script (fill after deploying) ──────────────────────────────────
# Get this URL after deploying google_apps_script.js as a Web App
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzf3je-VblPqQi-FfSQ-mNNtALrqo1uLCkHXlWsbD97tBHs_eHX5JUwiRLuQW95VYNcIg/exec"
APPS_SCRIPT_SECRET = "ipl2026secret"

FREE_ALERT_LIMIT = 2   # free-tier users get this many alerts

# ── Config ─────────────────────────────────────────────────────────────────────
POLL_SECONDS   = 20
RCB_MAIN_URL   = "https://www.royalchallengers.com/"
RCB_NEWS_URL   = "https://www.royalchallengers.com/rcb-cricket-news"
RCB_SHOP_URL   = "https://shop.royalchallengers.com/"
RCB_TICKET_URL = "https://shop.royalchallengers.com/ticket"
TEST_URL2      = "https://namandude.github.io/rcb-demo/"    # demo page
BMS_URL        = "https://in.bookmyshow.com/sports/tata-ipl-2026/ET00491491"


def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch(url) -> str | None:
    try:
        headers = {"Referer": "https://www.royalchallengers.com/"}
        if "bookmyshow" in url:
            headers = {
                "Referer": "https://www.google.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9",
            }
        r = cf_requests.get(url, impersonate="chrome110", timeout=20, headers=headers)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[{ts()}] ERROR fetching {url} — {e}")
        return None


# ── Subscriber management ───────────────────────────────────────────────────────

def get_subscribers() -> list[dict]:
    """Fetch active subscribers from Google Sheets via Apps Script."""
    if APPS_SCRIPT_URL == "YOUR_APPS_SCRIPT_URL":
        # Not configured yet — only alert yourself
        return [{"email": ALERT_EMAIL, "name": "Naman", "plan": "pro", "alerts_sent": 0}]
    try:
        r = cf_requests.get(
            APPS_SCRIPT_URL,
            params={"action": "list", "secret": APPS_SCRIPT_SECRET},
            impersonate="chrome110", timeout=15
        )
        data = r.json()
        if data.get("status") == "ok":
            return data.get("subscribers", [])
    except Exception as e:
        print(f"[{ts()}] ERROR fetching subscribers — {e}")
    return [{"email": ALERT_EMAIL, "name": "Naman", "plan": "pro", "alerts_sent": 0}]


def increment_alert_count_remote(email: str):
    """Tell Apps Script to increment alert count for this email."""
    if APPS_SCRIPT_URL == "YOUR_APPS_SCRIPT_URL":
        return
    try:
        cf_requests.get(
            APPS_SCRIPT_URL,
            params={"action": "increment", "secret": APPS_SCRIPT_SECRET, "email": email},
            impersonate="chrome110", timeout=10
        )
    except Exception as e:
        print(f"[{ts()}] ERROR incrementing count for {email} — {e}")


# ── Email sender ────────────────────────────────────────────────────────────────

def send_email_to(to_email: str, subject: str, body: str):
    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_USER
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(GMAIL_USER, GMAIL_PASSWORD)
            smtp.sendmail(GMAIL_USER, to_email, msg.as_string())

        print(f"[{ts()}] *** EMAIL SENT → {to_email} *** {subject}")
    except Exception as e:
        print(f"[{ts()}] *** EMAIL FAILED → {to_email} *** {e}")


def send_email(subject: str, body: str):
    """Send to your own alert email (for internal bot alerts)."""
    send_email_to(ALERT_EMAIL, subject, body)


def broadcast_alert(subject: str, body: str):
    """
    Send alert to all eligible subscribers.
    Free users: up to FREE_ALERT_LIMIT alerts.
    Pro users: unlimited.
    """
    subscribers = get_subscribers()
    sent_count = 0
    for sub in subscribers:
        email       = sub.get("email", "")
        plan        = sub.get("plan", "free")
        alerts_sent = int(sub.get("alerts_sent", 0))
        name        = sub.get("name", "there")

        if not email:
            continue

        # Free tier limit check
        if plan == "free" and alerts_sent >= FREE_ALERT_LIMIT:
            # Send upgrade nudge once (when they hit the limit exactly)
            if alerts_sent == FREE_ALERT_LIMIT:
                upgrade_body = (
                    f"Hi {name},\n\n"
                    "RCB tickets just went LIVE and we tried to alert you, "
                    "but you've used your 2 free alerts.\n\n"
                    "Upgrade to Pro for just ₹1 to get unlimited alerts for all of IPL 2026:\n"
                    "https://iplnotifier.github.io\n\n"
                    "— IPLNotifier"
                )
                send_email_to(email, "Upgrade to Pro — You Missed This Alert", upgrade_body)
                increment_alert_count_remote(email)
            continue

        # Personalise the body
        personalised = f"Hi {name},\n\n" + body
        send_email_to(email, subject, personalised)
        increment_alert_count_remote(email)
        sent_count += 1

    print(f"[{ts()}] Broadcast sent to {sent_count}/{len(subscribers)} subscribers")


# ── Page analysis ───────────────────────────────────────────────────────────────

def get_page_hash(html: str) -> str:
    return hashlib.md5(html.encode()).hexdigest()


def get_news_hash(html: str) -> str:
    """Hash only article links — fires when new article posted."""
    links = re.findall(r'href="(/rcb-cricket-news/news/[^"]+)"', html)
    unique = sorted(set(links))
    return hashlib.md5(" ".join(unique).encode()).hexdigest(), unique


def has_ticket_button(html: str) -> bool:
    spans = re.findall(r'<span class="buy-tck-spn[^"]*">([^<]+)</span>', html)
    return any("TICKET" in s.upper() for s in spans)


def get_buy_buttons(html: str) -> list:
    return re.findall(r'<span class="buy-tck-spn[^"]*">([^<]+)</span>', html)


def queue_fair_active(html: str) -> bool:
    commented = len(re.findall(r'<!--.*?queue-fair-adapter\.js.*?-->', html, re.DOTALL))
    total     = html.count("queue-fair-adapter.js")
    return total > commented


def bms_rcb_bookable(html: str) -> bool:
    """Check if any RCB match on BMS changed from Coming Soon to bookable."""
    # Find all RCB events and their CTA text
    matches = re.findall(
        r'"eventName":"([^"]*Royal Challengers[^"]*)".*?"cta":\{"text":"([^"]+)"',
        html
    )
    for name, cta in matches:
        if cta.lower() not in ("coming soon", "sold out"):
            return True, name, cta
    return False, "", ""


def extract_news_headline(html: str) -> str:
    match = re.search(r'<title>([^<]+)</title>', html)
    return match.group(1).strip() if match else ""


def describe_change(old_html: str, new_html: str) -> str:
    changes = []

    old_buttons = get_buy_buttons(old_html)
    new_buttons = get_buy_buttons(new_html)
    if old_buttons != new_buttons:
        changes.append(f"Buy button changed: {old_buttons} → {new_buttons}")

    old_title = extract_news_headline(old_html)
    new_title = extract_news_headline(new_html)
    if old_title != new_title:
        changes.append(f"Page title changed: {old_title} → {new_title}")

    old_links = set(re.findall(r'href="([^"]+)"', old_html))
    new_links = set(re.findall(r'href="([^"]+)"', new_html))
    added   = new_links - old_links
    removed = old_links - new_links
    if added:
        changes.append(f"New links added: {list(added)[:5]}")
    if removed:
        changes.append(f"Links removed: {list(removed)[:5]}")

    if not changes:
        changes.append("Something on the page changed (could be banner, image, news, score update etc.)")

    return "\n".join(changes)


# ── Main loop ───────────────────────────────────────────────────────────────────

def run():
    print(f"[{ts()}] Bot started | polling every {POLL_SECONDS}s")
    print(f"[{ts()}] Watching: royalchallengers.com + rcb-cricket-news + shop.royalchallengers.com + shop/ticket + BookMyShow")
    print(f"[{ts()}] Alerts → all IPLNotifier subscribers")
    print("-" * 60)

    # Initial snapshots
    print(f"[{ts()}] Taking initial snapshots...")
    main_html = ticket_html = None
    while main_html is None:
        main_html = fetch(RCB_MAIN_URL)
        if main_html is None: time.sleep(10)
    news_html = None
    while news_html is None:
        news_html = fetch(RCB_NEWS_URL)
        if news_html is None: time.sleep(10)
    shop_html = None
    while shop_html is None:
        shop_html = fetch(RCB_SHOP_URL)
        if shop_html is None: time.sleep(10)
    while ticket_html is None:
        ticket_html = fetch(RCB_TICKET_URL)
        if ticket_html is None: time.sleep(10)

    test2_html = fetch(TEST_URL2) or ""
    last_test2_hash = get_page_hash(test2_html)

    bms_html = fetch(BMS_URL) or ""
    last_bms_hash = get_page_hash(bms_html)

    last_main_hash   = get_page_hash(main_html)
    last_news_hash, last_news_links = get_news_hash(news_html)
    last_shop_hash   = get_page_hash(shop_html)
    last_ticket_hash = get_page_hash(ticket_html)
    last_main_html   = main_html
    last_shop_html   = shop_html
    last_ticket_html = ticket_html

    print(f"[{ts()}] Snapshots done. Watching for changes...\n")

    sms_sent_ticket  = False
    last_heartbeat   = time.time()
    HEARTBEAT_EVERY  = 600   # heartbeat email every 10 minutes


    while True:
        time.sleep(POLL_SECONDS)

        # ── Heartbeat: nothing changed email every 10 mins ───────────
        if time.time() - last_heartbeat >= HEARTBEAT_EVERY:
            send_email(
                subject="Nothing Nothing — Bot Still Running",
                body=(
                    "No changes detected on RCB sites.\n"
                    "Bot is running and watching every 20 seconds.\n\n"
                    f"Watching:\n"
                    f"  royalchallengers.com\n"
                    f"  shop.royalchallengers.com\n"
                    f"  shop.royalchallengers.com/ticket\n\n"
                    f"Time: {ts()}"
                )
            )
            last_heartbeat = time.time()

        # ── Check main RCB page ──────────────────────────────────────
        new_main = fetch(RCB_MAIN_URL)
        if new_main:
            new_hash = get_page_hash(new_main)

            if new_hash != last_main_hash:
                change_desc = describe_change(last_main_html, new_main)

                # URGENT: ticket button appeared
                if has_ticket_button(new_main) and not sms_sent_ticket:
                    print(f"[{ts()}] *** TICKET BUTTON LIVE! ***")
                    broadcast_alert(
                        subject="TICKET TICKET TICKET — RCB TICKETS LIVE BUY NOW!",
                        body=(
                            "RCB TICKETS ARE LIVE!\n\n"
                            "Go to: https://shop.royalchallengers.com/ticket\n\n"
                            f"Change detected:\n{change_desc}\n\n"
                            f"Time: {ts()}"
                        )
                    )
                    sms_sent_ticket = True
                else:
                    # Normal change — only alert yourself, not subscribers
                    print(f"[{ts()}] [MAIN] Page changed!")
                    send_email(
                        subject="CHANGED: RCB Main Site Updated — Check Now",
                        body=(
                            "Something changed on royalchallengers.com\n\n"
                            f"What changed:\n{change_desc}\n\n"
                            f"Check: https://www.royalchallengers.com\n\n"
                            f"Time: {ts()}"
                        )
                    )

                last_main_hash = new_hash
                last_main_html = new_main
            else:
                print(f"[{ts()}] [MAIN]   No change")


        # ── TEST 2: Our demo page — same detection as real RCB site ────
        new_test2 = fetch(TEST_URL2)
        if new_test2:
            spans = re.findall(r'<span class="buy-tck-spn[^"]*">([^<]+)</span>', new_test2)
            print(f"[{ts()}] [DEMO]  Button: {spans}")
            new_hash = get_page_hash(new_test2)
            if new_hash != last_test2_hash:
                if any("TICKET" in s.upper() for s in spans):
                    print(f"[{ts()}] [DEMO]  *** BUY TICKETS DETECTED! ***")
                    broadcast_alert(
                        subject="TICKET TICKET TICKET — Demo Tickets Live! (Bot Confirmed Working)",
                        body=(
                            f"Button changed to: {spans}\n\n"
                            "This is EXACTLY how it will work on real RCB site!\n\n"
                            f"Time: {ts()}"
                        )
                    )
                else:
                    send_email(
                        subject="DEMO PAGE CHANGED — Something Updated",
                        body=f"Button now shows: {spans}\n\nTime: {ts()}"
                    )
                last_test2_hash = new_hash
                test2_html = new_test2
            else:
                print(f"[{ts()}] [DEMO]  No change")

        # ── Check news page ──────────────────────────────────────────
        new_news = fetch(RCB_NEWS_URL)
        if new_news:
            new_hash, new_links = get_news_hash(new_news)
            if new_hash != last_news_hash:
                added = [l for l in new_links if l not in last_news_links]
                print(f"[{ts()}] [NEWS] New articles: {added}")
                send_email(   # only to yourself — news is not a ticket alert
                    subject="CHANGED: RCB New Article Posted",
                    body=(
                        "New article(s) posted on RCB News!\n\n"
                        + "\n".join(f"https://www.royalchallengers.com{l}" for l in added)
                        + f"\n\nTime: {ts()}"
                    )
                )
                last_news_hash  = new_hash
                last_news_links = new_links
            else:
                print(f"[{ts()}] [NEWS]   No change")

        # ── Check shop page ──────────────────────────────────────────
        new_shop = fetch(RCB_SHOP_URL)
        if new_shop:
            new_hash = get_page_hash(new_shop)
            if new_hash != last_shop_hash:
                change_desc = describe_change(last_shop_html, new_shop)
                print(f"[{ts()}] [SHOP] Page changed!")
                send_email(   # only to yourself — shop change might not be tickets
                    subject="CHANGED: RCB Shop Updated — Check Now",
                    body=(
                        "Something changed on shop.royalchallengers.com\n\n"
                        f"What changed:\n{change_desc}\n\n"
                        f"Check: https://shop.royalchallengers.com\n\n"
                        f"Time: {ts()}"
                    )
                )
                last_shop_hash = new_hash
                last_shop_html = new_shop
            else:
                print(f"[{ts()}] [SHOP]   No change")

        # ── Check ticket page ────────────────────────────────────────
        new_ticket = fetch(RCB_TICKET_URL)
        if new_ticket:
            new_hash = get_page_hash(new_ticket)

            if new_hash != last_ticket_hash:
                # URGENT: queue activated = tickets live
                if queue_fair_active(new_ticket) and not sms_sent_ticket:
                    print(f"[{ts()}] *** QUEUE ACTIVATED — TICKETS LIVE! ***")
                    broadcast_alert(
                        subject="TICKET TICKET TICKET — RCB Queue is Open BUY NOW!",
                        body=(
                            "RCB TICKET QUEUE IS OPEN!\n\n"
                            "Go NOW: https://shop.royalchallengers.com/ticket\n\n"
                            f"Time: {ts()}"
                        )
                    )
                    sms_sent_ticket = True
                else:
                    print(f"[{ts()}] [TICKET] Page changed!")
                    send_email(
                        subject="CHANGED: RCB Ticket Page Updated — Check Now",
                        body=(
                            "The RCB ticket page changed:\n"
                            "https://shop.royalchallengers.com/ticket\n\n"
                            f"Time: {ts()}"
                        )
                    )

                last_ticket_hash = new_hash
                last_ticket_html = new_ticket
            else:
                print(f"[{ts()}] [TICKET] No change")

        # ── Check BookMyShow ─────────────────────────────────────────
        new_bms = fetch(BMS_URL)
        if new_bms:
            new_hash = get_page_hash(new_bms)
            if new_hash != last_bms_hash:
                bookable, match_name, cta_text = bms_rcb_bookable(new_bms)
                if bookable and not sms_sent_ticket:
                    print(f"[{ts()}] *** BMS RCB TICKETS LIVE! ***")
                    broadcast_alert(
                        subject="TICKET TICKET TICKET — RCB Tickets on BookMyShow NOW!",
                        body=(
                            f"RCB TICKETS ARE LIVE ON BOOKMYSHOW!\n\n"
                            f"Match: {match_name}\n"
                            f"Status: {cta_text}\n\n"
                            f"Book NOW: https://in.bookmyshow.com/sports/tata-ipl-2026/ET00491491\n\n"
                            f"Time: {ts()}"
                        )
                    )
                    sms_sent_ticket = True
                else:
                    print(f"[{ts()}] [BMS] Page changed — not bookable yet, skipping email")
                last_bms_hash = new_hash
            else:
                print(f"[{ts()}] [BMS]    No change")

        print()


if __name__ == "__main__":
    run()
