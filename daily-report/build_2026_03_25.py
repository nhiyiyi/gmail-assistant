#!/usr/bin/env python3
"""Build 2026-03-25 daily report CSV."""
import csv, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATE = "2026-03-25"
OUTPUT = os.path.join(os.path.dirname(__file__), "2026-03-25.csv")
COLS = [
    "source_id","date","time_gmt7","source","ticket_id","source_link",
    "screenshot_url","original_content","email","candidate_name","topic_raw",
    "stage","category","interview_position","interview_company","submission_id",
    "browser","os","device","assessment","confidence","assessment_notes",
    "human_verdict","human_notes","include_in_report","report_bucket",
    "approval_status","reviewed_by","reviewed_at"
]

def row(**kw):
    r = {c: "" for c in COLS}
    r["date"] = DATE
    r["include_in_report"] = "?"
    r["approval_status"] = "new"
    r.update(kw)
    return r

def excl(**kw):
    r = row(**kw)
    r["stage"] = "EXCLUDED"
    r["assessment"] = "N/A"
    r["confidence"] = "High"
    return r

rows = []

# ── GOOGLE SHEET ENTRIES ──────────────────────────────────────────────────────

rows.append(row(
    source_id="SHEET-BUG-260325-001", time_gmt7="04:50", source="Google Sheet",
    ticket_id="BUG-260325-001", source_link="https://mail.google.com/mail/u/0/#all/19d230350d4e245f",
    original_content="Platform froze during response analysis, glitched without next question, repeated questions. Multiple browsers/networks/incognito/mobile all failed. 30-min interview took 80+ minutes.",
    email="pgviceiro.digital@gmail.com", candidate_name="Patricia", topic_raw="Feature Not Working",
    stage="Stage 2", category="Redirected to the beginning",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Platform froze mid-analysis, repeated questions instead of advancing — routing loop, no user action causes this."
))
rows.append(row(
    source_id="SHEET-BUG-260325-002", time_gmt7="04:50", source="Google Sheet",
    ticket_id="BUG-260325-002", source_link="https://mail.google.com/mail/u/0/#all/19d22d51c9618f9c",
    original_content="AI interview failed with 'Internet Unstable' warning. Internet verified at 292 Mbps down / 374 Mbps up. Browser console showed server-side 429 Too Many Requests error.",
    email="cunananjohn2004@gmail.com", candidate_name="John", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Server returned 429 (rate limiting) — definitively platform-side; candidate 292/374 Mbps rules out network issues."
))
rows.append(row(
    source_id="SHEET-BUG-260325-003", time_gmt7="04:50", source="Google Sheet",
    ticket_id="BUG-260325-003", source_link="https://mail.google.com/mail/u/0/#all/19d22cefed7919a8",
    original_content="Unable to progress past first question in AI interview. Tried refreshing, different browser, and mobile — same result.",
    email="mariumkhan826@gmail.com", candidate_name="Marium", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Issue persists across browsers and devices — likely platform-side analysis failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-004", time_gmt7="06:52", source="Google Sheet",
    ticket_id="BUG-260325-004",
    original_content="Interview froze during response submission with no submit option available. Page stuck ~10 minutes.",
    email="buballodk@gmail.com", candidate_name="Chingthang", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Submit option disappeared and page froze — platform-side UI state failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-005", time_gmt7="06:53", source="Google Sheet",
    ticket_id="BUG-260325-005",
    original_content="Interview link not working and unable to access HR Executive interview.",
    email="bandanabarik100@gmail.com", candidate_name="Bandana", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Link not working for HR Executive interview — likely platform-side link or routing issue."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-006", time_gmt7="06:53", source="Google Sheet",
    ticket_id="BUG-260325-006", email="bandanabarik100@gmail.com", candidate_name="Bandana",
    original_content="Duplicate of BUG-260325-005.", category="Duplicate",
    assessment_notes="Same email and issue as BUG-260325-005."
))
rows.append(row(
    source_id="SHEET-BUG-260325-007", time_gmt7="06:53", source="Google Sheet",
    ticket_id="BUG-260325-007",
    original_content="Interview platform froze and became stuck at the 'Preparing your Interview' stage. Page loading but never progressed.",
    email="mayur23tiwari@gmail.com", candidate_name="Mayur", topic_raw="Feature Not Working",
    stage="Stage 1", category="Stuck at Preparing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Stuck at Preparing your Interview — platform-side initialization failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-008", time_gmt7="09:47", source="Google Sheet",
    ticket_id="BUG-260325-008",
    original_content="Scheduled video interview for 20-3-2026 did not occur. Multiple requests made but no response.",
    email="shruthibambila@gmail.com", candidate_name="Shruthi", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Scheduled interview did not start — platform-side scheduling or access failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-009", time_gmt7="09:47", source="Google Sheet",
    ticket_id="BUG-260325-009",
    original_content="Technical issue while attempting to complete an interview, unable to proceed.",
    email="jemimaloyd@gmail.com", candidate_name="Jemima", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Technical issue preventing interview completion — no specific error detail."
))
rows.append(row(
    source_id="SHEET-BUG-260325-010", time_gmt7="09:47", source="Google Sheet",
    ticket_id="BUG-260325-010",
    original_content="Platform shows continuous loading screen when attempting to start interview and does not proceed.",
    email="jpjitsingh@gmail.com", candidate_name="Jpjit", topic_raw="Feature Not Working",
    stage="Stage 1", category="Stuck at Preparing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Continuous loading at interview start — platform initialization loop."
))
rows.append(row(
    source_id="SHEET-BUG-260325-011", time_gmt7="09:47", source="Google Sheet",
    ticket_id="BUG-260325-011",
    original_content="Video froze during interview while attempting to complete it. Reconnection attempts failed.",
    email="goelakshita354@gmail.com", candidate_name="Akshita", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Video froze repeatedly mid-interview — platform-side video stream failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-012", time_gmt7="09:47", source="Google Sheet",
    ticket_id="BUG-260325-012",
    original_content="Timeout error on the Flowmingo platform while taking interview. Error occurred after timer expired.",
    email="bagchimouli75@gmail.com", candidate_name="Mouli", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Timeout error at timer expiry — platform-side session management failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-013", time_gmt7="09:47", source="Google Sheet",
    ticket_id="BUG-260325-013",
    original_content="Attempted to join interview but received error: 'Error: Unable to establish secure connection'.",
    email="amaechiemmanuel94@gmail.com", candidate_name="Onyekachi", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Explicit 'Unable to establish secure connection' error — platform-side SSL/connection failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-014", time_gmt7="12:41", source="Google Sheet",
    ticket_id="BUG-260325-014",
    original_content="In the middle of AI interview but response is not getting analysed, preventing answer submission.",
    email="rebeccajulia777@gmail.com", candidate_name="Rebecca", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Response not getting analysed mid-interview — analysis stuck indefinitely is always a platform bug."
))
rows.append(row(
    source_id="SHEET-BUG-260325-015", time_gmt7="12:41", source="Google Sheet",
    ticket_id="BUG-260325-015",
    original_content="Unable to complete AI interview after multiple attempts due to persistent technical difficulties.",
    email="ozululilian@gmail.com", candidate_name="Lilian", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Persistent failure across multiple attempts — consistent platform-side issue."
))
rows.append(row(
    source_id="SHEET-BUG-260325-016", time_gmt7="12:43", source="Google Sheet",
    ticket_id="BUG-260325-016",
    original_content="Attempting to submit response during AI interview but response is not being submitted. Error message shown.",
    email="karishmakalyani32@gmail.com", candidate_name="Karishma", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Response not submitting with visible error — platform-side submission failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-017", time_gmt7="12:43", source="Google Sheet",
    ticket_id="BUG-260325-017",
    original_content="System does not work and cannot proceed with the interview.",
    email="pabsuamon@gmail.com", candidate_name="Pablo", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Cannot proceed — no specific error detail."
))
rows.append(row(
    source_id="SHEET-BUG-260325-018", time_gmt7="12:43", source="Google Sheet",
    ticket_id="BUG-260325-018",
    original_content="20-minute interview was incomplete and unable to continue. Needs to resume or complete.",
    email="mailpastordave@gmail.com", candidate_name="Dave", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Interview stopped mid-way — no specific error provided."
))
rows.append(row(
    source_id="SHEET-BUG-260325-019", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-019",
    original_content="Site problem preventing access to or completion of AI interview.",
    email="nimosrmnt@gmail.com", candidate_name="Nimoel", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Site problem blocking interview access — no specific error."
))
rows.append(row(
    source_id="SHEET-BUG-260325-020", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-020",
    original_content="Unable to complete interview due to technical difficulties.",
    email="shezashamim@gmail.com", candidate_name="Sheza", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Technical difficulties during interview — no specific error."
))
rows.append(row(
    source_id="SHEET-BUG-260325-021", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-021",
    original_content="Technical issues preventing interview completion.",
    email="vaibhavikolhe0606@gmail.com", candidate_name="Vaibhavi", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Technical issues preventing completion — no specific error."
))
rows.append(row(
    source_id="SHEET-BUG-260325-022", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-022",
    original_content="Requesting assistance with Finance Accounting Internship interview.",
    email="ldan09655@gmail.com", candidate_name="Dan", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Requesting help — insufficient detail."
))
rows.append(row(
    source_id="SHEET-BUG-260325-023", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-023",
    original_content="Unable to access the AI interview for HR Executive role.",
    email="bhavnay828@gmail.com", candidate_name="Bhavna", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Cannot access HR interview — no specific error."
))
rows.append(row(
    source_id="SHEET-BUG-260325-024", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-024",
    original_content="Reporting an issue but details are unclear.",
    email="shruthibhardwaj25@gmail.com", candidate_name="Shruthi", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Borderline", confidence="Low",
    assessment_notes="Insufficient detail to classify confidently."
))
rows.append(row(
    source_id="SHEET-BUG-260325-025", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-025",
    original_content="Unable to attend and complete interview due to technical issues.",
    email="jemimajemin2015@gmail.com", candidate_name="Jemima", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Cannot complete interview — no specific error."
))
rows.append(row(
    source_id="SHEET-BUG-260325-026", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-026",
    original_content="Unable to start the interview.",
    email="jpjitsingh2020@gmail.com", candidate_name="Jpjit", topic_raw="Feature Not Working",
    stage="Stage 1", category="Stuck at Preparing",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Cannot start interview — no specific error."
))
rows.append(row(
    source_id="SHEET-BUG-260325-027", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-027",
    original_content="Unable to complete interview due to technical difficulties.",
    email="mayurisendar@gmail.com", candidate_name="Mayuri", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Cannot complete — insufficient detail."
))
rows.append(row(
    source_id="SHEET-BUG-260325-028", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-028",
    original_content="Error when connecting to AI interview.",
    email="onyekachiamaechi@gmail.com", candidate_name="Onyekachi", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Connection error at interview entry — no specific error message."
))
rows.append(row(
    source_id="SHEET-BUG-260325-029", time_gmt7="12:44", source="Google Sheet",
    ticket_id="BUG-260325-029",
    original_content="Unable to complete interview due to technical issues.",
    email="sivathaprakash@gmail.com", candidate_name="Sivatha", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Technical issues preventing completion — no specific error."
))
rows.append(row(
    source_id="SHEET-BUG-260325-030", time_gmt7="16:03", source="Google Sheet",
    ticket_id="BUG-260325-030",
    original_content="After submitting response to first question, no further prompts or updates appeared. Platform stopped progressing.",
    email="rohangowdaaa28@gmail.com", candidate_name="Rohan", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Platform stopped after first question — analysis indefinitely stuck."
))
rows.append(row(
    source_id="SHEET-BUG-260325-031", time_gmt7="16:03", source="Google Sheet",
    ticket_id="BUG-260325-031",
    original_content="Getting stuck at a specific page during AI interview. Screenshot provided.",
    email="sanyasethi22@gmail.com", candidate_name="Sanya", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Stuck at specific page — platform-side state freeze."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-032", time_gmt7="16:03", source="Google Sheet",
    ticket_id="BUG-260325-032", email="sanyasethi22@gmail.com", candidate_name="Sanya",
    original_content="Duplicate of BUG-260325-031.", category="Duplicate",
    assessment_notes="Same email and issue as BUG-260325-031."
))
rows.append(row(
    source_id="SHEET-BUG-260325-033", time_gmt7="16:05", source="Google Sheet",
    ticket_id="BUG-260325-033",
    original_content="Attempted AI interview three times but encountered errors each time. Screenshots provided.",
    email="sonamkaprele24@gmail.com", candidate_name="Sonam", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Three consecutive failures — persistent platform-side error."
))
rows.append(row(
    source_id="SHEET-BUG-260325-034", time_gmt7="16:05", source="Google Sheet",
    ticket_id="BUG-260325-034",
    original_content="AI interview was administered in German/Dutch language despite selecting English as preference.",
    email="osasekeleni@gmail.com", candidate_name="Ekeleni", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Wrong language delivered despite English selection — platform-side language routing bug."
))
rows.append(row(
    source_id="SHEET-BUG-260325-035", time_gmt7="16:05", source="Google Sheet",
    ticket_id="BUG-260325-035",
    original_content="Cannot submit answer despite having answered the question. Submit option not working.",
    email="rajkumarogirala1705@gmail.com", candidate_name="Rajkumar", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Submit not working after answering — platform-side response capture/submission failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-036", time_gmt7="16:05", source="Google Sheet",
    ticket_id="BUG-260325-036",
    original_content="Interview got stuck three times after answering one question during AI interview.",
    email="yashikachauhan635@gmail.com", candidate_name="Yashika", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Stuck three consecutive times — repeated platform analysis failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-037", time_gmt7="16:11", source="Google Sheet",
    ticket_id="BUG-260325-037",
    original_content="After a certain period during the interview, process becomes unresponsive and gets stuck.",
    email="ayushmishraofficial7@gmail.com", candidate_name="Ayush", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Process becomes unresponsive mid-interview — platform-side stability issue."
))
rows.append(row(
    source_id="SHEET-BUG-260325-038", time_gmt7="16:11", source="Google Sheet",
    ticket_id="BUG-260325-038",
    original_content="Chatbot responses not loading after being uploaded. All troubleshooting steps attempted.",
    email="vrosas1992@gmail.com", candidate_name="Victor", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Chatbot responses not loading — platform-side content delivery issue."
))
rows.append(row(
    source_id="SHEET-BUG-260325-039", time_gmt7="16:11", source="Google Sheet",
    ticket_id="BUG-260325-039",
    original_content="After answering a question, system stopped and did not proceed to next question.",
    email="mrjraeo@gmail.com", candidate_name="Marjorie", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="System stopped after analysis — analysis stuck indefinitely is always platform bug."
))
rows.append(row(
    source_id="SHEET-BUG-260325-040", time_gmt7="16:11", source="Google Sheet",
    ticket_id="BUG-260325-040",
    original_content="Audio recorder experienced consistent lags despite strong connection during AI interview.",
    email="angeldeelaw@gmail.com", candidate_name="Angel", topic_raw="Feature Not Working",
    stage="Stage 2", category="Camera / microphone not working",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Audio recorder lagging despite strong connection — platform-side audio processing issue."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-041", time_gmt7="16:11", source="Google Sheet",
    ticket_id="BUG-260325-041", email="bandanabarik100@gmail.com", candidate_name="Bandana",
    original_content="Duplicate of BUG-260325-005.", category="Duplicate",
    assessment_notes="Same email as BUG-260325-005."
))
rows.append(row(
    source_id="SHEET-BUG-260325-042", time_gmt7="18:45", source="Google Sheet",
    ticket_id="BUG-260325-042",
    original_content="Interview platform freezes at 'Just a moment...We're analyzing your responses'. Completed all troubleshooting.",
    email="jeremiahobua8@gmail.com", candidate_name="Jeremiah", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Explicitly stuck on 'analyzing your responses' — analysis indefinitely stuck is always platform bug."
))
rows.append(row(
    source_id="SHEET-BUG-260325-043", time_gmt7="18:45", source="Google Sheet",
    ticket_id="BUG-260325-043",
    original_content="After answering and submitting, platform shows no more questions. Assessment appears stuck.",
    email="anitha.kalimuthu1308@gmail.com", candidate_name="Anitha", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="No more questions shown — platform analysis never completed."
))
rows.append(row(
    source_id="SHEET-BUG-260325-044", time_gmt7="18:45", source="Google Sheet",
    ticket_id="BUG-260325-044",
    original_content="Facing challenges attempting AI-driven interview for HR Executive and unable to complete.",
    email="parul7711@gmail.com", candidate_name="Parul", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Unable to complete — insufficient detail."
))
rows.append(row(
    source_id="SHEET-BUG-260325-045", time_gmt7="18:46", source="Google Sheet",
    ticket_id="BUG-260325-045",
    original_content="Had to wait 30 minutes for first answer analysis, then another 30 minutes for the next during AI interview.",
    email="jewelkent1@gmail.com", candidate_name="Jewel", topic_raw="Performance Issue",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="30-minute wait per analysis — analysis stuck indefinitely, classic platform bug."
))
rows.append(row(
    source_id="SHEET-BUG-260325-046", time_gmt7="18:46", source="Google Sheet",
    ticket_id="BUG-260325-046",
    original_content="Retried test after troubleshooting advice but same issue persists after extensive troubleshooting.",
    email="ykvasuvardhan@gmail.com", candidate_name="Vardhan", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Issue persists after all troubleshooting — consistent platform failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-047", time_gmt7="18:46", source="Google Sheet",
    ticket_id="BUG-260325-047",
    original_content="Attempting AI-led interview for HR Executive but encountered persistent platform errors.",
    email="sinhaishika22@gmail.com", candidate_name="Ishika", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Persistent platform errors during interview."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-048", time_gmt7="18:46", source="Google Sheet",
    ticket_id="BUG-260325-048", email="blessingbabs68@gmail.com", candidate_name="Blessing",
    original_content="Follow-up on previously reported issue.", category="Duplicate",
    assessment_notes="Follow-up; Slack entry for same user retained."
))
rows.append(row(
    source_id="SHEET-BUG-260325-049", time_gmt7="18:46", source="Google Sheet",
    ticket_id="BUG-260325-049",
    original_content="Completed all troubleshooting — cache cleared, different browsers, incognito, mobile. Issue still not resolved.",
    email="ramyaiyengar1717@gmail.com", candidate_name="Ramya", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="All troubleshooting exhausted across browsers and devices — definitive platform failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-050", time_gmt7="18:46", source="Google Sheet",
    ticket_id="BUG-260325-050",
    original_content="Exhausted all troubleshooting including new device, different internet, various browsers. Still not working.",
    email="lebsblessing@gmail.com", candidate_name="Blessing", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Platform Bug", confidence="High",
    assessment_notes="All troubleshooting exhausted including new device and internet — definitive platform failure."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-051", time_gmt7="18:46", source="Google Sheet",
    ticket_id="BUG-260325-051", email="rebeccajulia777@gmail.com", candidate_name="Rebecca",
    original_content="Follow-up requesting new interview link after redo attempt failed.", category="Duplicate",
    assessment_notes="Follow-up of BUG-260325-014."
))
for n in range(52, 69):
    ns = str(n).zfill(3)
    nm = "Hiring Manager" if n == 53 else "Candidate"
    if n == 53:
        rows.append(row(
            source_id=f"SHEET-BUG-260325-{ns}", time_gmt7="18:46", source="Google Sheet",
            ticket_id=f"BUG-260325-{ns}",
            original_content="Interview auto-submitted without candidate being able to answer. Reported by hiring manager.",
            email="unknown@email.com", candidate_name="Hiring Manager", topic_raw="Feature Not Working",
            stage="Other (Company)", category="Other (Company)",
            assessment="Platform Bug", confidence="High",
            assessment_notes="Interview auto-submitting without candidate answering — platform-side submission logic failure."
        ))
    else:
        rows.append(excl(
            source_id=f"SHEET-BUG-260325-{ns}", time_gmt7="18:46", source="Google Sheet",
            ticket_id=f"BUG-260325-{ns}", email="unknown@email.com", candidate_name="Candidate",
            original_content="Generic technical issue, no email captured.", category="Insufficient Data",
            assessment_notes="No email — insufficient data to include."
        ))
rows.append(row(
    source_id="SHEET-BUG-260325-069", time_gmt7="21:31", source="Google Sheet",
    ticket_id="BUG-260325-069",
    original_content="AI interview platform hangs after each question and does not allow progression to next question.",
    email="bmoyer0257@outlook.com", candidate_name="Bobbi", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Platform hangs after every question — systematic analysis failure."
))
rows.append(row(
    source_id="SHEET-BUG-260325-070", time_gmt7="21:31", source="Google Sheet",
    ticket_id="BUG-260325-070",
    original_content="During AI interview, response analyzing time took longer than expected with no further progression.",
    email="aishani.ab83@gmail.com", candidate_name="Aishani", topic_raw="Performance",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Analysis took too long and never completed — indefinite analysis wait is platform bug."
))
rows.append(row(
    source_id="SHEET-BUG-260325-071", time_gmt7="21:31", source="Google Sheet",
    ticket_id="BUG-260325-071",
    original_content="Interview crashed after first question. Platform accepts response then crashes into a restart loop.",
    email="hassanasad559@gmail.com", candidate_name="Hassan", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Crash into restart loop after first question — platform-side crash/routing loop."
))
rows.append(row(
    source_id="SHEET-BUG-260325-072", time_gmt7="21:31", source="Google Sheet",
    ticket_id="BUG-260325-072",
    original_content="Interview keeps loading without progressing to next section. Page refresh does not resolve.",
    email="shadekomide@gmail.com", candidate_name="Olamide", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Loading without progression — analysis stuck, refresh does not help."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-073", time_gmt7="21:31", source="Google Sheet",
    ticket_id="BUG-260325-073", email="ykvasuvardhan@gmail.com", candidate_name="Vardhan",
    original_content="Duplicate of BUG-260325-046.", category="Duplicate",
    assessment_notes="Same email as BUG-260325-046."
))
rows.append(row(
    source_id="SHEET-BUG-260325-074", time_gmt7="21:31", source="Google Sheet",
    ticket_id="BUG-260325-074",
    original_content="After waiting ~5 minutes following each answer submission, platform does not progress to next question.",
    email="keshavachinneti@gmail.com", candidate_name="Keshava", topic_raw="Performance",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="5-minute wait per question with no progression — analysis stuck indefinitely is platform bug."
))
rows.append(row(
    source_id="SHEET-BUG-260325-075", time_gmt7="21:31", source="Google Sheet",
    ticket_id="BUG-260325-075",
    original_content="Facing issue submitting the interview and requesting to reschedule.",
    email="prateekpi28@gmail.com", candidate_name="Prateek", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck during",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Unable to submit — no specific error detail."
))
rows.append(row(
    source_id="SHEET-BUG-260325-076", time_gmt7="21:31", source="Google Sheet",
    ticket_id="BUG-260325-076",
    original_content="Interview not working, keeps loading despite multiple attempts and changing internet connections.",
    email="bavadharani3002@gmail.com", candidate_name="Bavadharani", topic_raw="Feature Not Working",
    stage="Stage 2", category="Stuck analyzing",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Keeps loading despite internet changes — platform-side issue."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-077", time_gmt7="21:32", source="Google Sheet",
    ticket_id="BUG-260325-077", email="shezashamim@gmail.com", candidate_name="Sheza",
    original_content="Duplicate of BUG-260325-020.", category="Duplicate",
    assessment_notes="Same email as BUG-260325-020."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-078", time_gmt7="21:32", source="Google Sheet",
    ticket_id="BUG-260325-078", email="vaibhavikolhe0606@gmail.com", candidate_name="Vaibhavi",
    original_content="Duplicate of BUG-260325-021.", category="Duplicate",
    assessment_notes="Same email as BUG-260325-021."
))
rows.append(excl(
    source_id="SHEET-BUG-260325-079", time_gmt7="21:32", source="Google Sheet",
    ticket_id="BUG-260325-079", email="ldan09655@gmail.com", candidate_name="Dan",
    original_content="Duplicate of BUG-260325-022.", category="Duplicate",
    assessment_notes="Same email as BUG-260325-022."
))

# ── SLACK ENTRIES ─────────────────────────────────────────────────────────────

def slack(ts, time, email, name, content, stage, category, assessment, confidence, notes,
          position="", company="", submission_id="", browser="", os_val="", device="", screenshot=""):
    return row(
        source_id=f"SLACK-{ts}", time_gmt7=time, source="Slack",
        email=email, candidate_name=name, original_content=content,
        stage=stage, category=category, assessment=assessment, confidence=confidence,
        assessment_notes=notes, interview_position=position, interview_company=company,
        submission_id=submission_id, browser=browser, os=os_val, device=device,
        screenshot_url=screenshot, topic_raw="Technical Issue"
    )

def slack_excl(ts, time, email, name, content, cat, notes, position="", company="", submission_id="",
               browser="", os_val="", device="", screenshot=""):
    return excl(
        source_id=f"SLACK-{ts}", time_gmt7=time, source="Slack",
        email=email, candidate_name=name, original_content=content,
        category=cat, assessment_notes=notes, interview_position=position, interview_company=company,
        submission_id=submission_id, browser=browser, os=os_val, device=device, screenshot_url=screenshot
    )

rows.append(slack("1774457404.447599","23:50","kwenad058@gmail.com","David Segage",
    "My voice sounded choppy when I tried to answer the question.",
    "Stage 2","Camera / microphone not working","Likely Platform Bug","Medium",
    "Choppy audio during answer — platform-side audio encoding/upload issue.",
    "Team Member Interview Set","ROCO MOA","f5c2404a-7ff3-4a9d-ac7c-51a4df314471",
    "Chrome 145.0","Android 10","Android device"))
rows.append(slack("1774456883.133439","23:41","ribadiyameet1@gmail.com","Ribadiya meet",
    "Stuck on the preparing your screen.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Stuck at preparing screen — platform initialization failure.",
    "Associate MERN Developer Interview Set","TECH ERUDITE","838cf878-7cc4-4cee-98a5-2d8ea9222a10",
    "Chrome 146.0","Windows 10","Windows PC (64-bit)",
    "https://data.flowmingo.ai/2026/03/25/16_41_15_silver-papa-india-sierra-topaz/dryuu00g0c.png"))
rows.append(slack("1774456084.827179","23:28","akhilrd2018@gmail.com","Akhil N",
    "Stuck at 44%.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Stuck at 44% during interview preparation — platform loading failure.",
    "Software Engineer Interview Set (2)","Nityo Infotech","fa44a588-3181-4897-bfdb-32dac663742e",
    "Chrome 146.0","Windows 10","Windows PC (64-bit)"))
rows.append(slack("1774455150.049679","23:12","preethikaseshadri24@gmail.com","Preethika Sesh",
    "Taking too much time for next question. I have tried 3 times with different devices.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Too long for next question, persists across 3 different devices — analysis stuck, platform bug.",
    "","","","","",""))
rows.append(slack("1774454770.408989","23:06","estherboluwatife1702@gmail.com","Esther Ogundare",
    "Unable to move to the next question & Analyze the answer.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Cannot move to next question — analysis stuck indefinitely is always platform bug.",
    "","","","","",""))
rows.append(slack("1774453939.373829","22:52","adarshmajigoudar2018@gmail.com","Adarsh Majigoudar",
    "Whatever I spoke, those answers are not saving and timer is stopping.",
    "Stage 2","Answer not saved / lost","Likely Platform Bug","Medium",
    "Answers not saving during interview — platform should persist recorded answers automatically.",
    "","","","","",""))
rows.append(slack("1774453141.617639","22:39","rohangowdaaa28@gmail.com","Rohan Gowda",
    "I have responded to the first question but there has been no reply for 20 minutes.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "No reply after first question for 20 minutes — analysis stuck indefinitely is platform bug.",
    "","","","","",""))
rows.append(slack("1774452792.536669","22:33","shristisinha.work@gmail.com","Shristi",
    "My first response is not submitting.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "First response not submitting — platform-side response capture failure.",
    "","","","","",""))
rows.append(slack_excl("1774452778.370369","22:32","shristisinha.work@gmail.com","Shristi",
    "My response is not submitting.", "Duplicate",
    "Duplicate of SLACK-1774452792.536669 — same person 1 minute earlier."))
rows.append(slack("1774451642.040669","22:14","duncan.zheng16@gmail.com","Duncan Zheng",
    "Tried interview a few times. Camera ok, but on second question video was not recorded.",
    "Stage 2","Camera / microphone not working","Likely Platform Bug","Medium",
    "Video not recorded on second question despite camera working — platform-side video capture failure.",
    "","","","Chrome 146.0","",""))
rows.append(slack("1774451558.181509","22:12","viratchaudhary700@gmail.com","Deepanshu Tewatia",
    "I am unable to give my AI Interview, I refresh multiple times every time same issue.",
    "Stage 2","Stuck during","Likely Platform Bug","Low",
    "Stuck on refresh — no specific error, low confidence.",
    "","","","","",""))
rows.append(slack("1774450676.225449","21:57","sonamkaprele24@gmail.com","Sonam Sharma",
    "My screen gets stuck with 1st answer. What should I do?",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Screen stuck after 1st answer — analysis stuck is platform bug.",
    "","","","","",""))
rows.append(slack("1774450635.220419","21:57","rajkumarogirala1705@gmail.com","Rajkumar Ogirala",
    "I cannot submit the interview answers, I had tried all the possibilities.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "All troubleshooting exhausted, still cannot submit — platform-side failure.",
    "","","","","",""))
rows.append(slack("1774450443.130909","21:54","sowmyaadhanagopal@gmail.com","Sowmyaa Dhanagopal",
    "The analyses for my first response has been happening for 10 minutes.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Analysis running for 10 minutes with no completion — stuck analyzing is always platform bug.",
    "","","","","",""))
rows.append(slack("1774450246.733339","21:50","sampadakatkade99@gmail.com","Sampada Katkade",
    "It's been showing the same response after I have recorded the answer.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Same response shown repeatedly after recording — analysis loop, platform bug.",
    "","","","","",""))
rows.append(slack("1774450132.044719","21:48","sonamkaprele24@gmail.com","Sonam Sharma",
    "I am at interview preparing stage and my screen is stuck.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Screen stuck at preparing stage — platform initialization failure.",
    "","","","","",""))
rows.append(slack("1774449928.700199","21:45","roluwakemi1@gmail.com","Runsewe Oluwakemi",
    "After answering the first question, I am unable to move on to the next question.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Cannot move to next question after answering — analysis stuck indefinitely.",
    "","","","","",""))
rows.append(slack("1774449879.874659","21:44","mandirashree.vc@gmail.com","Mandira V C",
    "The video cam to be selected is different and it's not giving me the next question.",
    "Stage 2","Camera / microphone not working","Likely Platform Bug","Medium",
    "Camera selection issue blocking next question — platform not detecting camera state correctly.",
    "","","","","",""))
rows.append(slack("1774449862.337799","21:44","smritithakur153@gmail.com","Smriti Thakur",
    "Not able to perform my interview, tried thrice, not able to hear anything.",
    "Stage 2","Camera / microphone not working","Likely Platform Bug","Medium",
    "Cannot hear questions after 3 attempts — audio delivery failure, platform bug.",
    "","","","","",""))
rows.append(slack("1774449400.441419","21:36","ramchandramane9960@gmail.com","Ramchandra Mane",
    "When I click on start interview it is not asking any question, just loading.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Click start interview, no question appears — platform initialization failure.",
    "","","","","",""))
rows.append(slack("1774449133.258949","21:32","ademola956@gmail.com","Ademola Sodamola",
    "I have been unable to get past the first question in the interview.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Cannot get past first question — analysis stuck, platform bug.",
    "","","","","",""))
rows.append(slack("1774448951.828379","21:29","hamzaaliashraf.lhr@gmail.com","Hamza Ali Ashraf",
    "Its third time I resumed the interview.",
    "Stage 2","Stuck during","Likely Platform Bug","Low",
    "Resumed three times — repeated platform failure, insufficient detail.",
    "","","","","",""))
rows.append(slack("1774448075.507539","21:14","anishasweetanisha@gmail.com","Anisha Singh",
    "It stocked after answering 1st question and it is taking so much time.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Stuck after 1st question, excessive wait — analysis stuck is platform bug.",
    "","","","","",""))
rows.append(slack("1774447703.602749","21:08","jennifer19970000@gmail.com","Jennifer Nwachukwu",
    "I think its a technical issue.",
    "Stage 2","Stuck during","Borderline","Low",
    "No specific error described — borderline, insufficient detail.",
    "","","","","",""))
rows.append(slack("1774447596.738209","21:06","kmcaelian@gmail.com","Kent Michael Handumon",
    "Internet issue.",
    "Stage 2","Stuck during","Borderline","Low",
    "Self-reported internet issue — borderline, could be user connectivity.",
    "","","","","",""))
rows.append(slack_excl("1774447442.272319","21:04","marjorie.bungalon22@gmail.com","Marjorie Bungalon",
    "Been experiencing this a lot.", "Duplicate",
    "Follow-up of SLACK-1774446062 — same person, 23 minutes later."))
rows.append(slack_excl("1774447014.298269","20:56","osasekeleni@gmail.com","Ekeleni Omuli",
    "I'm not being asked in English.", "Duplicate",
    "Same email as SHEET-BUG-260325-034 — retained Sheet ticket."))
rows.append(slack("1774446144.800259","20:42","subharaje1970@gmail.com","Subhalakshmi Shanmugam",
    "Can't attend interview and the internet has good signal.",
    "Stage 2","Stuck during","Borderline","Low",
    "Cannot attend despite good internet — borderline, could be platform or user issue.",
    "","","","","",""))
rows.append(slack("1774446072.546739","20:41","soupernika2021@gmail.com","Soupernika Hariharan Srinivasan",
    "I have been trying to complete the AI Interview, net connection is fine but keeps getting stuck.",
    "Stage 2","Stuck during","Platform Bug","Medium",
    "Stuck despite confirmed good internet — platform-side failure.",
    "","","","","",""))
rows.append(slack_excl("1774446071.671629","20:41","mrjraeo@gmail.com","Marjorie Arceo",
    "After I answered the Question, where the AI analyze my responses, it got stuck.", "Duplicate",
    "Same email as SHEET-BUG-260325-039 — retained Sheet ticket."))
rows.append(slack("1774446062.578239","20:41","marjorie.bungalon22@gmail.com","Marjorie Bungalon",
    "After my first response and submission it will just give me the analyzing screen.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Stuck on analyzing screen after first response — analysis stuck is platform bug.",
    "","","","","",""))
rows.append(slack("1774445171.854409","20:26","giftymoses1@gmail.com","Godsgift Moses",
    "I am not able to go through my interview properly.",
    "Stage 2","Stuck during","Likely Platform Bug","Low",
    "Cannot proceed through interview — insufficient detail.",
    "","","","","",""))
rows.append(slack("1774445144.991049","20:25","sruthilayaprabakaran@gmail.com","Sruthilaya S Sudhamohan",
    "When I click the 'Submit response', the response doesn't get submitted.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Submit response button not working — platform-side submission failure.",
    "","","","","",""))
rows.append(slack("1774444829.840169","20:20","mayormuiz@gmail.com","Muiz M Ade",
    "Its taking too long to analyse response. I have only answered one question.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Analysis taking too long after one question — stuck analyzing is platform bug.",
    "","","","","",""))
rows.append(slack("1774444635.474599","20:17","hafizmuhammad9120@gmail.com","Hafiz Muhammad",
    "It is taking too much time to analyzing response.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Excessive analysis time — stuck analyzing indefinitely is always platform bug.",
    "","","","","",""))
rows.append(slack("1774443987.741039","20:06","shwetgarg222@gmail.com","Shwet Garg",
    "I have answered the first question, after submission it is not working.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Not working after first question submission — analysis stuck, platform bug.",
    "","","","","",""))
rows.append(slack("1774443968.340769","20:06","emmanueljacob39@gmail.com","EMMANUEL SAMUEL",
    "AM HAVING A VERY BAD NETWORK DUE TO MY LOCATION, WILL CONTINUE TRYING.",
    "Stage 2","Stuck during","Borderline","Low",
    "Self-reported bad network due to location — borderline, likely user connectivity.",
    "","","","","",""))
rows.append(slack("1774443736.945249","20:02","blessingbabs68@gmail.com","Blessing Babatunde",
    "I am having issues doing the interview in that after answering, it keeps analyzing but not moving forward.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Keeps analyzing without moving forward — analysis stuck indefinitely is platform bug.",
    "","","","","",""))
rows.append(slack_excl("1774442924.475469","19:48","rebeccajulia777@gmail.com","Rebecca Julia Rajkumar",
    "Am facing issues while submitting my response.", "Duplicate",
    "Duplicate of SLACK-1774441886 — same issue 17 minutes later."))
rows.append(slack("1774442865.676149","19:47","palakagarwal52001@gmail.com","Palak Agarwal",
    "My interview is not moving forward, it is stuck after the 1st question.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Stuck after 1st question — analysis not completing, platform bug.",
    "","","","","",""))
rows.append(slack("1774442807.646889","19:46","susanposzler@gmail.com","Susana Beatriz Poszler",
    "El sistema queda tildado analizando mis respuestas y la entrevista no avanza.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "System stuck analyzing responses (Spanish) — analysis stuck indefinitely is platform bug.",
    "","","","","",""))
rows.append(slack("1774441886.538959","19:31","rebeccajulia777@gmail.com","Rebecca Julia Rajkumar",
    "My response is not getting analyzed, its buffering.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Response not getting analyzed, buffering — analysis stuck is platform bug.",
    "","","","","",""))
rows.append(slack("1774441881.249719","19:31","amd576437@gmail.com","Md Asif",
    "It's taking too much to analyzing.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Excessive analysis time — stuck analyzing is platform bug.",
    "","","","","",""))
rows.append(slack("1774441606.007709","19:26","novialbitaaa@gmail.com","Novi Albita",
    "I couldn't upload my resume.",
    "Stage 1","Unable to upload CV","Likely Platform Bug","Medium",
    "Unable to upload resume — platform-side upload failure.",
    "","","","","",""))
rows.append(slack("1774440601.272159","19:10","ngoctuyennguyen091@gmail.com","Tuyen Nguyen",
    "After I finished answering 1 question, the site keep analyzing my response.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Site keeps analyzing after 1st answer — stuck analyzing is platform bug.",
    "","","","","",""))
rows.append(slack("1774440435.503889","19:07","tatyanakazg@gmail.com","Tetiana Kazgova",
    "The system has a problem with analyzing and storing the responses.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "System problem with analyzing and storing responses — platform-side failure.",
    "","","","","",""))
rows.append(slack_excl("1774440070.719829","19:01","ozululilian@gmail.com","Ozulu Lilian",
    "Taking so long to analyze question and respond.", "Duplicate",
    "Same email as SHEET-BUG-260325-015 — retained Sheet ticket."))
rows.append(slack("1774439926.764669","18:58","pragati7889@gmail.com","Pragati Jaiswal",
    "Not able to go after first question, it just stopped working.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Stopped after first question — analysis stuck, platform bug.",
    "","","","","",""))
rows.append(slack("1774439298.972099","18:48","kanishkasejwal30@gmail.com","Kanishka Sejwal",
    "I have completed my interview. It's getting started again.",
    "Stage 2","Redirected to the beginning","Platform Bug","High",
    "Completed interview but it restarted — platform-side routing loop after completion.",
    "","","","","",""))
rows.append(slack("1774439118.113709","18:45","navyakannan8@gmail.com","Navya Kannan",
    "I tried to Submit the answers, but it didn't.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Submit failed — platform-side response submission failure.",
    "","","","","",""))
rows.append(slack("1774437273.233369","18:14","dalilaross88@gmail.com","Dalila Addesa",
    "The page is not working, it keeps loading, and it's already 3 times.",
    "Stage 2","Stuck during","Platform Bug","High",
    "Page not loading 3 times in a row — repeated platform failure.",
    "","","","","",""))
rows.append(slack("1774437081.411629","18:11","info@viriminfotech.com","Virim Infotech",
    "I have created an interview for 10 people to join at the same time. Sometimes candidates get no invite, or link says not available.",
    "Other (Company)","Other (Company)","Platform Bug","High",
    "Candidates not receiving invites or link unavailable — company-side platform invite failure.",
    "","Virim Infotech","","","",""))
rows.append(slack_excl("1774436797.102839","18:06","madhushree6565@gmail.com","Madhushree R",
    "No response.", "Duplicate",
    "Vague follow-up of SLACK-1774435152 — same person, 27 minutes later."))
rows.append(slack("1774436725.455899","18:05","malavikamanoj09@gmail.com","Malavika Manoj",
    "It is getting stuck at 25% loading.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Stuck at 25% during preparing — platform loading failure.",
    "","","","","",""))
rows.append(slack_excl("1774436551.416859","18:02","malavikamanoj09@gmail.com","Malavika Manoj",
    "The interview is stuck.", "Duplicate",
    "Duplicate of SLACK-1774436725 — same person, 3 minutes earlier, less specific."))
rows.append(slack("1774435566.119379","17:46","mogotsimerriam@gmail.com","Merriam Mogotsi",
    "Can't resume.",
    "Stage 2","Stuck during","Likely Platform Bug","Medium",
    "Cannot resume interview — platform-side session resume failure.",
    "","","","","",""))
rows.append(slack("1774435152.636709","17:39","madhushree6565@gmail.com","Madhushree R",
    "It's not working properly.",
    "Stage 2","Stuck during","Likely Platform Bug","Low",
    "Not working properly — insufficient detail.",
    "","","","","",""))
rows.append(slack("1774434910.954029","17:35","aarushimehra01@gmail.com","Aarushi Mehra",
    "The audio is not uploading, tried 3 times.",
    "Stage 2","Camera / microphone not working","Platform Bug","High",
    "Audio not uploading after 3 attempts — platform-side audio recording/upload failure.",
    "","","","","",""))
rows.append(slack("1774434729.824019","17:32","oluwatofunmioguntade11@gmail.com","Oluwatofunmi Oguntade",
    "I am encountering a persistent Network problem on the Flowmingo platform.",
    "Stage 2","Stuck during","Borderline","Medium",
    "Persistent network problem on platform — borderline, could be platform or ISP routing.",
    "","","","","",""))
rows.append(slack_excl("1774434580.489959","17:29","mogotsimerriam@gmail.com","Merriam Mogotsi",
    "Can't submit my response.", "Duplicate",
    "Duplicate of SLACK-1774434377 — same person, 3 minutes later."))
rows.append(slack("1774434477.030339","17:27","olokoteephey@gmail.com","Boluwatife Oloko",
    "Analyzing my response takes time.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Analysis taking too long — stuck analyzing is platform bug.",
    "","","","","",""))
rows.append(slack_excl("1774434427.838819","17:27","vasucsfb2229@svvv.edu.in","VASU YADAV",
    "The screen has been struck only showing just a moment we're analyzing.", "Duplicate",
    "Duplicate of SLACK-1774433894 — same person, 9 minutes later."))
rows.append(slack("1774434377.648299","17:26","mogotsimerriam@gmail.com","Merriam Mogotsi",
    "Network can't submit my response.",
    "Stage 2","Stuck during","Borderline","Low",
    "Network + cannot submit — borderline, connectivity reported.",
    "","","","","",""))
rows.append(slack("1774434031.251129","17:20","aminasbongile@gmail.com","Bongi Mahlangu",
    "It keeps on taking me back to the first page.",
    "Stage 2","Redirected to the beginning","Platform Bug","High",
    "Redirected to first page repeatedly — platform routing loop, no user action causes this.",
    "","","","","",""))
rows.append(slack_excl("1774433928.269779","17:18","aminasbongile@gmail.com","Bongi Mahlangu",
    "Im stuck.", "Duplicate",
    "Duplicate of SLACK-1774434031 — same person 2 minutes earlier, less specific."))
rows.append(slack("1774433894.306149","17:18","vasucsfb2229@svvv.edu.in","VASU YADAV",
    "It has been stuck and showing just a moment we're analyzing your response.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "Explicitly stuck on 'analyzing your response' — analysis stuck indefinitely is platform bug.",
    "","","","","",""))
rows.append(slack_excl("1774433892.671679","17:18","mailpastordave@gmail.com","David Ekpe",
    "Being interviewed but network from interviewer is inconsistent.", "Duplicate",
    "Same email as SHEET-BUG-260325-018 — retained Sheet ticket."))
rows.append(slack("1774433876.053999","17:17","subhalakshmi112004@gmail.com","Subhalakshmi Shanmugam",
    "Interview is not scheduling.",
    "Stage 1","Unable to access","Likely Platform Bug","Medium",
    "Interview not scheduling — platform-side scheduling/access failure.",
    "","","","","",""))
rows.append(slack("1774433875.982219","17:17","sharmaprachi2503@gmail.com","Prachi Sharma",
    "Interview is stopped suddenly.",
    "Stage 2","Stuck during","Platform Bug","High",
    "Interview stopped suddenly mid-session — platform-side stability failure.",
    "","","","","",""))
rows.append(slack_excl("1774433860.701699","17:17","patelajay.1605@gmail.com","Ajay Patel",
    "It is loading and not working.", "Duplicate",
    "Duplicate of SLACK-1774433299 — same person."))
rows.append(slack_excl("1774433838.792189","17:17","jeremiahobua8@gmail.com","Jeremiah Obua",
    "Trying to move to next stage, it just freezes.", "Duplicate",
    "Same email as SHEET-BUG-260325-042 — retained Sheet ticket."))
rows.append(slack("1774433822.791749","17:17","michellesequeira93.ms@gmail.com","Michelle Dsouza",
    "Can't load it says preparing your interview.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Stuck at 'preparing your interview' — platform initialization failure.",
    "","","","","",""))
rows.append(slack("1774433751.204549","17:15","mandarrparab5@gmail.com","Mandarr Parab",
    "The screen has freeze when preparing for interview on 25%.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Screen frozen at 25% during preparation — platform loading failure.",
    "","","","","",""))
rows.append(slack_excl("1774433712.796909","17:15","sharmaprachi2503@gmail.com","Prachi Sharma",
    "My answer is not analysed yet.", "Duplicate",
    "Duplicate of SLACK-1774433875 — same person 2 minutes earlier."))
rows.append(slack_excl("1774433697.229649","17:14","patelajay.1605@gmail.com","Ajay Patel",
    "It is not going ahead.", "Duplicate",
    "Duplicate of SLACK-1774433299 — same person."))
rows.append(slack_excl("1774433603.699409","17:13","ozululilian@gmail.com","Ozulu Lilian",
    "It is taking a long time to analyze and move forward.", "Duplicate",
    "Same email as SHEET-BUG-260325-015 — retained Sheet ticket."))
rows.append(slack("1774433530.588979","17:12","arnair30@gmail.com","Aiswarya R",
    "For a 30 minute interview I have to sit for 2 hours because of the stuck analyzing issue.",
    "Stage 2","Stuck analyzing","Platform Bug","High",
    "30-min interview took 2 hours due to stuck analyzing — analysis stuck is platform bug.",
    "","","","","",""))
rows.append(slack("1774433299.754719","17:08","patelajay.1605@gmail.com","Ajay Patel",
    "Not working, it continuously refreshes the page.",
    "Stage 2","Stuck during","Platform Bug","High",
    "Continuous page refresh loop — platform-side state failure.",
    "","","","","",""))
rows.append(slack("1774433137.708489","17:05","abdul.wadood.khan4@gmail.com","Abdul Wadood Khan",
    "The interview doesn't start even after pressing start interview button.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Start interview button not working — platform initialization failure.",
    "","","","","",""))
rows.append(slack("1774433015.251569","17:03","jaganmohan0149@outlook.com","Jagan Mohan Rao Korada",
    "Unable to proceed, stuck at 35.7%.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Stuck at 35.7% during preparation — platform loading failure.",
    "","","","","",""))
rows.append(slack_excl("1774431848.924199","16:44","ozululilian@gmail.com","Ozulu Lilian",
    "I started the interview and it did not respond.", "Duplicate",
    "Same email as SHEET-BUG-260325-015 — retained Sheet ticket."))
rows.append(slack("1774431786.789239","16:43","recruitment.bryankaye@gmail.com","Bryan Kaye De Guzman",
    "Preparing interview stopped at 25.0%.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Stopped at 25% during preparation — platform loading failure.",
    "","","","","",""))
rows.append(slack("1774431776.532219","16:42","ahsan.rais@valus.io","Ahsan Rais",
    "One candidate submitted their interview but I can't see it in the dashboard.",
    "Other (Company)","Other (Company)","Platform Bug","High",
    "Candidate submission not visible in recruiter dashboard — platform-side data sync failure.",
    "","Valus","","","",""))
rows.append(slack_excl("1774431630.969109","16:40","bhavnay828@gmail.com","Bhavna Yadav",
    "I am not able to start my AI interview.", "Duplicate",
    "Same email as SHEET-BUG-260325-023 — retained Sheet ticket."))
rows.append(slack_excl("1774431402.211009","16:36","arnair30@gmail.com","Aiswarya R",
    "Its not working properly. I tried using different devices and internet.", "Duplicate",
    "Duplicate of SLACK-1774433530 — same person, less specific."))
rows.append(slack_excl("1774430848.441849","16:27","shruthibambila@gmail.com","Shruthi B",
    "Technical issues.", "Duplicate",
    "Same email as SHEET-BUG-260325-008 — retained Sheet ticket."))
rows.append(slack("1774430711.662449","16:25","floyd.ilustrado@gmail.com","Floyd Ilustrado",
    "Stuck when loading --- Preparing your interview (25.0%).",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Stuck at 25% preparing — platform initialization failure.",
    "","","","","",""))
rows.append(slack("1774430084.924459","16:14","mary.odanga@strathmore.edu","Mary Odanga",
    "On the demo I can't see or hear myself.",
    "Stage 2","Camera / microphone not working","Likely Platform Bug","Medium",
    "Cannot see or hear self on demo — platform not reading camera/mic.",
    "","","","","",""))
rows.append(slack("1774428945.966039","16:27","firozdanny416@gmail.com","Danishta Firoz",
    "I am facing issue in submitting my interview response due to network issue from platform side.",
    "Stage 2","Stuck during","Borderline","Medium",
    "Platform-side network issue reported for submission — borderline.",
    "","","","","",""))
rows.append(slack("1774427297.697339","15:28","sanjayk4it@gmail.com","Sanjay Kumar",
    "I have to refresh page again and again, and answering same question.",
    "Stage 2","Redirected to the beginning","Platform Bug","High",
    "Page refresh loops to same question — platform routing loop.",
    "","","","","",""))
rows.append(slack("1774426835.696439","15:20","adkrishnaraj@gmail.com","Krishnaraj A D",
    "The site isn't loading in any device, takes a lot of time for starting.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Site not loading across devices — platform initialization failure.",
    "","","","","",""))
rows.append(slack("1774426504.373279","15:15","shanoofrehman@gmail.com","Shanoof Rehman",
    "I am stuck in the Preparing your interview screen.",
    "Stage 1","Stuck at Preparing","Platform Bug","High",
    "Stuck at preparing screen — platform initialization failure.",
    "","","","","",""))

# ── Write CSV ──────────────────────────────────────────────────────────────────
with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=COLS)
    writer.writeheader()
    writer.writerows(rows)

from collections import Counter
included = [r for r in rows if r["stage"] != "EXCLUDED"]
excluded = [r for r in rows if r["stage"] == "EXCLUDED"]
print(f"Total rows: {len(rows)} | Included: {len(included)} | Excluded: {len(excluded)}")
stage_counts = Counter(r["stage"] for r in included)
for s in ["Stage 1","Stage 2","Stage 3","Other (Company)","Other (Candidate)"]:
    print(f"  {s}: {stage_counts.get(s,0)}")
cat_counts = Counter(r["category"] for r in included)
print("\nTop categories:")
for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
    print(f"  {cat}: {cnt}")
print(f"\nIncluded bugs: {len(included)}")
