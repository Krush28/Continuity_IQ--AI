"""Generate the demo handover documents (slide 10 scenario) into sample_docs/.

Scenario: Arjun Mehta, a developer on "ShopEase Order Management", is leaving.
Six scattered files: requirements PDF, technical notes DOCX, task status DOCX (table),
unresolved bugs PDF, database changes DOCX and a pending-work note (Markdown).
They deliberately contain real-world mess: one contradiction, a decision without a reason,
tasks without owners and a credential dependency, so the Gap Auditor has work to do.
"""
from pathlib import Path

import docx
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent.parent / "sample_docs"
OUT.mkdir(exist_ok=True)
ss = getSampleStyleSheet()


def pdf(name, blocks):
    story = []
    for kind, text in blocks:
        style = {"h1": ss["Title"], "h2": ss["Heading2"], "p": ss["BodyText"]}[kind]
        story += [Paragraph(text, style), Spacer(1, 4)]
    SimpleDocTemplate(str(OUT / name), pagesize=A4).build(story)


def word(name, parts):
    d = docx.Document()
    for kind, content in parts:
        if kind == "title":
            d.add_heading(content, 0)
        elif kind == "h":
            d.add_heading(content, 1)
        elif kind == "p":
            d.add_paragraph(content)
        elif kind == "li":
            d.add_paragraph(content, style="List Bullet")
        elif kind == "table":
            header, *rows = content
            t = d.add_table(rows=1, cols=len(header))
            t.style = "Table Grid"
            for i, h in enumerate(header):
                t.rows[0].cells[i].text = h
            for row in rows:
                cells = t.add_row().cells
                for i, v in enumerate(row):
                    cells[i].text = v
    d.save(OUT / name)


pdf("01_Requirements_ShopEase.pdf", [
    ("h1", "ShopEase Order Management System"),
    ("h2", "Overview"),
    ("p", "ShopEase is a web application for a mid-sized retail client in Pune to manage online orders, inventory and deliveries across three warehouses."),
    ("p", "The goal of phase 1 is to replace the client's spreadsheet-based order tracking before the Diwali sale season."),
    ("h2", "Scope"),
    ("p", "- Customer order placement and order history"),
    ("p", "- Inventory sync across the three warehouses every 15 minutes"),
    ("p", "- Payment collection through Razorpay"),
    ("p", "- Delivery status updates by SMS"),
    ("h2", "Requirements"),
    ("p", "- The system must support at least 500 concurrent users during sale periods."),
    ("p", "- Admin users must be able to export daily sales reports to Excel."),
    ("p", "- All customer data must be stored in India (data residency requirement from the client)."),
    ("h2", "Contacts"),
    ("p", "- Priya Nair (Project Manager) - priya.nair@shopease-demo.in - approvals, scope and client communication"),
    ("p", "- Rahul Desai (Client IT lead) - contact for warehouse API access and VPN"),
    ("p", "- Sneha Kulkarni (QA) - test plans and regression suite"),
])

word("02_Technical_Notes.docx", [
    ("title", "Technical Notes - ShopEase"),
    ("h", "Architecture decisions"),
    ("li", "We chose FastAPI for the backend because the team knows Python and it gives automatic API docs for the client's IT team."),
    ("li", "Decided to use PostgreSQL instead of MongoDB because orders, payments and inventory are strongly relational."),
    ("li", "Switched to Redis for caching product listings."),
    ("li", "Agreed to run inventory sync as a Celery background job every 15 minutes since the warehouse API is rate-limited to 60 calls per minute."),
    ("h", "Dependencies"),
    ("li", "Razorpay payment gateway - test and live API keys are stored in the team's Bitwarden vault under 'ShopEase'."),
    ("li", "Warehouse inventory REST API provided by the client - requires VPN access from Rahul Desai."),
    ("li", "MSG91 for SMS delivery notifications - depends on DLT template approval."),
    ("h", "Deployment"),
    ("p", "Staging is deployed on an AWS Mumbai (ap-south-1) EC2 instance using Docker Compose. Production deployment has not been set up yet."),
])

word("03_Task_Status.docx", [
    ("title", "Sprint 6 Task Status"),
    ("table", [
        ["Task", "Status", "Owner", "Priority"],
        ["User login and JWT authentication", "Done", "Arjun Mehta", "High"],
        ["Order placement API", "Done", "Arjun Mehta", "High"],
        ["Payment gateway integration", "Done", "Arjun Mehta", "High"],
        ["Inventory sync job", "In progress - 70%", "Arjun Mehta", "High"],
        ["Admin sales report export to Excel", "In progress", "", "Medium"],
        ["SMS delivery notifications", "Not started", "", "Medium"],
        ["Load testing for 500 users", "Not started", "", "High"],
    ]),
])

pdf("04_Unresolved_Bugs.pdf", [
    ("h1", "Known Issues - ShopEase (as of 10 Nov)"),
    ("h2", "Open bugs"),
    ("p", "- BUG-112: Duplicate orders are created when the customer double-clicks Pay on slow networks. Priority: High."),
    ("p", "- BUG-118: Inventory sync job fails with a timeout when a warehouse has more than 5,000 SKUs."),
    ("p", "- BUG-121: Sales report export shows wrong totals for orders refunded on the same day. Priority: Medium."),
    ("h2", "Resolved"),
    ("p", "- BUG-097: Login token expired too early - fixed by setting expiry to 12 hours."),
])

word("05_Database_Changes.docx", [
    ("title", "Database Changes Log"),
    ("h", "Schema changes"),
    ("li", "Added an idempotency_key column to the payments table to prevent double charges."),
    ("li", "Created the warehouse_stock table with a composite index on (warehouse_id, sku)."),
    ("li", "Migrated order status from free text to an enum (placed, paid, packed, shipped, delivered, cancelled)."),
    ("h", "Pending migrations"),
    ("li", "Need to add a refunds table before fixing BUG-121."),
])

(OUT / "06_Pending_Work.md").write_text("""# Pending work - handover note from Arjun

## Pending
- Payment gateway integration: webhook signature verification is still pending and must be done before go-live.
- Finish the inventory sync job: batch the warehouse API calls to fix the timeout (see BUG-118).
- Set up production deployment on AWS Mumbai.
- Write the load test for 500 concurrent users using Locust.

## Next steps
- Fix BUG-112 using the idempotency_key column that is already in the database.
- Get DLT template approval for SMS before starting SMS notifications.

## Who to ask
- Ask Priya Nair about scope changes and client deadlines.
- Contact Rahul Desai for warehouse API credentials and VPN.
""", encoding="utf-8")

print("Sample documents written to", OUT)
for f in sorted(OUT.iterdir()):
    print(" -", f.name)
