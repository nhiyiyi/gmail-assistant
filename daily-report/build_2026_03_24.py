#!/usr/bin/env python3
"""Build 2026-03-24 daily report CSV and push to Google Sheet."""
import csv, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OUTPUT = os.path.join(os.path.dirname(__file__), "2026-03-24.csv")

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
    r["date"] = "2026-03-24"
    r["include_in_report"] = "?"
    r["approval_status"] = "new"
    r.update(kw)
    return r

rows = []

# ── GOOGLE SHEET ENTRIES ──────────────────────────────────────────────────────

rows.append(row(
    source_id="SHEET-BUG-260324-001", time_gmt7="04:48", source="Google Sheet",
    ticket_id="BUG-260324-001",
    source_link="https://mail.google.com/mail/u/0/#all/19d1de57e0859fff",
    original_content="After completing the interview, screen stuck on loading for 10+ min. Camera remains active. Cannot click 'need help'.",
    email="iam@manegallo.com", candidate_name="Man", topic_raw="Post-Interview Issue",
    stage="Stage 3", category="Stuck evaluating",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Screen stuck on loading post-interview with camera still active is a classic stuck-evaluating symptom; no user action can cause infinite post-submit loading."
))
rows.append(row(
    source_id="SHEET-BUG-260324-002", time_gmt7="09:48", source="Google Sheet",
    ticket_id="BUG-260324-002",
    source_link="https://mail.google.com/mail/u/0/#all/19d1eb167c81e189",
    original_content="Unable to access interview link since yesterday. Link is not working.",
    email="tanushree.nabar@gmail.com", candidate_name="Tanushree", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Link not working persisting since previous day suggests a platform-side expiry or routing issue; no specific user error indicated."
))
rows.append(row(
    source_id="SHEET-BUG-260324-003", time_gmt7="12:47", source="Google Sheet",
    ticket_id="BUG-260324-003",
    source_link="https://mail.google.com/mail/u/0/#all/19d1f929657d667e",
    original_content="Camera will not turn on during interview session even after refreshing. Screenshot provided.",
    email="bachtrinh.wp@gmail.com", candidate_name="Bach", topic_raw="Feature Not Working",
    stage="Stage 2", category="Camera / microphone not working",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Camera not detected even after refresh suggests platform-side permission handling issue; may require permission troubleshooting or platform camera access bug."
))
rows.append(row(
    source_id="SHEET-BUG-260324-004", time_gmt7="12:47", source="Google Sheet",
    ticket_id="BUG-260324-004",
    source_link="https://mail.google.com/mail/u/0/#all/19d1f5a77baeca99",
    original_content="Website not working when attempting to start the interview. Requests practice and interview links.",
    email="ikhenobajoseph60@gmail.com", candidate_name="Joseph", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="No specific error message provided; website not working at interview start is likely a platform access issue but details are insufficient for high confidence."
))
rows.append(row(
    source_id="SHEET-BUG-260324-005", time_gmt7="12:47", source="Google Sheet",
    ticket_id="BUG-260324-005",
    source_link="https://mail.google.com/mail/u/0/#all/19cf9f9f5bade16a",
    original_content="System shows 'already submitted my application' and prevents restarting for 3 consecutive days.",
    email="rinah@inar.ae", candidate_name="Ranim", topic_raw="Feature Not Working",
    stage="Stage 1", category="Link already used / expired",
    assessment="Borderline", confidence="Medium",
    assessment_notes="System preventing resubmission could be correct behavior (already submitted) or a platform state error; borderline without knowing if a genuine prior submission exists."
))
rows.append(row(
    source_id="SHEET-BUG-260324-006", time_gmt7="15:59", source="Google Sheet",
    ticket_id="BUG-260324-006",
    source_link="https://mail.google.com/mail/u/0/#all/19d205ba647c6ecd",
    original_content="Interview link is not working. No specific error message provided.",
    email="aani700626@gmail.com", candidate_name="Chucha", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Low",
    assessment_notes="Link not working with no error details; likely platform-side but cannot confirm without more information."
))
rows.append(row(
    source_id="SHEET-BUG-260324-007", time_gmt7="15:59", source="Google Sheet",
    ticket_id="BUG-260324-007",
    source_link="https://mail.google.com/mail/u/0/#all/19d2018220f81a3f",
    original_content="Stuck at 00:00 during submission; interview restarted to question 7 at 00:00. Unsure if prior answers were recorded.",
    email="amanda.m.bastos@gmail.com", candidate_name="Amanda", topic_raw="Feature Not Working",
    stage="Stage 2", category="Redirected to the beginning",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Timer reaching 00:00 then resetting to an earlier question is a platform-side routing loop; no user action should cause this behavior."
))
rows.append(row(
    source_id="SHEET-BUG-260324-008", time_gmt7="15:59", source="Google Sheet",
    ticket_id="BUG-260324-008",
    source_link="https://mail.google.com/mail/u/0/#all/19d1fe629d115c46",
    original_content="Unable to access interview link despite trying multiple browsers. Requests alternative access method.",
    email="taisha.tahir@gmail.com", candidate_name="Aisha", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Issue persists across multiple browsers, ruling out browser-specific user error; platform access problem is the likely cause."
))
rows.append(row(
    source_id="SHEET-BUG-260324-009", time_gmt7="18:47", source="Google Sheet",
    ticket_id="BUG-260324-009",
    source_link="https://mail.google.com/mail/u/0/#all/19d20d093d62dea5",
    original_content="System repeatedly displayed the same question multiple times and did not save previous answers, forcing redo beyond 30-hour deadline.",
    email="ltchauanh4425@gmail.com", candidate_name="Anh", topic_raw="Feature Not Working",
    stage="Stage 2", category="Redirected to the beginning",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Repeated questions with answers not saved is a platform-side routing/state bug; per hints, repeated/looping questions map to 'Redirected to the beginning'."
))
rows.append(row(
    source_id="SHEET-BUG-260324-010", time_gmt7="21:28", source="Google Sheet",
    ticket_id="BUG-260324-010",
    source_link="https://mail.google.com/mail/u/0/#all/19d21687845d582e",
    original_content="Unable to access scheduled interview due to a network issue. No specific error message provided.",
    email="anchembiaanthony121@gmail.com", candidate_name="Anthony", topic_raw="Feature Not Working",
    stage="Stage 1", category="Unable to access",
    assessment="Borderline", confidence="Low",
    assessment_notes="Candidate self-reports a network issue which may be user-side connectivity; classified as borderline without evidence of a platform-side failure."
))
rows.append(row(
    source_id="SHEET-BUG-260324-011", time_gmt7="21:29", source="Google Sheet",
    ticket_id="BUG-260324-011",
    source_link="https://mail.google.com/mail/u/0/#all/19d215d27b673650",
    original_content="Error stating 'already completed' prevents accessing assessment. Screenshots attached.",
    email="pratiksha.mugdiya@gmail.com", candidate_name="Pratiksha", topic_raw="Feature Not Working",
    stage="Stage 1", category="Link already used / expired",
    assessment="Borderline", confidence="Medium",
    assessment_notes="System shows 'already completed' — could be legitimate prior completion or a platform state error; borderline without context on whether candidate actually submitted."
))

# ── SLACK ENTRIES ─────────────────────────────────────────────────────────────

rows.append(row(
    source_id="SLACK-1774296063.463059", time_gmt7="03:01", source="Slack",
    original_content="Hi. Please advise why I am not able to send an invite to a new team member",
    email="o.tsybko@utrustins.com", candidate_name="Olga Tsybko", topic_raw="Others",
    stage="Other (Company)", category="Other (Company)",
    browser="Edge 146.0", os="Windows 10", device="Windows PC (64-bit)",
    screenshot_url="https://data.flowmingo.ai/2026/03/23/20_00_09_golf-quebec-coral-silver-lima/ekuutsiehl.png",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Recruiter cannot send team invite — company-side platform feature failure with no user error possible for this action type."
))
rows.append(row(
    source_id="SLACK-1774299847.950799", time_gmt7="04:04", source="Slack",
    original_content="I completed an interview earlier on and it refreshed the page I somehow lost all my answers are you able to help get those answers for me or for me to finish where I left off",
    email="alettajulia.malebonyane@gmail.com", candidate_name="Aletta Malebonyane", topic_raw="Technical Issue",
    stage="Stage 2", category="Answer not saved / lost",
    submission_id="8d7352c4-31b0-4bdc-bb05-b93c8ca66426",
    interview_position="QA / QC Intern - Actual Hiring For linkedin Applications", interview_company="Flowmingo",
    browser="Safari", os="macOS", device="iPhone",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Page refresh during interview caused all answers to be lost; platform should persist session state, losing all answers on refresh points to missing session persistence."
))
rows.append(row(
    source_id="SLACK-1774324137.055069", time_gmt7="10:48", source="Slack",
    original_content="i want to change my email to john.nicholai.vigilia@gmail.com",
    email="renovatepal@gmail.com", candidate_name="John Nicholai Vigilia", topic_raw="Feature Request",
    stage="EXCLUDED", category="Feature Request",
    submission_id="f857f812-737d-402b-b665-cbc547f21eb1",
    interview_position="Front End Developer Interview Set", interview_company="My School Suite",
    browser="Firefox 148.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="N/A", confidence="High",
    assessment_notes="Feature Request topic — excluded per reporting rules."
))
rows.append(row(
    source_id="SLACK-1774324381.864099", time_gmt7="10:53", source="Slack",
    original_content="quy test",
    email="quy.phan+250201@gethomebase.com", candidate_name="quy h", topic_raw="Others",
    stage="EXCLUDED", category="Internal Test",
    submission_id="02c0dc56-ef8b-433c-9524-8253306dd522",
    interview_position="1703-17", interview_company="Homebase-Qtest",
    browser="Chrome 146.0", os="macOS 10.15.7", device="Mac",
    assessment="N/A", confidence="High",
    assessment_notes="Content is 'quy test' — clearly an internal test submission, excluded per reporting rules."
))
rows.append(row(
    source_id="SLACK-1774329408.739119", time_gmt7="12:16", source="Slack",
    original_content="I have to pay??",
    email="aidacecilia94@gmail.com", candidate_name="Aida Gurdian", topic_raw="Payment Issue",
    stage="EXCLUDED", category="UX Confusion",
    submission_id="5ae1a4e5-84a0-4d2d-a44b-b73ccdc87edf",
    interview_position="Executive Assistant", interview_company="Salas Staffing",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="N/A", confidence="High",
    assessment_notes="Asking whether payment is required — UX confusion, not a platform bug."
))
rows.append(row(
    source_id="SLACK-1774330071.679059", time_gmt7="12:27", source="Slack",
    original_content="For like 2 hours, the status/Score of candidates is saying Analyzing. How much time does this take?",
    email="sachin@av-core.com", candidate_name="Sachin Shah", topic_raw="User Experience Feedback",
    stage="Stage 3", category="Stuck evaluating",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    screenshot_url="https://data.flowmingo.ai/2026/03/24/05_27_45_quebec-juliet-foxtrot-amber-topaz/cvam771o4r.jpg",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Recruiter reports candidate scores stuck at 'Analyzing' for 2 hours — AI evaluation not completing is a platform-side failure that no user action can cause."
))
rows.append(row(
    source_id="SLACK-1774332474.577169", time_gmt7="13:07", source="Slack",
    original_content="Em phai tra loi 1 cau hoi nhieu lan va thoi gian cho response kha lau",
    email="giangtranlh.work@gmail.com", candidate_name="Giang Tran Le Hieu", topic_raw="Van de Ky thuat",
    stage="Stage 2", category="Stuck analyzing",
    submission_id="340936d5-c374-4848-8742-9b3eeaa3f418",
    interview_position="Yiyi - Growth Product (Intern/Fresher) For Linkedin Applications", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    screenshot_url="https://data.flowmingo.ai/2026/03/24/06_07_31_xray-coral-sierra-xray-jade/jonq918ht6.png",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Vietnamese: had to answer same question multiple times with long response wait — classic stuck-analyzing behavior where analysis never completes and forces retries."
))
rows.append(row(
    source_id="SLACK-1774333274.799319", time_gmt7="13:21", source="Slack",
    original_content="I can't hear the question",
    email="flores.arveen@gmail.com", candidate_name="Arveen Flores", topic_raw="Technical Issue",
    stage="Stage 2", category="AI avatar not loading",
    submission_id="77cc7368-a070-43e6-9e13-a3707f58b662",
    interview_position="Senior Business Analyst Interview Set", interview_company="My School Suite",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Candidate cannot hear the interview questions — AI avatar audio not playing is a platform-side media delivery failure."
))
rows.append(row(
    source_id="SLACK-1774338804.370629", time_gmt7="14:53", source="Slack",
    original_content="Some medical emergency",
    email="komalprashant312@gmail.com", candidate_name="Komal Tiwari", topic_raw="Others",
    stage="EXCLUDED", category="Not Technical",
    submission_id="699459b7-4409-460f-ae10-ba884dde7c35",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 145.0", os="Android 10", device="Android device",
    assessment="N/A", confidence="High",
    assessment_notes="Personal emergency reported, not a platform bug."
))
rows.append(row(
    source_id="SLACK-1774340101.187649", time_gmt7="15:15", source="Slack",
    original_content="I think so due to connectivity issues.",
    email="madhu.hrservices@gmail.com", candidate_name="Madhu Jha", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck during",
    submission_id="1405bb0c-5105-4726-b699-82aeac2883fe",
    interview_position="Talent Acquisition Business Partner (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Borderline", confidence="Low",
    assessment_notes="Self-reported connectivity issues — could be user's network or platform instability; classified as Stuck during due to connectivity mid-session."
))
rows.append(row(
    source_id="SLACK-1774342650.963249", time_gmt7="15:57", source="Slack",
    original_content="When i want to submit interveiw without paying for the premiuim i am not able",
    email="aaryanbolugam9@gmail.com", candidate_name="ARYAN BOLUGAM", topic_raw="Technical Issue",
    stage="EXCLUDED", category="UX Confusion",
    submission_id="5a7c4368-8212-493d-9fbd-446e8b4a09a9",
    interview_position="Business Development Intern Interview Set", interview_company="Zartek Technologies",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="N/A", confidence="High",
    assessment_notes="User believes premium payment is required to submit — UX confusion about the platform's free usage, not a bug."
))
rows.append(row(
    source_id="SLACK-1774344993.191499", time_gmt7="16:36", source="Slack",
    original_content="I have answered the question twice however the AI cannot hear me still after a long processeing",
    email="ongpaul2002@gmail.com", candidate_name="Paul Ong", topic_raw="Technical Issue",
    stage="Stage 2", category="Camera / microphone not working",
    submission_id="c6697da5-d018-4f06-bf29-fac3f2bf2929",
    interview_position="AI Developer Interview Set", interview_company="My School Suite",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="AI cannot detect audio after two attempts — microphone not being captured by the platform despite user's hardware being functional."
))
rows.append(row(
    source_id="SLACK-1774345367.341959", time_gmt7="16:42", source="Slack",
    original_content="I already submit my response twice but the AI advise she cant hear nothing.",
    email="flores.arveen@gmail.com", candidate_name="Arveen Flores", topic_raw="Technical Issue",
    stage="EXCLUDED", category="Duplicate",
    submission_id="77cc7368-a070-43e6-9e13-a3707f58b662",
    interview_position="Senior Business Analyst Interview Set", interview_company="My School Suite",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="N/A", confidence="High",
    assessment_notes="Duplicate follow-up from same candidate (Arveen Flores, same submission ID 77cc7368) — kept first/more detailed submission at 13:21."
))
rows.append(row(
    source_id="SLACK-1774345522.300899", time_gmt7="16:45", source="Slack",
    original_content="In unable to answr",
    email="shrutidwivedi865@gmail.com", candidate_name="Shruti Dwivedi", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck analyzing",
    submission_id="70c65950-1971-44b5-9377-7bdfdfd45c30",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Samsung Internet 29.0", os="Android 10", device="Android device",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Unable to answer/proceed during interview — likely stuck waiting for analysis to complete before next question appears."
))
rows.append(row(
    source_id="SLACK-1774345768.691369", time_gmt7="16:49", source="Slack",
    original_content="Only one question appeared.",
    email="goravsingh121@gmail.com", candidate_name="Gorav Singh", topic_raw="Technical Issue",
    stage="Stage 2", category="Question skipped / missing",
    submission_id="b719aebf-7aa9-423f-88d6-22aa80b9b34c",
    interview_position="Flowmingo Global Management Trainee (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Android 10", device="Android device",
    screenshot_url="https://data.flowmingo.ai/2026/03/24/09_49_24_blue-violet-silver-sierra-xray/bkyznk6l7x.jpg",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Only one question appeared in the entire interview set — remaining questions were not shown, indicating a platform-side question delivery failure."
))
rows.append(row(
    source_id="SLACK-1774347776.609269", time_gmt7="17:22", source="Slack",
    original_content="I can not access my 30 mjinutes AI interview",
    email="n_elez@hotmail.com", candidate_name="Nina MAdjura", topic_raw="Technical Issue",
    stage="Stage 1", category="Unable to access",
    submission_id="0fc87e19-ad63-4eec-869d-e9059aad8a38",
    interview_position="Talent Acquisition Business Partner (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Edge 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Cannot access AI interview — access failure before interview starts is likely platform-side link or routing issue."
))
rows.append(row(
    source_id="SLACK-1774349001.592869", time_gmt7="17:43", source="Slack",
    original_content="I hav given permission for camera access and it still shows grant access",
    email="rakshamehra02@gmail.com", candidate_name="Raksha Mehra", topic_raw="Others",
    stage="Stage 2", category="Camera / microphone not working",
    submission_id="467a5d5b-77d4-4bbd-b2a5-c250f1b0bbfd",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 145.0", os="Android 10", device="Android device",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Camera permission granted but platform still shows 'grant access' prompt — platform not detecting browser permission state correctly."
))
rows.append(row(
    source_id="SLACK-1774349717.270489", time_gmt7="17:55", source="Slack",
    original_content="the window is stuck more than 3 times",
    email="aachu6317@gmail.com", candidate_name="archana santhosh", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck during",
    submission_id="3e1abd1b-7971-4207-8c75-2ee91c7ffa96",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Window stuck/frozen more than 3 times during interview — repeated freezing is a platform-side stability issue."
))
rows.append(row(
    source_id="SLACK-1774350706.369799", time_gmt7="18:11", source="Slack",
    original_content="The camera doesn't turn on, I already refresh the page",
    email="bachtrinh.wp@gmail.com", candidate_name="Bach Trinh", topic_raw="Technical Issue",
    stage="Stage 2", category="Camera / microphone not working",
    submission_id="e6cdc13e-16d4-49e0-afbe-5b5e9839b882",
    interview_position="Flowmingo Finance & Accounting Intern For linkedin Applications", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    screenshot_url="https://data.flowmingo.ai/2026/03/24/11_11_34_silver-tango-pearl-amber-violet/ivk2p94udi.png",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Camera not turning on even after page refresh — platform not initializing camera correctly despite user having granted permissions."
))
rows.append(row(
    source_id="SLACK-1774351587.477709", time_gmt7="18:26", source="Slack",
    original_content="It is not moving to next question",
    email="nikitharao290402@gmail.com", candidate_name="Nikitha Rao", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck analyzing",
    submission_id="88545412-e972-47bd-8f6f-7fd108922196",
    interview_position="Teacher Interview Set (1)", interview_company="Hiringlabs Business Solutions",
    browser="Chrome 145.0", os="Android 10", device="Android device",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Interview not advancing to next question after answer submission — analysis stuck indefinitely, which no user action can cause."
))
rows.append(row(
    source_id="SLACK-1774353149.319369", time_gmt7="18:52", source="Slack",
    original_content="While I am trying to attend the AI interview, the page indicates 'We couldn't detect camera or microphone.' where my camera and microphone is accessible as per laptop and phone.",
    email="ramyaiyengar1717@gmail.com", candidate_name="Ramya Iyengar", topic_raw="Technical Issue",
    stage="Stage 2", category="Camera / microphone not working",
    submission_id="923882ec-6669-4d45-a695-0c2c114df230",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    screenshot_url="https://data.flowmingo.ai/2026/03/24/11_52_22_coral-charlie-lima-sierra-hotel/w1nxc1jewm.png",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Platform shows 'couldn't detect camera or microphone' despite user confirming camera/mic are accessible on both laptop and phone — platform detection failure."
))
rows.append(row(
    source_id="SLACK-1774357027.768249", time_gmt7="19:57", source="Slack",
    original_content="doesnt record anything I speak",
    email="shekinah.reno@gmail.com", candidate_name="Shekinah keren", topic_raw="Technical Issue",
    stage="Stage 2", category="Camera / microphone not working",
    submission_id="f740e7f6-b65d-416d-8c22-caf112af0d8d",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    screenshot_url="https://data.flowmingo.ai/2026/03/24/12_56_59_bravo-bravo-victor-golf-golf/m2s7e6yjui.jpg",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Platform does not record audio despite user speaking — microphone input not being captured by the platform."
))
rows.append(row(
    source_id="SLACK-1774357103.471119", time_gmt7="19:58", source="Slack",
    original_content="Screen stop",
    email="vjitender310@gmail.com", candidate_name="jitender verma", topic_raw="Technical Issue",
    stage="EXCLUDED", category="Duplicate",
    submission_id="ab4f0c10-cfcb-405a-9569-94fa17390c3b",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Android 10", device="Android device",
    assessment="N/A", confidence="High",
    assessment_notes="Duplicate of the 20:15 submission (same candidate, same submission ID ab4f0c10, identical content 'Screen stop')."
))
rows.append(row(
    source_id="SLACK-1774358145.236689", time_gmt7="20:15", source="Slack",
    original_content="Screen stop",
    email="vjitender310@gmail.com", candidate_name="jitender verma", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck during",
    submission_id="ab4f0c10-cfcb-405a-9569-94fa17390c3b",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Android 10", device="Android device",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Screen freezing mid-interview is a platform-side stability issue; 'screen stop' indicates interview froze completely."
))
rows.append(row(
    source_id="SLACK-1774359256.944709", time_gmt7="20:34", source="Slack",
    original_content="It is buffering from the last minutes even after restarting the website.",
    email="nilanjanaghosh008@gmail.com", candidate_name="Nilanjana Ghosh", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck during",
    submission_id="dd542d5c-e467-48ab-b1a7-fab6554ae83a",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Continuous buffering even after page restart indicates platform-side video/content delivery failure."
))
rows.append(row(
    source_id="SLACK-1774359769.274819", time_gmt7="20:42", source="Slack",
    original_content="The platform stopped when I had completed all the questions and achieved 00:00 minutes. It returned to minutes 7:00 with the question made in the beginning.",
    email="amanda.m.bastos@gmail.com", candidate_name="Amanda Bastos", topic_raw="Problema Tecnico",
    stage="Stage 2", category="Redirected to the beginning",
    submission_id="32a434ee-010b-43ea-84d4-a559c0a76078",
    interview_position="Project Support Specialist 260320-DOU-001", interview_company="ITProposal",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Completed all questions at 00:00 then redirected back to an earlier question — platform-side routing loop after timer completion."
))
rows.append(row(
    source_id="SLACK-1774360160.047829", time_gmt7="20:49", source="Slack",
    original_content="my video is not showing up although my camera is on and beacuse of that i'm unable to click on continue",
    email="yashasvighatpande01@gmail.com", candidate_name="yashasvi ghatpande", topic_raw="Technical Issue",
    stage="Stage 2", category="Camera / microphone not working",
    submission_id="f06eaa13-90dd-4b3d-970c-9e0ed69e6225",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    screenshot_url="https://data.flowmingo.ai/2026/03/24/13_47_30_yankee-bravo-violet-topaz-hotel/cg8i0khwdf.png",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Camera is on but video not showing in platform preview — platform not reading the camera feed despite device camera being active."
))
rows.append(row(
    source_id="SLACK-1774360454.057909", time_gmt7="20:54", source="Slack",
    original_content="I want English",
    email="blessingcharles675@gmail.com", candidate_name="Blessing Charles", topic_raw="Others",
    stage="EXCLUDED", category="Likely User Error",
    submission_id="cb3b8e5d-04f8-4b38-a7b9-96c31d87cc06",
    interview_position="Talent Acquisition Business Partner (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Android 10", device="Android device",
    assessment="Likely User Error", confidence="High",
    assessment_notes="Per judgment rules: 'I want to change my language' with no system error evidence is Likely User Error — may not know how to change language preference."
))
rows.append(row(
    source_id="SLACK-1774362863.542019", time_gmt7="21:34", source="Slack",
    original_content="Unstable connection",
    email="kirk.a.manuel@gmail.com", candidate_name="Kirk Anthony Manuel", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck during",
    submission_id="1e03ca45-1f98-42a8-8176-ff689370b5cc",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Safari 26.3", os="macOS", device="iPhone",
    assessment="Borderline", confidence="Low",
    assessment_notes="Unstable connection reported — could be user's network or platform-side connectivity issue; classified as Stuck during due to connection problem mid-interview."
))
rows.append(row(
    source_id="SLACK-1774364872.531639", time_gmt7="22:07", source="Slack",
    original_content="I'm not getting next questions",
    email="simrangurjar1902@gmail.com", candidate_name="Simran Gurjar", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck analyzing",
    submission_id="ebac78f1-5486-4dbf-9322-bf796189228a",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome iOS 144.0", os="macOS", device="iPhone",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Not receiving next questions after answering — interview stuck analyzing previous response, not advancing to next question."
))
rows.append(row(
    source_id="SLACK-1774365119.429109", time_gmt7="22:11", source="Slack",
    original_content="I am waiting in the call and its showing Just a moment, we are analyzing your response but till now no response. Can I drop off? Is my interview completed?",
    email="sindhu.manjunath0497@gmail.com", candidate_name="SINDHU M", topic_raw="Others",
    stage="Stage 2", category="Stuck analyzing",
    submission_id="bfdb7bd2-3ed0-4718-8aaa-3663a8d2d411",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Explicitly shows 'analyzing your response' for extended period with no resolution — analysis stuck indefinitely is always a platform bug."
))
rows.append(row(
    source_id="SLACK-1774365643.160899", time_gmt7="22:20", source="Slack",
    original_content="AI interviwer is not responding",
    email="rupashi023@gmail.com", candidate_name="rupashi sethi", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck analyzing",
    submission_id="de08ff00-fa9b-4fd4-9370-e700a8286520",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Platform Bug", confidence="High",
    assessment_notes="AI interviewer not responding after answer submission — stuck analyzing, no user action can cause AI to stop responding indefinitely."
))
rows.append(row(
    source_id="SLACK-1774366772.692559", time_gmt7="22:39", source="Slack",
    original_content="my answer recording is not submitting, it says just a moment we are analyzing your response",
    email="ashwinishital@gmail.com", candidate_name="Ashwini hanji", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck analyzing",
    submission_id="b1ffcfa0-2cc9-4dd4-a1b6-084358421fc8",
    interview_position="Online 1-on-1 Coding Tutor Interview Set (T)", interview_company="Ruvimo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    screenshot_url="https://data.flowmingo.ai/2026/03/24/15_39_23_foxtrot-bravo-bravo-golf-amber/v2fzd9aiqr.png",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Explicitly stuck on 'analyzing your response' — per judgment rules, analysis stuck indefinitely is always a Platform Bug."
))
rows.append(row(
    source_id="SLACK-1774369183.956599", time_gmt7="23:19", source="Slack",
    original_content="the platform freezes at 5 minutes to the end of the interview, and on refresh, it spools unknown questions and take too long to respond",
    email="fathiabenson@gmail.com", candidate_name="Faith Ibingha", topic_raw="Technical Issue",
    stage="Stage 2", category="Stuck during",
    submission_id="bd34971f-9bec-4dc3-866a-3a32bc765660",
    interview_position="Flowmingo Global Management Trainee (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Platform freezes near end of interview and shows unknown questions on refresh — platform-side freeze with state corruption on reload."
))
rows.append(row(
    source_id="SLACK-1774370919.992599", time_gmt7="23:48", source="Slack",
    original_content="I was doing an interview and had technical issues and now I can't recover my interview.",
    email="delfiagostino@gmail.com", candidate_name="Delfina Agostino", topic_raw="Others",
    stage="Stage 2", category="Stuck during",
    submission_id="e72ea855-9e0a-4f7c-83a3-8eb6747ac971",
    interview_position="Talent Acquisition Business Partner (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Safari 26.3", os="macOS", device="iPhone",
    assessment="Platform Bug", confidence="High",
    assessment_notes="Technical issues during interview with no recovery path — platform failure mid-interview with no resume capability."
))
rows.append(row(
    source_id="SLACK-1774371371.963599", time_gmt7="23:56", source="Slack",
    original_content="NOT SAVING THE ANSWERS",
    email="krithikajeyasuriyan06@gmail.com", candidate_name="Krithika Jeyasuriyan", topic_raw="Others",
    stage="Stage 2", category="Answer not saved / lost",
    submission_id="3cb7b445-b6c8-499e-8bcc-8e6c90f04b9d",
    interview_position="Human Resources Executive (For LinkedIn Applications)", interview_company="Flowmingo",
    browser="Chrome 146.0", os="Windows 10", device="Windows PC (64-bit)",
    assessment="Likely Platform Bug", confidence="Medium",
    assessment_notes="Answers not being saved during interview — platform not persisting recorded answers, which should happen automatically regardless of user action."
))

# ── Write CSV ─────────────────────────────────────────────────────────────────
with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=COLS)
    writer.writeheader()
    writer.writerows(rows)

# ── Summary ───────────────────────────────────────────────────────────────────
from collections import Counter
included = [r for r in rows if r["stage"] != "EXCLUDED"]
excluded = [r for r in rows if r["stage"] == "EXCLUDED"]
print(f"Total rows: {len(rows)} | Included: {len(included)} | Excluded: {len(excluded)}")
stage_counts = Counter(r["stage"] for r in included)
for s in ["Stage 1","Stage 2","Stage 3","Other (Company)","Other (Candidate)"]:
    print(f"  {s}: {stage_counts.get(s,0)}")
cat_counts = Counter(r["category"] for r in included)
print("\nCategory breakdown:")
for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
    print(f"  {cat}: {cnt}")
print(f"\nTotal bugs (included): {len(included)}")

# ── Push to Google Sheet ──────────────────────────────────────────────────────
print("\nCalling set_report_config...")
from src.api.sheets_client import set_report_config, upsert_daily_report_rows, check_report_complete
result = set_report_config("2026-03-24", 350, 351)
print("set_report_config:", result)

print("\nCalling upsert_daily_report_rows...")
result2 = upsert_daily_report_rows(rows)
print("upsert result:", result2)

print("\nCalling check_report_complete...")
result3 = check_report_complete("2026-03-24")
print("completion:", result3)
